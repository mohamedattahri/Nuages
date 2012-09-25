# -*- coding: utf-8 -*-
import logging
import inspect
try:
    from django.conf.urls import url, patterns
except ImportError:
    #Deprecated, will be removed in Django 1.6
    from django.conf.urls.defaults import url, patterns 
from django.utils.importlib import import_module
from nuages.nodes import Node, NodeAlias


logger = logging.getLogger(__name__)


def __get_classes_from_module(module, cls):
    return [info[1] for info in inspect.getmembers(module, inspect.isclass)
            if info[1].__module__ == module.__name__ 
            and issubclass(info[1], cls)]
    
def __build_urls_for_node_type(source, cls, builder_fn):
    urls = []
    if inspect.isclass(source) and issubclass(source, NodeAlias):
        urls = [builder_fn(source)]
    elif inspect.ismodule(source):
        urls = map(builder_fn,
                   __get_classes_from_module(source, cls))
    elif type(source) == str:
        urls = map(builder_fn,
                   __get_classes_from_module(import_module(source), cls))
    else:
        raise Exception('%s must be a module or an %s class instance' % 
                        (str(source), cls.__name__))
        
    return patterns('', *filter(bool, urls))

def __build_alias_url(alias_cls):
    if not alias_cls.url:
        raise RuntimeError('Alias "%s" has no defined url pattern.' % 
                           alias_cls.__name__)
        
    return url(alias_cls.get_full_url_pattern(), alias_cls.process,
               name=alias_cls.get_view_name())
    
def __build_node_url(node_cls):
    if not node_cls.url:
        return
    
    if not len(node_cls.get_allowed_methods(implicits=False)):
        logger.warn('%s has none of the handlers required to define ' \
                    'the HTTP methods it supports' %
                    (node_cls.name or node_cls.__name__,))
    
    return url(node_cls.get_full_url_pattern(), node_cls.process,
               name=node_cls.get_view_name())
    
def build_urls(source):        
    return (__build_urls_for_node_type(source, Node, __build_node_url) +
            __build_urls_for_node_type(source, NodeAlias, __build_alias_url))
