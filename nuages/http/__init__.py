import re
import itertools
import collections
import logging
from datetime import datetime
from django.conf import settings
from django.http import Http404, HttpResponse as _HttpResponse
from django.core.handlers.wsgi import STATUS_CODE_TEXT


__all__ = ('HttpResponse', 'HttpResponse', 'Etag', 'Range', 'ContentRange',
           'InvalidRequestError', 'ForbiddenError', 'NotModifiedError',
           'HttpException')


logger = logging.getLogger(__name__)
        
        
def datetime_to_timestamp(datetm):
    '''Returns the timestamp representation of a datetime instance.'''
    return float(datetm.strftime("%s") + 
                ".%03d" % (datetm.time().microsecond / 1000))
    
    
def parse_datetime(datestr):
    '''Turns a ISO8601 or RFC1123 date string representation to a Python
    datetime instance.'''
    if 'T' in datestr:
        return datetime.strptime(datestr, '%Y-%m-%dT%T.%fZ')
    
    if 'GMT' in datestr:
        return datetime.strptime(datestr, '%a, %d %b %Y %T GMT')
    
    
class RequestMeta(collections.MutableMapping):
    '''Wrapper around the META dict of a Django HttpRequest instance'''
    def __init__(self, request_meta):
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
            
            if header == 'Range':
                return Range.parse(value)
            
            if header == 'HTTP_ACCEPT':
                items = filter(lambda x: not x.startswith('q='),
                               itertools.chain(*[i.split(',') 
                                                 for i in value.split(';')]))
                return [settings.DEFAULT_CONTENT_TYPE if i == '*/*' else i
                        for i in items]
            
            return value
        except(ValueError), e:
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
        self._base_request = base_request
        self.META = RequestMeta(base_request.META)
        
    @property
    def method(self):
        '''Support for the X-HTTP-Method-Override header.
        Returns the value of the header if set, falls back to the real HTTP
        method if not.'''
        return self.META.get('X_HTTP_METHOD_OVERRIDE',
                             self._base_request.method)
        
    def __getattr__(self, name):
        '''Allows all the attributes of the base HttpRequest to be mirrored in
        the wrapper, unless they've been overridden. '''
        return getattr(self._base_request, name)       
    
    
class HttpResponse(_HttpResponse):
    '''A transparent wrapper around the Django HttpResponse class.
    Currently not really useful, but this would save some time if the need
    becomes clearer later.'''
    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        super(HttpResponse, self).__init__(*args, **kwargs)
        

class HttpException(Exception, HttpResponse):
    '''When raised, turns to an HTTP response detailing the error that
    occurred. 
    This class is both an Exception and an HttpResponse, which means it can
    be "raised', or be the value returned by a view.'''
    def __init__(self, node, status=503, description=''):
        description = description or STATUS_CODE_TEXT[status]
        Exception.__init__(self, description)
        _HttpResponse.__init__(self, status=status,
                               content=self.format_description())
        self.__node = node
        
    @property
    def node(self):
        return self.__node
    
    def format_description(self):
        return '<hello>%s</world>' % str(self)        

        
class NotModifiedError(HttpException):
    '''"If the client has performed a conditional GET request and access is
    allowed, but the document has not been modified, the server SHOULD respond
    with this status code. The 304 response MUST NOT contain a message-body,
    and thus is always terminated by the first empty line after the header
    fields."'''
    def __init__(self, node):
        super(NotModifiedError, self).__init__(node, 304)
        

class InvalidRequestError(HttpException):
    '''"The request could not be understood by the server due to malformed
    syntax"'''
    def __init__(self, node, status=400, description=''):
        super(InvalidRequestError, self).__init__(node, status, description)
        

class Unauthorized(HttpException):
    '''"The request requires user authentication.
    The response MUST include a WWW-Authenticate header field (section 14.47)
    containing a challenge applicable to the requested resource."
    
    (http://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.4.2)'''
    def __init__(self, node):
        super(Unauthorized, self).__init__(node, 401)
        #TODO: Add a WWW-Authenticate header


class ForbiddenError(HttpException):
    '''The server understood the request, but is refusing to fulfill it.
    Authorization will not help and the request SHOULD NOT be repeated.
    If the request method was not HEAD and the server wishes to make public
    why the request has not been fulfilled, it SHOULD describe the reason for
    the refusal in the entity. If the server does not wish to make this
    information available to the client, the status code 404 (Not Found)
    can be used instead.'''
    def __init__(self, node, description=None):
        if not description:
            raise Http404
        super(ForbiddenError, self).__init__(node, 403, description)
        
        
class MethodNotAllowedError(HttpException):
    '''"The method specified in the Request-Line is not allowed for the
    resource identified by the Request-URI. The response MUST include an
    Allow header containing a list of valid methods for the requested
    resource."'''
    def __init__(self, node):
        super(MethodNotAllowedError, self).__init__(node, 405)
        self['Allow'] = ', '.join(node.allow)
        
        
class NotAcceptableError(HttpException):
    '''"The resource identified by the request is only capable of generating
    response entities which have content characteristics not acceptable
    according to the accept headers sent in the request.
    
    Unless it was a HEAD request, the response SHOULD include an entity
    containing a list of available entity characteristics and location(s)
    from which the user or user agent can choose the one most appropriate."'''
    def __init__(self, node):
        description = ', '.join(node.outputs)
        super(NotAcceptableError, self).__init__(node, 406, description)
        

class ConflictError(HttpException):
    '''"The request could not be completed due to a conflict with the current
    state of the resource. This code is only allowed in situations where it is 
    expected that the user might be able to resolve the conflict and resubmit
    the request. The response body SHOULD include enough information for the
    user to recognize the source of the conflict. Ideally, the response entity
    would include enough information for the user or user agent to fix the
    problem; however, that might not be possible and is not required."'''
    def __init__(self, node, description=None):
        super(ConflictError, self).__init__(node, 409, description)
        
        
class PreconditionFailedError(HttpException):
    '''"The precondition given in one or more of the request-header fields
    evaluated to false when it was tested on the server."'''
    def __init__(self, node, description=''):
        super(PreconditionFailedError, self).__init__(node, 412, description)


class UnsupportedMediaTypeError(HttpException):
    '''"The server is refusing to service the request because the entity of
    the request is in a format not supported by the requested resource for the
    requested method."'''
    def __init__(self, node, description=''):
        super(UnsupportedMediaTypeError, self).__init__(node, 415, description)
        
        
class RequestedRangeNotSatisfiableError(HttpException):
    '''"A server SHOULD return a response with this status code if a request
    included a Range request-header field (section 14.35), and none of the
    range-specifier values in this field overlap the current extent of the
    selected resource, and the request did not include an If-Range
    request-header field. "'''
    def __init__(self, node, description=''):
        super(RequestedRangeNotSatisfiableError, self).__init__(node, 416,
                                                                description)


class Etag(object):
    '''The ETag response-header field provides the current value of the entity 
    tag for the requested variant
    (http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.19)'''
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
            
        return cls(*match.groupdict())


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
