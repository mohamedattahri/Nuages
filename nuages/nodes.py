# -*- coding: utf-8 -*-
import inspect
import urlparse
import hashlib
from django.conf import settings
from django.utils.importlib import import_module
from django.core.urlresolvers import reverse, resolve
from django.core.cache import cache
from nuages.forms import Form, UnexpectedFieldsError
from nuages.http import (HttpRequest, HttpResponse,
                         ETAG_WILDCARD, ForbiddenError, InvalidRequestError,
                         RequestedRangeNotSatisfiableError,
                         UnsupportedMediaTypeError,
                         MethodNotAllowedError)
from nuages.utils import get_matching_mime_types, doc


__all__ = ('Node', 'CollectionNode', 'ResourceNode', 'NodeAlias',
           'parseQueryString', 'parseBody')

'''
Django settings:
#NUAGES_API_ENDPOINT
#NUAGES_MAX_COLLECTION_SIZE
'''
API_ENDPOINT = urlparse.urlparse(getattr(settings, 'NUAGES_API_ENDPOINT', ''))
MAX_COLLECTION_SIZE = getattr(settings, 'NUAGES_MAX_COLLECTION_SIZE', 1000)
IDEMPOTENT_METHODS = ['GET', 'HEAD', 'OPTIONS']
RESOURCE_HTTP_METHODS_HANDLERS = {  'HEAD'     : 'retrieve',
                                    'GET'      : 'retrieve',
                                    'PUT'      : 'replace',
                                    'PATCH'    : 'modify',
                                    'DELETE'   : 'delete', }
COLLECTION_HTTP_METHODS_HANDLER = { 'HEAD'     : 'list',
                                    'GET'      : 'list',
                                    'POST'     : 'add',
                                    'PUT'      : 'replace',
                                    'PATCH'    : 'modify',
                                    'DELETE'   : 'delete', }
FORM_URL_ENCODED = 'application/x-www-form-urlencoded'


