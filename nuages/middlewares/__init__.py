from datetime import timedelta
from django.http import Http404
from django.conf import settings
from django.utils.cache import patch_vary_headers
from nuages.utils import add_header_if_undefined, get_matching_mime_types
from nuages.utils import serialization
from nuages.http import (HttpRequest, HttpException, HttpResponse,
                         ETAG_WILDCARD, ForbiddenError,
                         MethodNotAllowedError, NotAcceptableError,
                         PreconditionFailedError, NotModifiedError)


DAY_DELTA = timedelta(days=1)


class RequestHandlerMiddleware():
    
    def __serialize(self, data, content_type):
        #TODO: implement a dynamic list of serialization engines
        if content_type in serialization.JSON_MIMETYPES:
            return serialization.to_json(data)
        elif content_type in serialization.XML_MIMETYPES:
            return serialization.to_xml(data)
        elif content_type in serialization.HTML_MIMETYPES:
            return serialization.to_html(data)
        else:
            raise NotAcceptableError(self)
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        '''Validates a request before it calls the appropriate processing
        method in the node.'''
        try:           
            node_cls = view_func.im_self
            request = HttpRequest(request)
        
            if not len(node_cls.get_allowed_methods(implicits=False)):
                raise Http404
            
            if request.method not in node_cls.get_allowed_methods():
                raise MethodNotAllowedError(node_cls)
            
            if request.method != 'OPTIONS':
                if not len(get_matching_mime_types(request, node_cls)):
                    raise NotAcceptableError(node_cls)
        except(HttpException), http_exception:
            return self.process_exception(request, http_exception)
        except AttributeError:
            pass
    
    def process_response(self, request, response):
        '''Completes the response with global headers that might have not
        been defined at the node level'''
        if (not issubclass(response.__class__, HttpResponse) or
            not response.node or 
            isinstance(response, HttpException) or
            request.method == 'OPTIONS'):
            return response
        
        try:
            node = response.node
            request = node.request
            etag = node.get_etag()
            last_modified = etag.last_modified
            
            if(request.META.get('HTTP_IF_MATCH', ETAG_WILDCARD) != etag or 
               request.META.get('HTTP_IF_UNMODIFIED_SINCE',
                                last_modified + DAY_DELTA) <= last_modified):
                raise PreconditionFailedError(self)
            
            if(request.META.get('HTTP_IF_NONE_MATCH') == etag or
                request.META.get('HTTP_IF_MODIFIED_SINCE',
                                 last_modified - DAY_DELTA) >= last_modified):
                raise NotModifiedError(self)
            
            add_header_if_undefined(response, 'Strict-Transport-Security',
                                    'max-age=99999999')
            patch_vary_headers(response, ['Accept'])
            
            #Content type adjustments
            content_type = response.get('Content-Type',
                                        settings.DEFAULT_CONTENT_TYPE)
            if '; charset' in content_type:
                response['Content-Type'] = ('%s; charset=%s' % 
                                            (content_type,
                                             settings.DEFAULT_CHARSET))
                                        
            response['Etag'] = etag
            response['Last-Modified'] = etag.last_modified
            response.content = self.__serialize(response.payload,
                                                content_type=content_type)
            
            return response
        except(HttpException), http_exception:
            return self.process_exception(request, http_exception)
        
    def process_exception(self, request, exception):
        '''Intercepts any exceptions raised by Nuages and turns it
        into a meaningful HTTP response.'''
        if issubclass(exception.__class__, HttpException):
            return exception
