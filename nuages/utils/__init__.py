# -*- coding: utf-8 -*-


def add_header_if_undefined(response, header, value):
    if header not in response:
        response[header] = value
        

def get_matching_mime_types(request, node_class):
    return list(set(node_class.outputs) &
                set(request.META.get('HTTP_ACCEPT', [])))