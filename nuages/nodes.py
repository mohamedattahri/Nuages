# -*- coding: utf-8 -*-
import inspect
import urlparse
from django.conf import settings
from django.utils.importlib import import_module
from django.core.urlresolvers import reverse, resolve
from nuages.http import (HttpRequest, HttpResponse, InvalidRequestError,
                         ForbiddenError, NotModifiedError, ETAG_WILDCARD,
                         Range)
from nuages.utils import serialization


__all__ = ('Node', 'CollectionNode', 'ResourceNode')


API_ENDPOINT = urlparse.urlparse(settings.NUAGES_API_ENDPOINT
                                 if hasattr(settings, 'NUAGES_API_ENDPOINT')
                                 else '')


class Node(object):
    ''''''
    uri = None
    name = None
    parent = None
    secure = False
    range_unit = ('resource', 'resources')
    max_limit = 200
    outputs = ['application/json', 'application/xml',
               'application/xhtml+xml', 'text/html', '*/*']
    allow = ['GET']
    __implicit_methods = ['OPTIONS', 'HEAD']
    _parent_instance = None
    
    def __new__(cls, *args, **kwargs):
        cls.outputs = [settings.DEFAULT_CONTENT_TYPE if c == '*/*' else c
                       for c in cls.outputs]
        return object.__new__(cls, *args, **kwargs)
    
    def __init__(self, request, *args, **kwargs):
        values = locals().get('args', tuple())
        
        self._try_cross()
        
        if self.parent:
            self._parent_instance = self.parent(request, **kwargs)
            
        self.__locals = {}
        members = filter(lambda x: x not in ['self', 'request'],
                         inspect.getargspec(self.__init__)[0])
        for index, name in enumerate(members):
            self.__locals.update({name: values[index]})
            setattr(self, name, values[index])
                
        self.request = request
        
        if self.parent:
            self._parent_instance = self.parent(request, **kwargs)
        
        if request.method not in (self.allow + self.__implicit_methods):
            raise InvalidRequestError(self, 405) #Method not allowed
        
        if request.method != 'OPTIONS':
            self._matching_outputs = list(set(self.outputs) &
                                          set(request.META.get('HTTP_ACCEPT',
                                                                [])))
            if not len(self._matching_outputs):
                raise InvalidRequestError(self, 406) #Not acceptable
    
    def _can_cross(self):
        return True
        
    def _can_read(self):
        return False
    
    def _can_write(self):
        return False
    
    def _try_cross(self):
        if not self._can_cross():
            raise ForbiddenError(self, 'Access to resource has been denied.')
    
    def _try_read(self):
        if not self._can_read():
            raise ForbiddenError(self, 'Access to resource has been denied.')    
    
    def _try_write(self):
        if not self._can_write():
            raise ForbiddenError(self, 'Access to resource has been denied.')
    
    def build_uri(self, absolute=True):
        self._try_read() #You don't need the URI of a resource you can't see.
        
        kwargs = self.__locals
        if self.parent:
            parent_uri = self._parent_instance.build_uri(absolute=False)
            kwargs.update(resolve(parent_uri)[2])

        relative = reverse(self.__class__.get_view_name(), kwargs=kwargs)
        if not absolute:
            return relative
        
        return urlparse.urlunparse(('https' if self.secure else 'http',
                                    API_ENDPOINT[1] or self.request.get_host(),
                                    relative,
                                    None,
                                    None,
                                    None))

    @property
    def etag(self):
        #FIXME: Change this to different default value.
        return ETAG_WILDCARD
    
    @property
    def last_modified(self):
        return self.etag.last_modified
    
    def _get(self, *args):
        '''
        GET method documentation.
        '''       
        if ((self.request.META.get('HTTP_IF_MATCH', ETAG_WILDCARD) is not 
             self.etag) or
            self.request.META.get('HTTP_IF_NONE_MATCH') is self.etag):
            raise InvalidRequestError(self, 412) #Precondition Failed
        
        if (self.request.META.get('HTTP_IF_MODIFIED_SINCE') < self.etag or
            self.request.META.get('HTTP_IF_UNMODIFIED_SINCE') > self.etag):
            raise NotModifiedError(self, 304) #Not modified
        
        response = HttpResponse(self, 200)
        response['Content-Type'] = self._matching_outputs[0]
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
        if self.request['HTTP_IF_MATCH'] is self.etag:
            raise InvalidRequestError(self, 409) #Conflict
        
        return HttpResponse(self.request, self)
    
    def _put(self, *args, **kwargs):
        '''
        PUT method documentation.
        '''
        raise NotImplementedError()
    
    def _delete(self, *args, **kwargs):
        '''
        DELETE method documentation.
        '''
        raise NotImplementedError()
    
    def _head(self, *args, **kwargs):
        response = self._get(*args, **kwargs)
        response.content = ''
        return response
    
    def _options(self, *args, **kwargs):
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
        response['Allow'] = ','.join(map(lambda x: x.upper(), self.allow))
        
        #TODO: Format the output in something people can use.        
        docs = filter(bool, [getattr(self, '_' + method.lower()).__doc__ 
                             for method in self.allow])
        response.content = '\n'.join(docs)
        return response
    
    def to_dict(self):
        raise NotImplementedError()
    
    def serialize(self, fields=[], mime_type=None):
        self._try_read()
        
        mime_type = mime_type or self._matching_outputs[0]
        data = dict([(k, v) for k,v in self.to_dict().items()
                     if k not in fields])
        for node in self.__class__.get_children_nodes():
            try:
                data.update({node.range_unit[1]:
                             node(self.request, **self.__locals).build_uri()})
            except ForbiddenError:
                continue
                
        map(data.pop, fields)
        
        #TODO: implement a dynamic list of serialization engines
        if mime_type in serialization.JSON_MIMETYPES:
            return serialization.to_json(data)
        elif mime_type in serialization.XML_MIMETYPES:
            return serialization.to_xml(data)
        elif mime_type in serialization.HTML_MIMETYPES:
            return serialization.to_html(data)
        else:
            raise NotImplementedError()
        
    def __repr__(self):
        try:
            return self.serialize(mime_type=(self._matching_outputs[0] 
                                             if len(self._matching_outputs)
                                             else 'application/json'))
        except:
            return repr(super(Node, self))
        
    @classmethod
    def get_children_nodes(cls):
        root_urlconf = import_module(settings.ROOT_URLCONF)
        return [url.callback.im_self for url in root_urlconf.urlpatterns
                if url.callback.im_self.parent and
                issubclass(url.callback.im_self.parent, cls) ]
        
    @classmethod
    def get_full_pattern(cls):
        if not cls.parent:
            return cls.uri
        
        if not issubclass(cls.parent, Node):
            raise ValueError('\'parent\' must be an instance of HttpNode')
        
        return cls.parent.get_full_pattern().rstrip('$') + cls.uri.lstrip('^')
    
    @classmethod
    def get_view_name(cls):
        if cls.name:
            return cls.name
        
        return cls.__module__.replace('.', '_') + '_' + cls.__name__
        
    @classmethod
    def process(cls, request, *args, **kwargs):
        instance = cls(HttpRequest(request), **kwargs)
        method_func = getattr(instance, '_' + request.method.lower())
        return method_func()


class CollectionNode(Node):
    allow = ['GET', 'POST']
    
    def fetch(self, query=None, offset=0, limit=200):
        if limit > self.max_limit:
            raise InvalidRequestError(self, 413) #Request Entity Too Large
        
        result = []
        if not len(result):
            raise InvalidRequestError(self, 416)    #Requested Range Not
                                                    #Satisfiable
        
        return result
    
    def _get(self, query='', *args):
        response = super(CollectionNode, self)._get()
        
        request_range = self.request.META.get('HTTP_RANGE')
        if not request_range:
            request_range = Range(self.range_unit[1], 0, 200)
            response['Accept-Range'] = self.range_unit[1]
                    
        response.content = self.fetch(query=filter, offset=request_range.offset,
                                      limit=request_range.limit)
        return response


class ResourceNode(Node):
    allow = ['GET', 'PATCH']
    
    def _get(self, *args, **kwargs):
        '''Hello, this is a get function'''
        response = super(ResourceNode, self)._get()
        response.content = self.serialize(mime_type=self._matching_outputs[0])
        return response