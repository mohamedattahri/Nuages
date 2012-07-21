# -*- coding: utf-8 -*-
import json


__all__ = ('to_json', 'to_xml', 'to_html', 'XmlSerializer', 'JSON_MIMETYPES',
           'XML_MIMETYPES')


JSON_MIMETYPES = ['application/json', 'text/javascript']
XML_MIMETYPES = ['application/xml', 'text/xml']
HTML_MIMETYPES = ['application/xhtml+xml', 'text/html']


def to_json(data):
    return json.dumps(data)


def to_xml(data):
    pass


def to_html(data):
    return ('<!DOCTYPE html><html><head></head><body><ul>%s</ul></body></html>'
            % ''.join(['<li>%s: %s</li>' % (k, v) for k, v in data.items()]))
    
