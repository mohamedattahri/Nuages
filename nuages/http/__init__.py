import re
import itertools
import collections
import logging
import inspect
from datetime import datetime, date
from django.conf import settings
from django.utils.http import parse_http_date, http_date
from django.http import Http404, HttpResponse as _HttpResponse
from django.core.handlers.wsgi import STATUS_CODE_TEXT


__all__ = ('HttpResponse', 'HttpResponse', 'HttpError', 'NotModifiedError',
           'InvalidRequestError', 'UnauthorizedError', 'ForbiddenError',
           'MethodNotAllowedError', 'NotAcceptableError', 'ConflictError',
           'PreconditionFailedError', 'UnsupportedMediaTypeError',
           'RequestRangeNotSatisfiableError', 'Etag', 'Range', 'ContentRange',)


logger = logging.getLogger(__name__)
ISO8601_DATEFORMAT = '%Y-%m-%dT%T.%fZ'
        
        
def datetime_to_timestamp(datetm):
    '''Returns the timestamp representation of a datetime instance.'''
    return float(datetm.strftime("%s") + 
                ".%03d" % (datetm.time().microsecond / 1000))
    

def datetime_to_str(datetm):
    '''Returns a string representation of the current date'''
    return http_date(datetime_to_timestamp(datetm))
    
    
def parse_datetime(datestr):
    '''Turns a ISO8601 or RFC1123 date string representation to a Python
    datetime instance.'''
    try:
        datestr = float(datestr)
        return datetime.fromtimestamp(datestr)
    except ValueError:
        pass
    
    try:
        datestr = str(datestr)
        if 'GMT' in datestr:    
            return datetime.fromtimestamp(parse_http_date(datestr))
        
        return datetime.strptime(datestr, ISO8601_DATEFORMAT)
    except Exception, e:
        raise ValueError('Unable to parse date \'%s\' (reason: %s)' % 
                           (datestr, repr(e)))
    
    
class RequestMeta(collections.MutableMapping):
    '''Wrapper around the META dict of a Django HttpRequest instance'''
    def __init__(self, request_meta):
        self.store = request_meta
        
    def __getitem__(self, key):
        key = self.__keytransform__(key)
        header, value = key, self.store.get(key)
        try:
            if header == 'HTTP_AUTHORIZATION':
                try:
                    protocol, token = value.strip(' ').split(' ')
                    protocol = protocol.upper()
                    if protocol == 'BASIC':
                        username, password = token.decode('base64').split(':')
                        return protocol, username, password
                    
                    return protocol, token
                except ValueError:
                    return value
            
            if header in ['HTTP_IF_MATCH', 'HTTP_IF_NONE_MATCH']:
                return (Etag.parse(value) if ';' not in value
                        else [map(Etag.parse, value.split(';'))])
            
            if header == 'HTTP_IF_RANGE':
                return Etag.parse(value)
            
            if header in ['HTTP_IF_MODIFIED_SINCE',
                          'HTTP_IF_UNMODIFIED_SINCE']:
                return parse_datetime(value)
            
            if header == 'HTTP_RANGE':
                return Range.parse(value)
            
            if header == 'HTTP_ACCEPT':
                if not value:
                    return [settings.DEFAULT_CONTENT_TYPE]
                
                items = filter(lambda x: not x.startswith('q='),
                               itertools.chain(*[i.split(',') 
                                                 for i in value.split(';')]))
                return [settings.DEFAULT_CONTENT_TYPE if i == '*/*' else i
                        for i in items]
            return value
        except:
            return value
        
    def get(self, key, default=None):
        try:
            if self.__keytransform__(key) in self.store:
                return self.__getitem__(key)
        except:
            pass
        
        return default
    
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
        self._base_request = base_request
        self.META = RequestMeta(base_request.META)
        
    @property
    def method(self):
        '''Support for the X-HTTP-Method-Override header.
        Returns the value of the header if set, falls back to the real HTTP
        method if not.'''
        return self.META.get('HTTP_X_HTTP_METHOD_OVERRIDE',
                             self._base_request.method).upper()
        
    def __getattr__(self, name):
        '''Allows all the attributes of the base HttpRequest to be mirrored in
        the wrapper, unless they've been overridden.'''
        return getattr(self._base_request, name)       
    
    
