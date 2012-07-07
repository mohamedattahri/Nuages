# -*- coding: utf-8 -*-
import inspect
from django.conf.urls import patterns, url
#from django.utils.importlib import import_module
from nuages.nodes import HttpNode


def __get_nodes_from_module(module):
    ''''''
    return [info[1] for info in inspect.getmembers(module)
            if inspect.isclass(info[1]) and isinstance(info[1], HttpNode)]
    
    
def __build_node_url(node):
    ''''''
    if not node.uri:
        raise ValueError('\'uri\' attribute is required')
    
    if node.parent:
        if not isinstance(node.parent, HttpNode):
            raise ValueError('\'parent\' must be an instance of HttpNode')
        node.uri = node.parent.uri.rstrip('$') + node.uri.lstrip('^')
        
    return url(node.uri, node.handle, name=node.name)


def build_urls(source):
    ''''''
    urls = []
    if isinstance(source, HttpNode):
        urls = [__build_node_url(source)]
    elif inspect.ismodule(source):
        urls = map(__build_node_url, __get_nodes_from_module(source))
    else:
        raise Exception('%s must be a module or an HttpNode class instance' %
                        str(source))
        
    return patterns('', *urls)