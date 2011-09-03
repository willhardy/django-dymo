#!/usr/bin/env python2.5
# -*- coding: UTF-8 -*-

try:
    import ez_setup
    ez_setup.use_setuptools()
except ImportError:
    pass

from setuptools import setup, find_packages

setup(
    name = "Django-DyMo",
    version = '0.1',
    packages = find_packages(),
    install_requires = ['django>=1.3'],
    author = "Will Hardy",
    author_email = "django-dymo@willhardy.com.au",
    description = "A framework for managing dynamic models with Django.",
    long_description = open('README.rst').read(),
    license = "LICENSE",
    keywords = "django, framework, dynamic models",
    url = "https://github.com/willhardy/django-dymo",
    include_package_data = True,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Framework :: Django",
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Topic :: Software Development"
    ],
)

