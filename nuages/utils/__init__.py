# -*- coding: utf-8 -*-

def add_header_if_undefined(response, header, value):
    if header not in response:
        response[header] = value

def parse_accept_header(accept):
    """Parse the Accept header *accept*, returning a list with pairs of
    (media_type, q_value), ordered by q values.
    """
    result = []
    for media_range in accept.split(","):
        parts = media_range.split(";")
        media_type = parts.pop(0)
        media_params = []
        q = 1.0
        for part in parts:
            (key, value) = part.lstrip().split("=", 1)
            if key == "q":
                q = float(value)
            else:
                media_params.append((key, value))
        result.append((media_type, tuple(media_params), q))

    result.sort(lambda x, y: -cmp(x[2], y[2]))
    return [mime_type for (mime_type, _, __) in result]


def get_matching_mime_types(request, mimetypes):
    accept = request.META.get('HTTP_ACCEPT', "")
    if isinstance(accept, basestring):
        accept = parse_accept_header(accept)

    return list(set(mimetypes) & set(accept))
