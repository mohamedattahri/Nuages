# -*- coding: utf-8 -*-


def add_header_if_undefined(response, header, value):
    if header not in response:
        response[header] = value
        

def get_matching_mime_types(request, mimetypes):
    return list(set(mimetypes) &
                set(request.META.get('HTTP_ACCEPT', [])))