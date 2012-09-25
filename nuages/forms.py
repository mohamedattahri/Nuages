# -*- coding: utf-8 -*-
from django.forms import Form, fields
from django.forms import ValidationError
from django.utils.encoding import force_unicode


class UnexpectedFieldsError(Exception):
    def __init__(self, field_names):
        super(UnexpectedFieldsError, self).__init__('Unexpected field(s): %s' %
                                                    ', '.join(field_names))


class Form(Form):
    def __init__(self, data=None, strict=True, node=None, *args, **kwargs):
        super(Form, self).__init__(data=data, *args, **kwargs)
        self.node = node
        if strict:
            unexpected_fields = [key for key in data
                                 if key not in self.fields]
            if len(unexpected_fields):
                raise UnexpectedFieldsError(unexpected_fields)
    
    def errors_as_text(self):
        lines = []
        for key, messages in self.errors.items():
            lines.append('%s: %s' % (key, ', '.join([force_unicode(msg) for
                                                     msg in messages])))
        return '\n'.join(lines)

    def get_first_error(self):
        for v in self.errors.values():
            return ';'.join([force_unicode(i) for i in v])
            