class Node(object):
    label= None
    url = None
    name = None
    parent = None
    secure = False
    method_handlers = None
    _parent_instance = None
    _post_mortem_etag = None
    outputs = ['application/json', 'application/xml',
               'application/xml+xhtml', 'text/html', '*/*']
    
    def __new__(cls, *args, **kwargs):
        hasher = hashlib.sha1()
        map(hasher.update, [cls.get_full_url_pattern(),
                          ''.join(map(str, args)),
                          str(kwargs)])
        key = hasher.hexdigest()
        cached = cache.get(key)
        if cached:
            return cached
        
        cls.label = cls.label or cls.__name__.lower()
        cls.outputs = set([settings.DEFAULT_CONTENT_TYPE if c == '*/*' else c
                       for c in cls.outputs])
        instance = object.__new__(cls, *args, **kwargs)
        cache.set(key, instance)
        return instance
    
    def __init__(self, request, *args, **kwargs):
        '''Initializes a new instance of the Node class:
         
        - request: Current HttpRequest instance.
        - *args, **kwargs are passed all the way to the top parent node.'''
        self.request = request
        members = filter(lambda x: x not in ['self', 'request'],
                         inspect.getargspec(self.__init__)[0])
        self.__locals = dict(zip(members, args))
        map(lambda t: setattr(self, t[0], t[1]), self.__locals.items())
        
        kwargs.update(self.__locals)
        self._chained_args = kwargs
        
        if self.parent:
            self._parent_instance = self.parent(request, **self._chained_args)
            
        self._try_cross()
            
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
    
    def _try_handle_request(self):
        if self.request.method == 'OPTIONS':
            return True
        
        func_name = ('_can_%s' %
                     self.method_handlers[self.request.method])

        if hasattr(self, func_name):
            if not getattr(self, func_name)():
                raise ForbiddenError(self,
                                     'Access to resource has been denied.')
            return 
        
        if self.request.method.upper() in IDEMPOTENT_METHODS:
            return self._try_read()
        
        return self._try_write()
    
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
        
        secure = self.secure or self.request.is_secure()
        return urlparse.urlunparse(('https' if secure else 'http',
                                    API_ENDPOINT[1] or self.request.get_host(),
                                    relative, None, None, None))

    def get_etag(self):
        '''Gets the ETag of the current node.'''
        return self._post_mortem_etag or ETAG_WILDCARD
    
    def render_in_parent(self):
        '''Defines how the reference to the current node in rendered in its
        parent node
        
        Returns a dict'''
        return {self.label: self.build_url(absolute=True)}
    
    def render_in_collection(self):
        '''Determines how the current node in rendered inside a collection of 
        nodes'''
        return {'uri': self.build_url(absolute=True)}
    
    def _call_http_method_handler(self, method=None, *args, **kwargs):
        handler = getattr(
          self,
          self.method_handlers[method or self.request.method.upper()]
        )
        return handler(*args, **kwargs)
    
    def _process_get(self):
        response = HttpResponse(node=self,
                                content_type=self._matching_outputs[0])
        data = self._call_http_method_handler(method='GET')
        
        for node_cls in self.__class__.get_children_nodes():
            try:
                child_node = node_cls(self.request, **self._chained_args)
                data.update(child_node.render_in_parent())
            except ForbiddenError:
                continue
            
        response.payload = data    
        return response
    
    def _process_patch(self):
        '''If not exception is raised, the resource is serialized and included
        in the body of the response'''
        if self._call_http_method_handler() is False:
            return HttpResponse(node=self, status=204)
        return self._process_get()
    
    def _process_put(self):
        self._call_http_method_handler()
    
    def _process_delete(self):
        '''The handler should return a boolean specifying whether the deleted
        resource should be included in the body of the response'''
        self._post_mortem_etag = self.get_etag()
        if self._call_http_method_handler() is False:
            return HttpResponse(node=self, status=204)
        return self._process_get() 
    
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
        response.content = self.__class__.generate_doc()
        return response
    
    @classmethod
    def generate_doc(cls):
        allowed = cls.get_allowed_methods(implicits=False)
        node_doc = doc.Node(name=cls.label,
                            url_regex=cls.get_full_url_pattern(),
                            accept=cls.outputs)
        for i, handler_func in enumerate([getattr(cls,
                                                  cls.method_handlers[m])
                                          for m in allowed]):
            qstr_deco = handler_func.func_dict.get(parseQueryString.__name__)
            qstr_form = qstr_deco.form_cls if qstr_deco else None
            body_deco = handler_func.func_dict.get(parseBody.__name__)
            body_form = body_deco.form_cls if body_deco else None
            method_doc = doc.Method(verb=allowed[i],
                                    description=handler_func.__doc__,
                                    queryString_form=qstr_form,
                                    body_form=body_form,
                                    content_types=(body_deco.content_types if
                                                   body_deco else []))
            node_doc.methods.append(method_doc)
        return str(node_doc)
    
    @classmethod
    def get_children_nodes(cls):
        root_urlconf = import_module(settings.ROOT_URLCONF)
        return [url.callback.im_self for url in root_urlconf.urlpatterns
                if hasattr(url.callback, 'im_self') and
                hasattr(url.callback.im_self, 'parent') and
                url.callback.im_self.parent and
                issubclass(url.callback.im_self.parent, cls)]
        
    @classmethod
    def get_full_url_pattern(cls):
        if not cls.parent:
            return cls.url
        
        if not issubclass(cls.parent, Node):
            raise ValueError('\'parent\' must be an instance of Node class.')
        
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
        return [method for method, handler in cls.method_handlers.items()
                if hasattr(cls, handler)] + implicit_methods
                
    @classmethod
    def process(cls, request, **kwargs):
        instance = cls(HttpRequest(request), **kwargs)
        instance._try_handle_request()
        method_func = getattr(instance,
                              '_process_' + instance.request.method.lower())
        return method_func()


class CollectionNode(Node):
    label = None
    range_unit = None
    max_limit = MAX_COLLECTION_SIZE
    method_handlers = COLLECTION_HTTP_METHODS_HANDLER
    
    def __new__(cls, *args, **kwargs):
        cls.range_unit = cls.range_unit or cls.__name__ + 's'
        cls.label = cls.label or cls.range_unit
        return Node.__new__(cls, *args, **kwargs)
    
    def _call_http_method_handler(self, *args, **kwargs):
        handler = getattr(self,
                          self.method_handlers[self.request.method.upper()])
        return handler(*args, **kwargs)
    
    def _process_get(self, fields=[]):
        response = HttpResponse(self, content_type=self._matching_outputs[0])
        
        request_range = self.request.META.get('HTTP_RANGE')
        kwparams = {}
        if not request_range:
            response['Accept-Range'] = self.range_unit
        else:
            kwparams = {'offset': request_range.offset,
                        'limit' : request_range.limit}    
        items = self._call_http_method_handler(**kwparams)
        if items is None:
            raise ValueError('%s() method of node %s returned None.' % 
                             (self.method_handlers.get(self.request.method),
                              self.__class__.__name__))
        
        if not len(items) and request_range: 
            raise RequestedRangeNotSatisfiableError(self)
        
        response.payload = []
        for item in items:
            try:
                response.payload.append(item.render_in_collection())
            except ForbiddenError:
                pass
        
        if not len(response.payload):
            response.status = 204
        elif request_range:
            response.status = 206 
        else:
            response.status = 200
            
        return response

    def _process_post(self):
        '''Redirects the client to the Node returne by the handler.'''
        created_node = self._call_http_method_handler()
        response = HttpResponse(self, 302)
        response['Location'] = created_node.build_url()
        return response


