import re
from datetime import datetime
from django.http import (HttpRequest as _HttpRequest,
                         HttpResponse as _HttpResponse)


__all__ = ['HTTP_METHODS', 'HttpResponse', 'HttpResponse', 'Etag', 'Range',
           'ContentRange', 'InvalidRequestError', 'HttpException']


HTTP_METHODS = ['HEAD', 'GET', 'POST', 'PATCH', 'PUT', 'DELETE', 'OPTIONS']

    
class HttpException(Exception):
    def __init__(self, request, status_code=503,
                 description="Service unavailable"):
        map(lambda k, v: setattr(self, k, v), self.__locals.items())


class InvalidRequestError(HttpException):
    '''
    Represents an exception raised during the initial phase of validation
    of the HTTP request.s
    '''
    def __init__(self, request):
        super(InvalidRequestError, self).__init__(request, 400)
        
        
class NotModifiedError(HttpException):
    def __init__(self, request):
        super(NotModifiedError, self).__init__(request, 304)
        
        
def datetime_to_timestamp(datetm):
    '''
    Returns the timestamp representation of a datetime instance.
    '''
    return long(datetm.strftime("%s") + 
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


class HttpRequest(_HttpRequest):
    ''''''
    def __getattr__(self, header):
        '''
        Overrides the default behavior to parse the header values into
        something much easier to manipulate.
        '''
        try:
            header, value = (header.upper(), self._headers[header]) 
            if header in ['HTTP_IF_MATCH', 'HTTP_IF-NONE_MATCH']:
                return (Etag.parse(value) if ';' not in value
                        else [map(Etag.parse, value.split(';'))])
            elif header is 'HTTP_IF_RANGE':
                return Etag.parse(value)
            elif header in ['HTTP_IF_MODIFIED_SINCE',
                            'HTTP_IF_UNMODIFIED_SINCE']:
                return parse_datetime(value)
        except(ValueError), e:
            raise InvalidRequestError(400, repr(e))
    
    
class HttpResponse(_HttpResponse):
    ''''''
    def __init__(self, request):
        self.__request = request


class Etag(object):
    '''
    The ETag response-header field provides the current value of the entity 
    tag for the requested variant
    (http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.19)
    '''
    def __init__(self, last_modified, id_):
        self.__locals = locals()
        setattr(self, 'timestamp', datetime_to_timestamp(last_modified))
        map(lambda k, v: setattr(self, k, v), self.__locals.items())
        
    def __repr__(self):
        return '%(timestamp)-%(id_)' % self.__locals
    
    @classmethod
    def parse(cls, raw_etag):
        try:
            timestamp, id_ = raw_etag.split('-')
            return cls(datetime.fromtimestamp(timestamp), id_)
        except:
            ValueError('Invalid \'Etag\' header value')


class Range(object):
    '''
    Parses the content of a Range header into a simple helper class.
    
    HTTP retrieval requests using conditional or unconditional GET methods
    MAY request one or more sub-ranges of the entity, instead of the entire 
    entity.
    (http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.35.2)
    '''
    def __init__(self, unit, offset, limit):
        map(lambda k, v: setattr(self, k, v), locals().items())
    
    @classmethod
    def parse(cls, raw_header):
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
        map(lambda k, v: setattr(self, k, v), self.__locals.items())
        
    def __repr__(self):
        return '%(unit) %(first)-%(last)/%(total)' % self.__locals
