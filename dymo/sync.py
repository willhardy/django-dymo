#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import logging
from django.db import models
from django.core.cache import cache
from django.db.models.loading import cache as app_cache

logger = logging.getLogger('dymo')


def get_cached_model(app_label, model_name, regenerate=False, local_hash=lambda i: i._hash):
    """ Return the locally cached model (from Django's model cache). 
        Returns None if there is no cached model, or if it is out of date.
    """

    # If this model has already been generated, we'll find it here
    previous_model = models.get_model(app_label, model_name)

    # Before returning our locally cached model, check that it is still current
    if previous_model is not None and not regenerate:
        CACHE_KEY = HASH_CACHE_TEMPLATE % (app_label, model_name)
        if cache.get(CACHE_KEY) != local_hash(previous_model):
            logging.debug("Local and shared dynamic model hashes are different: %s (local) %s (shared)" % (local_hash(previous_model), cache.get(CACHE_KEY)))
            regenerate = True
        
    # We can force regeneration by disregarding the previous model
    if regenerate:
        previous_model = None
        # Django keeps a cache of registered models, we need to make room for
        # our new one
        remove_from_model_cache(app_label, model_name)

    return previous_model


def remove_from_model_cache(app_label, model_name):
    """ Removes the given model from the model cache. """
    try:
        del app_cache.app_models[app_label][model_name.lower()]
    except KeyError:
        pass

def notify_model_change(model=None, app_label=None, object_name=None, invalidate_only=False, local_hash=lambda i: i._hash):
    """ Notifies other processes that a dynamic model has changed. 
        This should only ever be called after the required database changes have been made.
    """
    if model is not None:
        app_label = model._meta.app_label
        object_name = model._meta.object_name
    CACHE_KEY = HASH_CACHE_TEMPLATE % (app_label, object_name) 
    if invalidate_only:
        val = None
        #dynamic_model_changed.send(sender=None, app_label=app_label, object_name=object_name)
    elif model:
        val = local_hash(model)
        dynamic_model_changed.send(sender=model)

    cache.set(CACHE_KEY, val)

import django.dispatch
dynamic_model_changed = django.dispatch.Signal(providing_args=["sender", "app_label", "object_name"])


HASH_CACHE_TEMPLATE = 'dynamic_model_hash_%s-%s'