class ResourceNode(Node):
    method_handlers = RESOURCE_HTTP_METHODS_HANDLERS
    
    def render_in_collection(self):
        payload = super(ResourceNode, self).render_in_collection()
        if payload:
            payload.update({'uri': self.build_url(absolute=True),
                            'etag': str(self.get_etag())})
        return payload
    
    
    
    
class NodeAlias(object):
    '''Represents a node that's an alias with a different URL pattern to
    another node'''
    parent = None
    url = None
    name = ''
    permanent = True
    
    def __init__(self, request, **kwargs):
        self.request = request
        if self.parent:
            self._parent_instance = self.parent(request, **kwargs)
            
    def get_canonical_node(self, **kwargs):
        raise NotImplementedError
    
    @classmethod
    def get_view_name(cls):
        return  (cls.name or
                 cls.__module__.replace('.', '_') + '_alias_' + cls.__name__) 
    
    @classmethod
    def get_full_url_pattern(cls):
        if not cls.parent:
            return cls.url
        
        if not issubclass(cls.parent, Node):
            raise ValueError('\'parent\' must be an instance of the Node class')
        
        return (cls.parent.get_full_url_pattern().rstrip('$') +
                cls.url.lstrip('^'))
        
    @classmethod
    def get_allowed_methods(cls, implicits=True):
        implicit_methods = ['HEAD', 'OPTIONS'] if implicits else []
        return ['GET'] + implicit_methods
    
    @classmethod
    def process(cls, request, **kwargs):
        if request.method not in cls.get_allowed_methods():
            raise MethodNotAllowedError(cls)
        
        response = HttpResponse(status=301 if cls.permanent else 302)
        response['Location'] = (cls(request, **kwargs)
                                .get_canonical_node(**kwargs)
                                .build_url())
        return response
        


class parseData(object):
    '''Decorates Node handler methods and allows incoming data to be parsed
    and validated using a Form.
    
    Decorated Node handler method is called with mandatory parameters as args,
    and optional ones as kwargs'''
    def __init__(self, form_cls):
        if not issubclass(form_cls, Form):
            raise ValueError('\'form_cls\' must be a subclass of ' \
                             'nuages.forms.Form')
            
        self.form_cls = form_cls
        
    def __call__(self, fn):
        if (fn.func_name not in RESOURCE_HTTP_METHODS_HANDLERS.values() and
            fn.func_name not in COLLECTION_HTTP_METHODS_HANDLER.values()):
            assert False, fn.func_name
            raise RuntimeError('%s can only decorate Node handler methods' %
                               self.__class__.__name__)
        
        def wrapped_fn(*args, **kwargs):
            required, optional = self.parse(args[0])
            args += required
            kwargs.update(optional)
            return fn(*args, **kwargs)
        wrapped_fn.func_dict[self.__class__.__name__] = self
        return wrapped_fn
    
    def get_fields(self, form):
        required, optional = (), {}
        for key, field in form.fields.items():
            if field.required:
                required += (form.cleaned_data.get(key),)
            else:
                optional[key] = form.cleaned_data.get(key)
        return required, optional
        
    def parse(self, node):
        return (), {}


class parseQueryString(parseData):
    '''Added as a decorator, parses data from the query string and 
    validates it using the submitted Form instance.'''
    def parse(self, node):
        try:
            form = self.form_cls(node.request.GET, node=node)
            if not form.is_valid():
                raise InvalidRequestError(description=form.errors_as_text())
            return self.get_fields(form)
        except UnexpectedFieldsError, e:
            raise InvalidRequestError(description=str(e))


class parseBody(parseData):
    '''Added as a decorator, takes the data in the body of the request,
    checks if it came in a supported format, validates it using the submitted
    Form instance, and passes it as required and optional parameters to the
    handler method. 
    
    Can only decorate handlers of POST, PUT and PATCH methods.
    
    Non url-encoded data is passed \'as is\' in the 'payload' attribute.
    '''
    def __init__(self, form_cls, content_types=[FORM_URL_ENCODED]):
        self.content_types = content_types
        super(parseBody, self).__init__(form_cls)
        
    def parse(self, node):
        if node.request.method in ['OPTIONS', 'HEAD', 'GET', 'DELETE']:
            raise RuntimeError('Invalid %s decorator. %s ' \
                               'methods can\'t carry data in their bodies.' %
                               (self.__class__.__name__, node.request.method))
            
        request_content_type = node.request.META.get('CONTENT_TYPE')
        if (node.request.META.get('CONTENT_LENGTH', 0) and
            request_content_type not in self.content_types):
            raise UnsupportedMediaTypeError
            
        if (request_content_type != FORM_URL_ENCODED):
            return (), {'payload': node.request.raw_post_data}
        
        try:    
            form = self.form_cls(node.request.POST, node=node)
            if not form.is_valid():
                raise InvalidRequestError(description=form.errors_as_text())
            return self.get_fields(form)
        except UnexpectedFieldsError, e:
            raise InvalidRequestError(description=str(e))