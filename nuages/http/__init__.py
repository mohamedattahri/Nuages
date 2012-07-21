import re
import itertools
import collections
from datetime import datetime
from django.conf import settings
from django.http import HttpResponse as _HttpResponse
from django.core.handlers.wsgi import STATUS_CODE_TEXT


__all__ = ('HttpResponse', 'HttpResponse', 'Etag', 'Range', 'ContentRange',
           'InvalidRequestError', 'ForbiddenError', 'NotModifiedError',
           'HttpException')


class HttpException(Exception):
    def __init__(self, node, status=503,
                 description=None):
        self.__locals = locals()
        map(lambda key: setattr(self, key, self.__locals[key]), self.__locals)
        super(Exception, self).__init__(description or STATUS_CODE_TEXT[status])


class InvalidRequestError(HttpException):
    def __init__(self, node, status=400):
        super(InvalidRequestError, self).__init__(node, status)


class ForbiddenError(HttpException):
    def __init__(self, node, description):
        super(ForbiddenError, self).__init__(node, 403, description)        

        
class NotModifiedError(HttpException):
    def __init__(self, node):
        super(NotModifiedError, self).__init__(node, 304)
        
        
def datetime_to_timestamp(datetm):
    '''
    Returns the timestamp representation of a datetime instance.
    '''
    return float(datetm.strftime("%s") + 
                ".%03d" % (datetm.time().microsecond / 1000))
    
    
def parse_datetime(datestr):
    '''
    Turns a ISO8601 or RFC1123 date string representation to a Python
    datetime instance.
    '''
    if 'T' in datestr:
        return datetime.strptime(datestr, '%Y-%m-%dT%T.%fZ')
    
    if 'GMT' in datestr:
        return datetime.strptime(datestr, '%a, %d %b %Y %T GMT')
    
    
class RequestMeta(collections.MutableMapping):
    '''Wrapper around the META dict of a Django HttpRequest instance'''
    def __init__(self, request_meta):
        '''
        @param request_meta:dict
        '''
        self.store = request_meta
        
    def __getitem__(self, key):
        try:
            key = self.__keytransform__(key)
            header, value = (key, self.store[key])
            
            if header in ['HTTP_IF_MATCH', 'HTTP_IF-NONE_MATCH']:
                return (Etag.parse(value) if ';' not in value
                        else [map(Etag.parse, value.split(';'))])
            
            if header == 'HTTP_IF_RANGE':
                return Etag.parse(value)
            
            if header in ['HTTP_IF_MODIFIED_SINCE',
                            'HTTP_IF_UNMODIFIED_SINCE']:
                return parse_datetime(value)
            
            if header == 'HTTP_ACCEPT':
                items = filter(lambda x: not x.startswith('q='),
                               itertools.chain(*[i.split(',') 
                                                 for i in value.split(';')]))
                return [settings.DEFAULT_CONTENT_TYPE if i == '*/*' else i
                        for i in items]
            
            return value
        except(KeyError), e:
            raise InvalidRequestError(400, repr(e))
    
    def __setitem__(self, key, value):
        self.store[self.__keytransform__(key)] = value

    def __delitem__(self, key):
        del self.store[self.__keytransform__(key)]

    def __iter__(self):
        return iter(self.store)

    def __len__(self):
        return len(self.store)

    def __keytransform__(self, key):
        return key.upper().replace('-', '_')
    
    
class HttpRequest(object):
    '''
    Wrapper around the DJANGO HttpRequest with improved methods,
    and attributes.
    '''
    def __init__(self, base_request):
        '''
        @param base_request:django.http.HttpRequest
        '''
        self._base_request = base_request
        self.META = RequestMeta(base_request.META)
        
    @property
    def method(self):
        '''
        Support for the X-HTTP-Method-Override header.
        Returns the value of the header if set, falls back to the real HTTP
        method if not.
        '''
        return self.META.get('X_HTTP_METHOD_OVERRIDE',
                             self._base_request.method)
        
    def __getattr__(self, name):
        '''
        Allows all the attributes of the base HttpRequest to be mirrored in
        the wrapper, unless they've been overridden. 
        '''
        return getattr(self._base_request, name)       
    
    
class HttpResponse(_HttpResponse):
    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        super(HttpResponse, self).__init__(*args, **kwargs)


class Etag(object):
    '''
    The ETag response-header field provides the current value of the entity 
    tag for the requested variant
    (http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.19)
    '''
    def __init__(self, last_modified, id_):
        self.__locals = locals()
        setattr(self, 'timestamp', datetime_to_timestamp(last_modified))
        map(lambda key: setattr(self, key, self.__locals[key]), self.__locals)
        
    def __cmp__(self, instance):
        return repr(self) == repr(instance)
        
    def __repr__(self):
        if not self.timestamp:
            return '*'
        
        return '%(timestamp)-%(id_)' % self.__locals
    
    @classmethod
    def parse(cls, raw_etag):
        try:
            timestamp, id_ = raw_etag.split('-')
            return cls(datetime.fromtimestamp(timestamp), id_)
        except:
            ValueError('Invalid \'Etag\' header value')
            
            
ETAG_WILDCARD = Etag(datetime.fromtimestamp(0), '0')


class Range(object):
    '''
    Parses the content of a Range header into a simple helper class.
    
    HTTP retrieval requests using conditional or unconditional GET methods
    MAY request one or more sub-ranges of the entity, instead of the entire 
    entity.
    (http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.35.2)
    '''
    def __init__(self, unit, offset, limit):
        map(lambda key: setattr(self, key, locals()[key]), locals())
    
    @classmethod
    def parse(cls, raw_header):
        #FIXME: Not all the formats defined by the HTTP RFC are supported
        match = re.match(r'^(?P<unit>\w+)=(?P<offset>\d+)-(?P<limit>\d+)$',
                         raw_header)
        if not match:
            raise ValueError('Invalid \'Range\' header value')
            
        return cls(*match.groupdict())


class ContentRange(object):
    '''
    Builds a valid Content-Range header representation as defined in the
    HTTP protocol.
    
    The Content-Range entity-header is sent with a partial entity-body to 
    specify where in the full entity-body the partial body should be applied.
    (http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.16)
    '''
    def __init__(self, unit, first, last, total):
        self.__locals = locals()
        map(lambda key: setattr(self, key, self.__locals[key]), self.__locals)
        
    def __repr__(self):
        return '%(unit) %(first)-%(last)/%(total)' % self.__locals
