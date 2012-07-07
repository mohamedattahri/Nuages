# -*- coding: utf-8 -*-
from nuages.http import (HttpResponse, InvalidRequestError, NotModifiedError)


class HttpNode(object):
    ''''''
    name = None
    parent = None
    uri = None
    range_unit = ('resource', 'resources')
    max_limit = 200
    allows = ['HEAD', 'GET']
    outputs = ['application/json', 'application/xml']
    
    def __init__(self, request, *args, **kwargs):
        self._request = request
        
        if request.method.upper() not in self.allows:
            raise InvalidRequestError(request, 405) #Method not allowed
        
        self.__matching_outputs = set(self.allows) & set(request['HTTP_ACCEPT'])
        if not len(self.__matching_outputs):
            raise  InvalidRequestError(request, 406) #Not acceptable
    
    def _get(self, *args, **kwargs):
        '''
        GET method documentation.
        '''
        if (self._request['HTTP_IF_MATCH'] is not self.etag or
            self._request['HTTP_IF_NONE_MATCH'] is self.etag):
            raise InvalidRequestError(self, 412) #Precondition Failed
        
        if (self._request['HTTP_IF_MODIFIED_SINCE'] < self.etag or
            self._request['HTTP_IF_UNMODIFIED_SINCE'] > self.etag):
            raise NotModifiedError(self, 304) #Not modified
        
        response = HttpResponse(self, 200)
        response['Etag'] = self.etag
        response['Last-Modified'] = self.last_modified
        return response
    
    def _post(self, *args, **kwargs):
        '''
        POST method documentation.
        '''
        raise NotImplementedError()
    
    def _patch(self, *args, **kwargs):
        '''
        PATCH method documentation.
        '''
        if self._request['HTTP_IF_MATCH'] is self.etag:
            raise InvalidRequestError(self, 409) #Conflict
        
        return HttpResponse(self._request, self)
    
    def _put(self, *args, **kwargs):
        '''
        PUT method documentation.
        '''
        raise NotImplementedError()
    
    def _delete(self, *args, **kwargs):
        '''
        DELETES method documentation.
        '''
        raise NotImplementedError()
    
    def _head(self, *args, **kwargs):
        response = self._get(*args, **kwargs)
        response.content = ''
        return response
    
    def _options(self):
        '''
        The OPTIONS method represents a request for information about
        the communication options available on the request/response chain 
        identified by the Request-URI. This method allows the client to 
        determine the options and/or requirements associated with a resource, 
        or the capabilities of a server, without implying a resource action or 
        initiating a resource retrieval.
        [...]
        The response body, if any, SHOULD also include information about
        the communication options.
        (http://www.w3.org/Protocols/rfc2616/rfc2616-sec9.html#sec9.2)
        
        Nuages uses the docstring of each HTTP method handler allowed for
        the current node to generate a doc and add it to the body of the 
        response.
        '''
        response = HttpResponse(200)
        response['Allow'] = ','.join(map(lambda x: x.upper(), self.allows))
        
        #TODO: Format the output in something people can use.        
        docs = [getattr('_%s_%s', self.__class__.__name__, 
                        method.lower()).__doc__ 
                for method in filter('HEAD', self.allows)]
        response.content = '\n'.join(docs)
        
        return response
        
    @classmethod
    def process(cls, request, *args, **kwargs):
        instance = cls(request, **kwargs)
        method_func = getattr(instance, '_%s_%s' % (instance.__class__.__name__,
                                                    request.method.lower()))
        return method_func(**kwargs)


class CollectionNode(HttpNode):
    def fetch(self, query=None, offset=0, limit=200):
        if limit > self.max_limit:
            raise InvalidRequestError(self, 413) #Request Entity Too Large
        
        result = []
        if not len(result):
            raise InvalidRequestError(self, 416) #Requested Range Not Satisfiable
        
        return result
    
    def _get(self, query='', *args):
        response = super(CollectionNode, self)._get()
        
        range = self._request['HTTP_RANGE']
        offset, limit = (0, 200)
        if range:
            response.status_code = 206 #Partial
            offset, limit = (range.offset, range.limit)
        else:
            response['Accept-Range'] = self.range_unit[1]
        
        response.content = self.fetch(query=filter, offset=offset,
                                      limit=limit)
        return response

    def _post(self, *args, **kwargs):
        pass


class ResourceNode(HttpNode):
    
    def _get(self, *args, **kwargs):
        pass
    
    def _patch(self):
        pass
    
    def _delete(self):
        pass