from datetime import timedelta
from django.http import Http404
from django.conf import settings
from django.utils.cache import patch_vary_headers
from nuages.utils import add_header_if_undefined
from nuages.core.formatters import ApiResponseFormatter, ErrorResponseFormatter
from nuages.nodes import get_method_handlers, get_matching_mime_types_for_node
from nuages.http import (HttpRequest, HttpError, HttpResponse,
                         ETAG_WILDCARD, ForbiddenError, NotModifiedError,
                         MethodNotAllowedError,PreconditionFailedError,
                         NotAcceptableError,)


DAY_DELTA = timedelta(days=1)


class RequestHandlerMiddleware():

    def process_view(self, request, view_func, view_args, view_kwargs):
        '''Validates a request before it calls the appropriate processing
        method in the node.'''
        try:
            node_cls = view_func.im_self
            request = HttpRequest(request)

            if not len(node_cls.get_allowed_methods(implicits=False)):
                if settings.DEBUG:
                    names = set(get_method_handlers(node_cls).values())
                    raise RuntimeError('%s has no instance methods (%s) to ' \
                                       'process HTTP requests.' %
                                       (node_cls.__name__, ', '.join(names)))

                #404 seems to be the most reasonable choice
                raise Http404

            if request.method not in node_cls.get_allowed_methods():
                raise MethodNotAllowedError()

            if (request.method != 'OPTIONS' and
                not len(get_matching_mime_types_for_node(request, node_cls))):
                    raise NotAcceptableError(node_cls)

        except(HttpError), http_exception:
            return self.process_exception(request, http_exception)
        except AttributeError:
            pass

    def process_response(self, request, response):
        '''Completes the response with global headers that might have not
        been defined at the node level'''
        if (not issubclass(response.__class__, HttpResponse) or
            not response.node or
            isinstance(response, HttpError) or
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

            if request.is_secure():
                add_header_if_undefined(response, 'Strict-Transport-Security',
                                        'max-age=99999999')

            patch_vary_headers(response, ['Accept'])

            response['Etag'] = etag
            response['Last-Modified'] = etag.last_modified

            if request.method != 'HEAD' and response.payload:
                ApiResponseFormatter(request, response).format()

            return response
        except(HttpError), http_exception:
            return self.process_exception(request, http_exception)

    def process_exception(self, request, exception):
        '''Intercepts any exceptions raised by Nuages and turns it
        into a meaningful HTTP response.'''
        if isinstance(exception, HttpError):
            ErrorResponseFormatter(request, exception).format()
            return exception
