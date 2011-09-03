#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from django.db import connection, DatabaseError
from django.db import models
from django.contrib.admin.sites import NotRegistered
from django.db.models.signals import class_prepared
from django.db.models.loading import cache as app_cache
from django.core.urlresolvers import clear_url_caches
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.utils.importlib import import_module
from django.core.cache import cache
from django.conf import settings
from django.db.models import get_app
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext as _

import logging
from south.db import db

logger = logging.getLogger('dymo')

# Keys belonging to the model, cannot be field names
# Some are more likely than others
RESERVED_ATTRIBUTES = (
    models.Model.__dict__.keys()   # Model class methods, attributes
    + ['objects', '_base_manager'] # Added by manager
    + ['MultipleObjectsReturned', 'DoesNotExist'] # Added by base
    + ['_order', 'id', '_meta', 'pk'] # Added by options
    )


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
    create_permissions(get_app(model._meta.app_label), created_models=[], verbosity=0)

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

def create_db_table(model_class):
    """ Takes a Django model class and create a database table, if necessary.
    """
    # XXX Create related tables for ManyToMany etc

    db.start_transaction()
    table_name = model_class._meta.db_table

    # Introspect the database to see if it doesn't already exist
    if (connection.introspection.table_name_converter(table_name) 
                        not in connection.introspection.table_names()):

        fields = _get_fields(model_class)

        db.create_table(table_name, fields)
        # Some fields are added differently, after table creation
        # eg GeoDjango fields
        db.execute_deferred_sql()
        logger.debug("Created table '%s'" % table_name)

    db.commit_transaction()


def delete_db_table(model_class):
    table_name = model_class._meta.db_table
    db.start_transaction()
    db.delete_table(table_name)
    logger.debug("Deleted table '%s'" % table_name)
    db.commit_transaction()


def _get_fields(model_class):
    """ Return a list of fields that require table columns. """
    return [(f.name, f) for f in model_class._meta.local_fields]


def add_necessary_db_columns(model_class):
    """ Creates new table or relevant columns as necessary based on the model_class.
        No columns or data are renamed or removed.
        This is available in case a database exception occurs.
    """
    db.start_transaction()

    # Create table if missing
    create_db_table(model_class)

    # Add field columns if missing
    table_name = model_class._meta.db_table
    fields = _get_fields(model_class)
    db_column_names = [row[0] for row in connection.introspection.get_table_description(connection.cursor(), table_name)]

    for field_name, field in fields:
        if field.column not in db_column_names:
            logger.debug("Adding field '%s' to table '%s'" % (field_name, table_name))
            db.add_column(table_name, field_name, field)


    # Some columns require deferred SQL to be run. This was collected 
    # when running db.add_column().
    db.execute_deferred_sql()

    db.commit_transaction()


def rename_db_column(table_name, old_name, new_name):
    """ Rename a sensor's database column. """
    db.start_transaction()
    db.rename_column(table_name, old_name, new_name) 
    logger.debug("Renamed column '%s' to '%s' on %s" % (old_name, new_name, table_name))
    db.commit_transaction()


################################################################################
# Validation functions
# TODO: Move to a separate submodule and import?
################################################################################

# This is prefixed to model field names when a reserved system name is used.
CONFLICT_STRING = '_noconflict_'

def validate_identifier_slug(val):
    """ Validates a slug that will be used to generate an identifier. """
    # TODO: Extend standard slug validation?
    # Ensure this can be encoded in ASCII without change
    try:
        val.encode("ascii")
    except UnicodeEncodeError:
        raise ValidationError(_("Please use standard letters and numbers, no accents."))

    # Ensure the string only has valid characters
    for char in val:
        if not char.isalnum() and char not in "-":
            raise ValidationError(_("A key may only contain letters, numbers and hyphen (-)."))

    # Identifiers generally must start with a character, not a digit
    if val[:1].isdigit():
        raise ValidationError(_("A key must start with a letter, not a number."))

    # Ensure that the slug does not begin with conflict string
    if val.startswith(CONFLICT_STRING) or val.startswith(CONFLICT_STRING.replace("_","-")):
        raise ValidationError(_("A key cannot start with %s.") % CONFLICT_STRING)

    return val


