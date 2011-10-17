#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from django.db.models.signals import class_prepared
from django.db.models.loading import cache as app_cache
from south.db import db


_dynamic_model_registry = {}

def register_dynamic_models(app_label, name, dependencies, get_models_fn):
    """ Register a class of dynamic models, by linking a function that returns
        an iterable of dynamic models. 
    """
    _dynamic_model_registry[name] = get_models_fn

    # Build all models as soon as possible
    when_classes_prepared(app_label, dependencies, get_models_fn)


def get_dynamic_models(*names):
    if not names:
        names = _dynamic_model_registry.keys()
    for name in names:
        for model in _dynamic_model_registry[name]():
            yield model


def when_classes_prepared(app_name, dependencies, fn):
    """ Runs the given function as soon as the model dependencies are available.
        You can use this to build dyanmic model classes on startup instead of
        runtime. 

        app_name       the name of the relevant app
        dependencies   a list of model names that need to have already been 
                       prepared before the dynamic classes can be built.
        fn             this will be called as soon as the all required models 
                       have been prepared

        NB: The fn will be called as soon as the last required
            model has been prepared. This can happen in the middle of reading
            your models.py file, before potentially referenced functions have
            been loaded. Becaue this function must be called before any 
            relevant model is defined, the only workaround is currently to 
            move the required functions before the dependencies are declared.

        TODO: Allow dependencies from other apps?
    """
    dependencies = [x.lower() for x in dependencies]

    def _class_prepared_handler(sender, **kwargs):
        """ Signal handler for class_prepared. 
            This will be run for every model, looking for the moment when all
            dependent models are prepared for the first time. It will then run
            the given function, only once.
        """
        sender_name = sender._meta.object_name.lower()
        already_prepared = set(app_cache.app_models.get(app_name,{}).keys() + [sender_name])

        if (sender._meta.app_label == app_name and sender_name in dependencies
          and all([x in already_prepared for x in dependencies])):
            db.start_transaction()
            try:
                fn()
            except DatabaseError:
                # If tables are  missing altogether, not much we can do
                # until syncdb/migrate is run. "The code must go on" in this 
                # case, without running our function completely. At least
                # database operations will be rolled back.
                db.rollback_transaction()
            else:
                db.commit_transaction()
                # TODO Now that the function has been run, should/can we 
                # disconnect this signal handler?
    
    # Connect the above handler to the class_prepared signal
    # NB: Although this signal is officially documented, the documentation
    # notes the following:
    #     "Django uses this signal internally; it's not generally used in 
    #      third-party applications."
    class_prepared.connect(_class_prepared_handler, weak=False)

