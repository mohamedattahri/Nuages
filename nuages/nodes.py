# -*- coding: utf-8 -*-
import inspect
import urlparse
from django.conf import settings
from django.utils.importlib import import_module
from django.core.urlresolvers import reverse, resolve
from nuages.http import (HttpRequest, HttpResponse, InvalidRequestError,
                         Range, ETAG_WILDCARD, ForbiddenError,
                         RequestedRangeNotSatisfiableError,)
from nuages.utils import get_matching_mime_types


__all__ = ('Node', 'CollectionNode', 'ResourceNode')


API_ENDPOINT = urlparse.urlparse(settings.NUAGES_API_ENDPOINT
                                 if hasattr(settings, 'NUAGES_API_ENDPOINT')
                                 else '')


HTTP_METHODS_HANDLERS = {'GET'      : 'render',
                         'POST'     : 'create',
                         'PUT'      : 'replace',
                         'PATCH'    : 'patch',
                         'DELETE'   : 'delete', }


class Node(object):
    url = None
    name = None
    parent = None
    secure = False
    outputs = ['application/json', 'application/xml',
               'application/xml+xhtml', 'text/html', '*/*']
    
    def __new__(cls, *args, **kwargs):
        cls.outputs = [settings.DEFAULT_CONTENT_TYPE if c == '*/*' else c
                       for c in cls.outputs]
        return object.__new__(cls, *args, **kwargs)
    
    def __init__(self, request, *args, **kwargs):
        '''Initializes a new instance of the Node class:
         
        - request: Current HttpRequest instance.
        - *args, **kwargs are passed all the way to the top parent node.'''
        self._try_cross()    
            
        self.request = request
        members = filter(lambda x: x not in ['self', 'request',
                                             'parent_instance'],
                         inspect.getargspec(self.__init__)[0])
        self.__locals = dict(zip(members, args))
        map(lambda t: setattr(self, t[0], t[1]), self.__locals.items())
        
        self._parent_instance = kwargs.pop('parent_instance', None)
        if self._parent_instance:
            self.parent = self._parent_instance.__class__
            self.request = self._parent_instance.request
        elif self.parent:
            self._parent_instance = self.parent(request, **kwargs)
            
        self._matching_outputs = get_matching_mime_types(request,
                                                         self.__class__)
    
    def _can_cross(self):
        '''Returns a boolean indicating whether the node can be crossed to
        access a child node or not.'''
        return True
        
    def _can_read(self):
        '''Returns a boolean indicating whether the resource of the node can
        be serialized or not.'''
        return False
    
    def _can_write(self):
        '''Returns a boolean indicating whether the resource of the node can
        be modified or not'''
        return False
    
    def _try_cross(self):
        '''Checks if the node is crossable, otherwise raises an exception.'''
        if not self._can_cross():
            raise ForbiddenError(self, 'Access to resource has been denied.')
    
    def _try_read(self):
        '''Checks if the node is readable, otherwise raises an exception.'''
        if not self._can_read():
            raise ForbiddenError(self, 'Access to resource has been denied.')    
    
    def _try_write(self):
        '''Checks if the node is modifiable, otherwise raises an exception.'''
        if not self._can_write():
            raise ForbiddenError(self, 'Access to resource has been denied.')
    
    def build_url(self, absolute=True):
        '''Dynamically builds the URL of the current node.
        
        - absolute: specifies whether to return an absolute URL, including the
        API root configured in the settings.'''
        self._try_read() #You don't need the URL of a resource you can't see.
        
        kwargs = self.__locals
        if self._parent_instance:
            parent_url = self._parent_instance.build_url(absolute=False)
            kwargs.update(resolve(parent_url)[2])

        relative = reverse(self.__class__.get_view_name(), kwargs=kwargs)
        if not absolute:
            return relative
        
        return urlparse.urlunparse(('https' if self.secure else 'http',
                                    API_ENDPOINT[1] or self.request.get_host(),
                                    relative, None, None, None))

    def get_etag(self):
        '''Gets the ETag of the current node.'''
        return ETAG_WILDCARD
    
    def _call_http_method_handler(self, *args, **kwargs):
        handler = getattr(self,
                          HTTP_METHODS_HANDLERS[self.request.method.upper()])
        return handler(*args, **kwargs)
    
    def _process_get(self):
        self._try_read()
        
        response = HttpResponse(self, content_type=self._matching_outputs[0])
        data = self._call_http_method_handler()
        
        for node_cls in self.__class__.get_children_nodes():
            try:
                node_url = node_cls(self.request, **self.__locals).build_url()
                data[node_cls.name or node_cls.__name__.lower()] = node_url
            except ForbiddenError:
                continue
            except TypeError:
                continue
            
        response.payload = data    
        return response
    
    def _process_post(self):
        raise NotImplementedError()
    
    def _process_patch(self):
        raise NotImplementedError()
    
    def _process_put(self):
        raise NotImplementedError()
    
    def _process_delete(self):
        raise NotImplementedError()
    
    def _process_head(self):
        '''The HEAD method is identical to GET except that the server MUST NOT
        return a message-body in the response. The metainformation contained
        in the HTTP headers in response to a HEAD request SHOULD be identical
        to the information sent in response to a GET request.'''
        return self._process_get()
    
    def _process_options(self):
        '''The OPTIONS method represents a request for information about
        the communication options available on the request/response chain 
        identified by the Request-URL. This method allows the client to 
        determine the options and/or requirements associated with a resource, 
        or the capabilities of a server, without implying a resource action or 
        initiating a resource retrieval.
        [...]
        The response body, if any, SHOULD also include information about
        the communication options.
        (http://www.w3.org/Protocols/rfc2616/rfc2616-sec9.html#sec9.2)
        
        Nuages uses the docstring of each HTTP method handler allowed for
        the current node to generate a doc and add it to the body of the 
        response.'''
        allowed = self.__class__.get_allowed_methods(implicits=False)
        response = HttpResponse(self, 200)
        response['Allow'] = ', '.join(map(lambda x: x.upper(), allowed))
        
        #TODO: Format the output in something people can use.        
        docs = filter(bool,
                      [getattr(self, HTTP_METHODS_HANDLERS[m.upper()]).__doc__
                       for m in allowed])
        response.content = '\n'.join(docs)
        return response
    
    @classmethod
    def get_children_nodes(cls):
        root_urlconf = import_module(settings.ROOT_URLCONF)
        return [url.callback.im_self for url in root_urlconf.urlpatterns
                if url.callback.im_self.parent and
                issubclass(url.callback.im_self.parent, cls) ]
        
    @classmethod
    def get_full_url_pattern(cls):
        if not cls.parent:
            return cls.url
        
        if not issubclass(cls.parent, Node):
            raise ValueError('\'parent\' must be an instance of HttpNode')
        
        return (cls.parent.get_full_url_pattern().rstrip('$') +
                cls.url.lstrip('^'))
    
    @classmethod
    def get_view_name(cls):
        if cls.name:
            return cls.name
        
        return cls.__module__.replace('.', '_') + '_' + cls.__name__
    
    @classmethod
    def get_allowed_methods(cls, implicits=True):
        implicit_methods = ['HEAD', 'OPTIONS'] if implicits else []
        return [method for method, handler in HTTP_METHODS_HANDLERS.items()
                if hasattr(cls, handler) and
                inspect.ismethod(getattr(cls, handler))] + implicit_methods
                
    @classmethod
    def process(cls, request, **kwargs):
        instance = cls(HttpRequest(request), **kwargs)
        method_func = getattr(instance, '_process_' + request.method.lower())
        return method_func()


class CollectionNode(Node):
    range_unit = None
    max_limit = 200
    
    def __new__(cls, *args, **kwargs):
        cls.range_unit = cls.range_unit or cls.__name__ + 's' 
        return object.__new__(cls, *args, **kwargs)
        
    def _process_get(self, fields=[]):
        response = HttpResponse(self, content_type=self._matching_outputs[0])
        
        request_range = self.request.META.get('HTTP_RANGE')
        if not request_range:
            used_paging = True
            request_range = Range(self.range_unit, 0, self.max_limit)
            response['Accept-Range'] = self.range_unit
        
        items = self._call_http_method_handler(offset=request_range.offset,
                                              limit=request_range.limit)
        
        if not len(items):
            if used_paging:
                raise RequestedRangeNotSatisfiableError(self)
            response.status = 204
            return response
        
        response.status = 206 if used_paging else 200
        response.payload = [item.render_in_collection()
                            for item in items]
        return response


class ResourceNode(Node):
    def render_in_collection(self):
        return {'uri': self.build_url(absolute=True),
                'etag': self.get_etag()}