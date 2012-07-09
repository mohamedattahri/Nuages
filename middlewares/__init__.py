from nuages.http import HttpException, HttpResponse


class RequestHandlerMiddleware():
#    def process_request(self, request):
#        ''''''
#        pass
#    
#    def process_view(self, request, view_func, view_args, view_kwargs):
#        ''''''
#        pass
#    
#    def process_response(self, request, response):
#        ''''''
#        return response
    
    def process_exception(self, request, exception):
        ''''''
        if not issubclass(exception.__class__, HttpException):
            return
        
        node = exception.node
        response = HttpResponse(request, status=exception.status)
        
        if response.status_code == 405: #Method Not Allowed
            response['Allow'] = 'OPTIONS,' + ','.join(node.allows)
            
        return response