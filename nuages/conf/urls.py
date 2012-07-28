# -*- coding: utf-8 -*-
import logging
import inspect
from django.conf.urls import url, patterns
from django.utils.importlib import import_module
from nuages.nodes import Node


logger = logging.getLogger(__name__)


def __get_nodes_from_module(module):
    return [info[1] for info in inspect.getmembers(module, inspect.isclass)
            if info[1].__module__ == module.__name__ 
            and issubclass(info[1], Node)]
    
def __build_node_url(node_cls):
    if not len(node_cls.get_allowed_methods(implicits=False)):
        logger.warn('%s has none of the handlers required to define ' \
                    'the HTTP methods it supports' %
                    (node_cls.name or node_cls.__name__,))
    
    if not node_cls.url:
        raise ValueError('\'uri\' attribute is required')
    
    return url(node_cls.get_full_url_pattern(), node_cls.process,
               name=node_cls.get_view_name())

def build_urls(source):
    urls = []
    if inspect.isclass(source) and issubclass(source, Node):
        urls = [__build_node_url(source)]
    elif inspect.ismodule(source):
        urls = map(__build_node_url, __get_nodes_from_module(source))
    elif type(source) == str:
        urls = map(__build_node_url,
                   __get_nodes_from_module(import_module(source)))
    else:
        raise Exception('%s must be a module or an HttpNode class instance' % 
                        str(source))
        
    return patterns('', *urls)
