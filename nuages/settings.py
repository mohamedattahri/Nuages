# -*- coding: utf-8 -*-
import os
from django.conf import settings


settings.TEMPLATE_DIRS = getattr(settings, 'TEMPLATE_DIRS', []) + [
    os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'),
]