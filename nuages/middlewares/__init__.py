from django.utils.cache import patch_vary_headers
from nuages.utils import add_header_if_undefined, get_matching_mime_types
from nuages.http import (HttpRequest, HttpException, HttpResponse,
                         MethodNotAllowedError, NotAcceptableError)


class RequestHandlerMiddleware():
    def process_view(self, request, view_func, view_args, view_kwargs):
        '''Validates a request before it calls the appropriate processing
        method in the node.'''
        try:
            request = HttpRequest(request)
            node_cls = view_func.im_self
            
            if request.method not in (node_cls.allow + ['OPTIONS', 'HEAD']):
                raise MethodNotAllowedError(node_cls)
        
            if request.method != 'OPTIONS':
                if not len(get_matching_mime_types(request, node_cls)):
                    raise NotAcceptableError(node_cls)
        except(HttpException), http_exception:
            return self.process_exception(request, http_exception)
    
    def process_response(self, request, response):
        '''Completes the response with global headers that might have not
        been defined at the node level'''
        add_header_if_undefined(response, 'Strict-Transport-Security',
                                'max-age=99999999')
        
        if not isinstance(response, HttpException):
            patch_vary_headers(response, ['accept'])
        
        return response
    
    def process_exception(self, request, exception):
        '''Intercepts any exceptions raised by Nuages and turns it
        into a meaningful HTTP response.'''
        if issubclass(exception.__class__, HttpException):
            return exception