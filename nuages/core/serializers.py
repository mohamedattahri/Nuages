# -*- coding: utf-8 -*-
import json


__all__ = ('to_json', 'to_xml')


from datetime import datetime, date, time


class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime) or isinstance(obj, date):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)


def to_json(data):
    return json.dumps(data, cls=CustomEncoder)


def to_xml(data):
    raise NotImplementedError('XML Serialization has yet to be implemented.')
