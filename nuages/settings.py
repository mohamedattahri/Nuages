# -*- coding: utf-8 -*-
import os
from django.conf import settings


settings.MIDDLEWARE_CLASSES = getattr(settings, 'MIDDLEWARE_CLASSES', ()) + (
    'nuages.middlewares.RequestHandlerMiddleware',
)


settings.TEMPLATE_DIRS = getattr(settings, 'TEMPLATE_DIRS', []) + [
    os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'),
]