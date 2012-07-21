# -*- coding: utf-8 -*-
try:
    from distutils.core import setup
except ImportError:
    from setuptools import setup

setup(
    name='nuages',
    packages=['nuages'],
    version=open('VERSION').read(),
    author=u'Greendizer',
    package_data={'nuages' : ['../VERSION']},
    install_requires=['django >= 1.4',],
    url='https://github.com/mohamedattahri/Nuages',
    license=open('LICENCE').read(),
    description='Django + REST',
    long_description=open('README.markdown').read(),
)