class HttpResponse(_HttpResponse):
    '''A transparent wrapper around the Django HttpResponse class.'''
    def __init__(self, node=None, payload=None, *args, **kwargs):
        self.__node = node
        self.payload = None
        super(HttpResponse, self).__init__(*args, **kwargs)
        
    def __getattr(self, attr):
        if attr == 'status':
            attr = 'status_code'
        return super(HttpResponse, self).__getattr__(attr)
        
    def __setattr__(self, attr, val):
        if attr == 'status':
            attr = 'status_code'
        return super(HttpResponse, self).__setattr__(attr, val)
        
    def __setitem__(self, header, value):
        '''Conversion of types'''
        if type(value) in (datetime, date):
            value = datetime_to_str(value)
            
        super(HttpResponse, self).__setitem__(header, value)
       
    @property
    def content_type(self):
        value = self.get('Content-Type', settings.DEFAULT_CONTENT_TYPE)
        return value[:max(0, value.find('; charset')) or None].strip(' ')
        
    @property
    def node(self):
        return self.__node        


class HttpError(HttpResponse, Exception):
    '''When raised, turns to an HTTP response detailing the error that
    occurred. 
    This class is both an Exception and an HttpResponse, which means it can
    be "raised', or be the value returned by a view.'''
    def __init__(self, node=None, status=503, description=''):
        HttpResponse.__init__(self, status=status)
        Exception.__init__(self)
        self.message = description or STATUS_CODE_TEXT.get(status)
        self.__node = node
        self.content = str(self)
        
    @property
    def node(self):
        return self.__node
    
    def __str__(self):
        return self.message
    

class NotFoundError(HttpError):
    ''''''
    def __init__(self, node=None):
        super(NotFoundError, self).__init__(node, 404)

        
class NotModifiedError(HttpError):
    '''"If the client has performed a conditional GET request and access is
    allowed, but the document has not been modified, the server SHOULD respond
    with this status code. The 304 response MUST NOT contain a message-body,
    and thus is always terminated by the first empty line after the header
    fields."'''
    def __init__(self, node=None):
        super(NotModifiedError, self).__init__(node, 304)
        

class InvalidRequestError(HttpError):
    '''"The request could not be understood by the server due to malformed
    syntax"'''
    def __init__(self, node=None, status=400, description=''):
#        assert False, description
        super(InvalidRequestError, self).__init__(node, status, description)
        

class UnauthorizedError(HttpError):
    '''"The request requires user authentication.
    The response MUST include a WWW-Authenticate header field (section 14.47)
    containing a challenge applicable to the requested resource."
    
    (http://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.4.2)'''
    def __init__(self, node=None):
        super(UnauthorizedError, self).__init__(node, 401)
        #TODO: Add a WWW-Authenticate header


class ForbiddenError(HttpError):
    '''The server understood the request, but is refusing to fulfill it.
    Authorization will not help and the request SHOULD NOT be repeated.
    If the request method was not HEAD and the server wishes to make public
    why the request has not been fulfilled, it SHOULD describe the reason for
    the refusal in the entity. If the server does not wish to make this
    information available to the client, the status code 404 (Not Found)
    can be used instead.'''
    def __init__(self, node=None, description=None):
        if not description:
            raise Http404
        super(ForbiddenError, self).__init__(node, 403, description)
        
        
class MethodNotAllowedError(HttpError):
    '''"The method specified in the Request-Line is not allowed for the
    resource identified by the Request-URI. The response MUST include an
    Allow header containing a list of valid methods for the requested
    resource."'''
    def __init__(self, node=None):
        super(MethodNotAllowedError, self).__init__(node, 405)
        node = node if inspect.isclass(node) else node.__class__
        self['Allow'] = ', '.join(node.get_allowed_methods(implicits=False))
        
        
class NotAcceptableError(HttpError):
    '''"The resource identified by the request is only capable of generating
    response entities which have content characteristics not acceptable
    according to the accept headers sent in the request.
    
    Unless it was a HEAD request, the response SHOULD include an entity
    containing a list of available entity characteristics and location(s)
    from which the user or user agent can choose the one most appropriate."'''
    def __init__(self, node):
        description = ', '.join(node.outputs)
        super(NotAcceptableError, self).__init__(node, 406, description)
        

