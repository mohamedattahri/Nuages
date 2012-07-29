# -*- coding: utf-8 -*-
from django.forms import Form
from django.utils.encoding import force_unicode


class Form(Form):
    def errors_as_text(self):
        lines = []
        for key, messages in self.errors.items():
            lines.append('%s: %s' % (key, ', '.join([force_unicode(msg) for
                                                     msg in messages])))
        return '\n'.join(lines)

    def get_first_error(self):
        for v in self.errors.values():
            return ';'.join([force_unicode(i) for i in v])