def slug_to_class_name(val):
    """ Prepare the given value to be used as a python class name. """
    val = val.encode('ascii', 'ignore').title()
    return filter(str.isalpha, val)


def slug_to_identifier(val):
    """ Prepare the given value to be used as a python or database identifier. """
    # remove non-ascii, hyphens and lower
    val = val.encode('ascii', 'ignore').replace("-","_").lower()

    # filter our undesired characters
    val = filter(lambda x: x.isalnum() or x in "_", val)

    # Model fields cannot contain double underscore. It's best to remove them early
    # to ensure uniqueness constraints are caught when the user can change them
    while "__" in val:
        val = val.replace("__", "_")

    return val


def slug_to_model_field_name(val):
    """ Prepare the given value to be used as a model attribute identifier. """
    val = slug_to_identifier(val)

    # Ensure we don't end up with something that will conflict with model attributes
    if val in RESERVED_ATTRIBUTES:
        val = CONFLICT_STRING + val

    return val


def notify_model_change(model=None, app_label=None, object_name=None, invalidate_only=False, local_hash=lambda i: i._hash):
    """ Notifies other processes that a dynamic model has changed. 
        This should only ever be called after the required database changes have been made.
    """
    if model is not None:
        app_label = model._meta.app_label
        object_name = model._meta.object_name
        name = model._meta.verbose_name
    else:
        name = "%s.%s" % (app_label, object_name)
    CACHE_KEY = HASH_CACHE_TEMPLATE % (app_label, object_name) 
    if invalidate_only:
        val = None
    elif model:
        val = local_hash(model)
        dynamic_model_changed.send(sender=model)

    cache.set(CACHE_KEY, val)
    #logger.debug("Setting \"%s\" hash to: %s" % (name, val))

import django.dispatch
dynamic_model_changed = django.dispatch.Signal(providing_args=["sender"])


HASH_CACHE_TEMPLATE = 'dynamic_model_hash_%s-%s'


######################################################################
# REGISTRY
######################################################################

_dynamic_model_registry = {}

def register_dynamic_models(app_label, name, dependencies, get_models_fn):
    """ Register a class of dynamic models, by linking a function that returns
        an iterable of dynamic models. 
    """
    _dynamic_model_registry[name] = get_models_fn

    # Build all models as soon as possible
    when_classes_prepared(app_label, dependencies, get_models_fn)


def delete_dynamic_tables(*names):
    db.start_transaction()
    for model in get_dynamic_models(*names):
        for f in model._meta.fields:
            if isinstance(f, models.ForeignKey):
                db.delete_foreign_key(model._meta.db_table, f.name)
    transaction.commit_unless_managed()

    db.start_transaction()
    for model in get_dynamic_models(*names):
        db.delete_table(model._meta.db_table, cascade=True)
    #db.commit_transaction()
    transaction.commit_unless_managed()


def get_dynamic_models(*names):
    # If no names provided, delete all tables
    if not names:
        names = _dynamic_model_registry.keys()
    for name in names:
        for model in _dynamic_model_registry[name]():
            yield model


######################################################################
# Move to tests.py
######################################################################

from django.test import TestCase as DjangoTestCase
from django.core.management import call_command
from django.db import connection, transaction


class TestCase(DjangoTestCase):

    def _fixture_setup(self):
        # This is partially copied from the parent (in the Django source)
        # But loads the base test data fixture before loading the rest.

        ##### Reenable when using multi_db #####
        # If the test case has a multi_db=True flag, flush all databases.
        # Otherwise, just flush default.
        #if getattr(self, 'multi_db', False):
        #    databases = connections
        #else:
        #    databases = [DEFAULT_DB_ALIAS]
        #databases = connections

        # Flush dynamic models first (unmanaged models are skipped by flush command)
        # Dyanamic tables must be flushed first because they reference django tables
        delete_dynamic_tables()

        # Flush the rest
        call_command('flush', only_django=False, verbosity=0, interactive=False)#, database=db)

        # build all models between fixture loading
        if getattr(self, 'fixtures', None):
            for fixture in self.fixtures:
                call_command('loaddata', fixture, verbosity=0)#, database=db)
                all(get_dynamic_models())