class ConflictError(HttpError):
    '''"The request could not be completed due to a conflict with the current
    state of the resource. This code is only allowed in situations where it is 
    expected that the user might be able to resolve the conflict and resubmit
    the request. The response body SHOULD include enough information for the
    user to recognize the source of the conflict. Ideally, the response entity
    would include enough information for the user or user agent to fix the
    problem; however, that might not be possible and is not required."'''
    def __init__(self, node=None, description=None):
        super(ConflictError, self).__init__(node, 409, description)
        
        
class PreconditionFailedError(HttpError):
    '''"The precondition given in one or more of the request-header fields
    evaluated to false when it was tested on the server."'''
    def __init__(self, node=None, description=''):
        super(PreconditionFailedError, self).__init__(node, 412, description)


class UnsupportedMediaTypeError(HttpError):
    '''"The server is refusing to service the request because the entity of
    the request is in a format not supported by the requested resource for the
    requested method."'''
    def __init__(self, node=None, description=''):
        super(UnsupportedMediaTypeError, self).__init__(node, 415, description)
        
        
class RequestedRangeNotSatisfiableError(HttpError):
    '''"A server SHOULD return a response with this status code if a request
    included a Range request-header field (section 14.35), and none of the
    range-specifier values in this field overlap the current extent of the
    selected resource, and the request did not include an If-Range
    request-header field. "'''
    def __init__(self, node=None, description=''):
        super(RequestedRangeNotSatisfiableError, self).__init__(node, 416,
                                                                description)


class Etag(object):
    '''The ETag response-header field provides the current value of the entity 
    tag for the requested variant
    (http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.19)'''
    def __init__(self, last_modified, id_):
        self.__locals = locals()
        setattr(self, 'timestamp', datetime_to_timestamp(last_modified))
        self.__locals['timestamp'] = self.timestamp
        map(lambda key: setattr(self, key, self.__locals[key]), self.__locals)
        
    def __eq__(self, instance):
        try:
            if not instance:
                return False
            
            #A WILDCARD ETag is considered equal to any ETag value.
            if repr(self) == '*' or repr(instance) == '*':
                return True
            
            if self.id_ != instance.id_:
                return False
    
            return self.last_modified == instance.last_modified
        except:
            return False
    
    def __ne__(self, instance):
        return not self.__eq__(instance)
        
    def __cmp__(self, instance):
        if not instance:
            return 1
        
        #A WILDCARD ETag is considered equal to any ETag value.
        if repr(self) == '*' or repr(instance) == '*': 
            return 0
        
        return self.last_modified - instance.last_modified
    
    def __repr__(self):
        if not self.timestamp:
            return '*'
        
        return '%f-%s' % (self.timestamp, self.id_)
    
    @classmethod
    def parse(cls, raw_etag):
        try:
            timestamp, id_ = raw_etag.split('-')
            return cls(datetime.fromtimestamp(timestamp), id_)
        except:
            ValueError('Invalid \'Etag\' header value')
            
            
ETAG_WILDCARD = Etag(datetime.fromtimestamp(0), '0')


class Range(object):
    '''Parses the content of a Range header into a simple helper class.
    
    HTTP retrieval requests using conditional or unconditional GET methods
    MAY request one or more sub-ranges of the entity, instead of the entire 
    entity.
    (http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.35.2)'''
    def __init__(self, unit, offset, limit):
        self.__locals = locals()
        map(lambda key: setattr(self, key, self.__locals[key]), self.__locals)
    
    @classmethod
    def parse(cls, raw_header):
        #FIXME: Not all the formats defined by the HTTP RFC are supported
        match = re.match(r'^(?P<unit>\w+)=(?P<offset>\d+)-(?P<limit>\d+)$',
                         raw_header)
        if not match:
            raise ValueError('Invalid \'Range\' header value')
        
        values = match.groupdict()     
        return cls(values['unit'],
                   int(values['offset']),
                   int(values['limit']))


class ContentRange(object):
    '''Builds a valid Content-Range header representation as defined in the
    HTTP protocol.
    
    The Content-Range entity-header is sent with a partial entity-body to 
    specify where in the full entity-body the partial body should be applied.
    (http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.16)'''
    def __init__(self, unit, first, last, total):
        self.__locals = locals()
        map(lambda key: setattr(self, key, self.__locals[key]), self.__locals)
        
    def __repr__(self):
        return '%(unit) %(first)-%(last)/%(total)' % self.__locals
