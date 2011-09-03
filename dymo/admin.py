#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import logging
from django.db import models
from django.core.urlresolvers import clear_url_caches
from django.utils.importlib import import_module
from django.conf import settings
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType

logger = logging.getLogger('dymo')


def unregister_from_admin(admin_site, model=None, old_table_name=None):
    " Removes the dynamic model from the given admin site "

    if old_table_name is None and model is not None:
        old_table_name = model._meta.db_table

    # First deregister the current definition
    # This is done "manually" because model will be different
    # db_table is used to check for class equivalence.
    for reg_model in admin_site._registry.keys():
        if old_table_name == reg_model._meta.db_table:
            del admin_site._registry[reg_model]

    # Try the normal approach too
    if model is not None:
        try:
            admin_site.unregister(model)
        except NotRegistered:
            pass

    # Reload the URL conf and clear the URL cache
    # It's important to use the same string as ROOT_URLCONF
    reload(import_module(settings.ROOT_URLCONF))
    clear_url_caches()

    # logger.debug("Removed %r model from admin" % model.__name__)


def reregister_in_admin(admin_site, model, admin_class=None):
    " (re)registers a dynamic model in the given admin site "

    # We use our own unregister, to ensure that the correct
    # existing model is found 
    # (Django's unregister doesn't expect the model class to change)
    unregister_from_admin(admin_site, model)
    admin_site.register(model, admin_class)

    # Reload the URL conf and clear the URL cache
    # It's important to use the same string as ROOT_URLCONF
    reload(import_module(settings.ROOT_URLCONF))
    clear_url_caches()

    logger.debug("(Re-)Added %r model to admin" % model.__name__)

    # Add any missing permissions
    create_permissions(models.get_app(model._meta.app_label), created_models=[], verbosity=0)

    propogate_permissions(model)


def propogate_permissions(model):
    """ Grant dynamic model permissions to anyone who has them on the 
        parent model 
    """
    model_ct = ContentType.objects.get_for_model(model)
    required_permissions = Permission.objects.filter(content_type=model_ct)
    parent_ct = ContentType.objects.get_for_model(model._definition_model)
    parent_permissions = Permission.objects.filter(content_type=parent_ct)
    # Create a directory of users and groups who have certain permissions
    directory = {}
    for perm in parent_permissions:
        perm_type = perm.codename.split("_")[0]
        groups = set(perm.group_set.all().values_list('id', flat=True))
        users = set(perm.user_set.all().values_list('id', flat=True))
        directory[perm_type] = (groups, users)
    # Add any required permissions to relevant users and groups 
    for perm in required_permissions:
        perm_type = perm.codename.split("_")[0]
        groups = set(perm.group_set.all().values_list('id', flat=True))
        users = set(perm.user_set.all().values_list('id', flat=True))
        req_groups, req_users  = directory[perm_type]
        for group in Group.objects.filter(id__in=req_groups-groups):
            group.permissions.add(perm)
        for user in User.objects.filter(id__in=req_users-users):
            user.user_permissions.add(perm)

