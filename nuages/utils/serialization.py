# -*- coding: utf-8 -*-
import re
import json


__all__ = ('to_json', 'to_xml', 'to_html', 'XmlSerializer', 'JSON_MIMETYPES',
           'XML_MIMETYPES')


JSON_MIMETYPES = ['application/json', 'text/javascript']
XML_MIMETYPES = ['application/xml', 'text/xml']
HTML_MIMETYPES = ['application/xhtml+xml', 'text/html']


from datetime import datetime, date
from nuages.http import datetime_to_timestamp


class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime) or isinstance(obj, date):
            return datetime_to_timestamp(obj)
        return json.JSONEncoder.default(self, obj)


def to_json(data):
    return json.dumps(data, cls=CustomEncoder)


def to_xml(data):
    pass


def to_html(data):
    html = '<!DOCTYPE html><html><head></head><body><ul>'
    entities = data if not type(data) is dict else [data]
    for entity in entities:
        html += '<li><ul>'    
        for k, v in entity.items():
            try:
                if re.match(r'^\w+:\/\/.+$', v):
                    v = '<a href="%s">%s</a>' % (v, v)
            except:
                pass
            html += '<li>%s: %s</li>' % (k, v)
        html += '</ul></li>'
    html += '</ul></body></html>'
    return html