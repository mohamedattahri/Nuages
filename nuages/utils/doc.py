# -*- coding: utf-8 -*-


__all__ = ('EndPoint', 'Node', 'Method', 'QueryStringParameter',
           'BodyParameter')


class DocElement(object):
    pass


class EndPoint(DocElement):
    def __init__(self, url):
        self.url = url
        self.nodes = []


class Node(DocElement):
    def __init__(self, name, url_regex, accept):
        self.name = name
        self.url_regex = url_regex
        self.accept = accept
        self.methods = []


class Method(DocElement):
    def __init__(self, verb, description='', queryString_form=None,
                 body_form=None, content_types=[]):
        self.verb = verb
        self.description = ''
        self.required_parameters = []
        self.optional_parameters = []
        

class QueryStringParameter(DocElement):
    pass


class BodyParameter(DocElement):
    pass