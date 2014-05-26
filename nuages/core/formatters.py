# -*- coding: utf-8 -*-
from django.conf import settings
from django.template import loader, Context
from nuages.core import serializers
from nuages.utils import get_matching_mime_types
from nuages.http import NotAcceptableError


HTTP_ERROR_FORMATS = ['application/json', 'application/xml', 'text/html',
                      'text/javascript', 'text/xml', '*/*']
JSON_MIMETYPES = ['application/json', 'text/javascript']
XML_MIMETYPES = ['application/xml', 'text/xml']
HTML_MIMETYPES = ['application/xhtml+xml', 'text/html']


class ResponseFormatter(object):
    def __init__(self, request, response):
        self.request = request
        self.response = response

    def html(self, data, template_name=None):
        if not template_name:
            raise NotImplementedError

        template = loader.get_template("nuages_%s.html" % template_name)
        data.update({
            'response': self.response,
        })
        return template.render(Context(data))

    def json(self, data):
        return serializers.to_json(data)

    def xml(self, data):
        return serializers.to_xml(data)

    def format(self):
        content_type = settings.DEFAULT_CONTENT_TYPE
        data = self.response.payload

        # if self.response.node and len(self.response.node.outputs):
        matching_types = get_matching_mime_types(self.request,
                                                 HTTP_ERROR_FORMATS)

        if len(matching_types):
            content_type = matching_types[0]


        self.response['Content-Type'] = content_type

        if content_type in JSON_MIMETYPES:
            self.response.content = self.json(data)
        elif content_type in XML_MIMETYPES:
            self.response.content = self.xml(data)
        elif content_type in HTML_MIMETYPES:
            self.response.content = self.html(data)
        else:
            raise NotAcceptableError(self.response.node)


class ApiResponseFormatter(ResponseFormatter):
    def html(self, data):
        return super(self.__class__, self).html(data, template_name="response")


class ErrorResponseFormatter(ResponseFormatter):
    def html(self, data):
        return super(self.__class__, self).html(data, template_name="error")
