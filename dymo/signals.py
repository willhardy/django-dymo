#!/usr/bin/env python
# -*- coding: UTF-8 -*-

""" Signal builders to catch renamed tables and columns.
"""

from django.db.models.signals import pre_save, post_save, post_delete
from django.db import transaction

from dymo.db import rename_db_column, rename_db_table, delete_db_table, delete_db_column
from dymo.db import get_deleted_tables, get_deleted_columns, DELETED_PREFIX
from dymo.sync import notify_model_change
from dymo.models import DeletedColumn, DeletedTable

OLD_COLUMN_NAME_ATTR = "_dymo_old_column_name"
OLD_TABLE_NAME_ATTR = "_dymo_old_table_name"
OLD_MODEL_NAME_ATTR = "_dymo_old_model_name"


def connect_column_migration_signals(model_class, col_attr, get_model_name, get_table_name, app_label=None, soft_delete=True):
    """ Connects signals to perform migration when column name has been changed or the column has been deleted.
        Optionally, a soft delete can be set, which only renames the column out of the way.
    """
    _pre_save = build_column_pre_save(col_attr, get_model_name, get_table_name)
    pre_save.connect(_pre_save, sender=model_class, weak=False)

    _post_save = build_column_post_save(col_attr, get_model_name, get_table_name, app_label)
    post_save.connect(_post_save, sender=model_class, weak=False)

    _post_delete = build_column_post_delete(col_attr, get_model_name, get_table_name, app_label, soft_delete)
    post_delete.connect(_post_delete, sender=model_class, weak=False)


def connect_table_migration_signals(model_class, model_name_attr, table_name_attr=None, app_label=None, soft_delete=True):
    """ Connects signals to perform migration when table name has been changed or the table has been deleted.
        Optionally, a soft delete can be set, which only renames the table out of the way.
    """
    _pre_save = build_table_pre_save(model_name_attr, table_name_attr)
    pre_save.connect(_pre_save, sender=model_class)

    _post_save = build_table_post_save(model_name_attr, table_name_attr, app_label)
    post_save.connect(_post_save, sender=model_class)

    # Tables are not deleted automatically (because of potential problems with related objects)
    # Either a soft_delete is used to move the table out of the way, or nothing happens.
    # If your system wants to delete the table, it needs to do it manually
    if soft_delete:
        _post_delete = build_table_post_delete(model_name_attr, table_name_attr, app_label)
        post_delete.connect(_post_delete, sender=model_class)


def build_column_pre_save(col_attr, get_model_name, get_table_name, query=None):
    def column_pre_save(sender, instance, **kwargs):
        """ Make note of any potential column name changes.
            col_attr is the attribute that contains the column name.
            get_model_name and get_table_name are functions that take an
            instance and return the relevant name. If the table name has
            changed at the same time as the column change, this will fail
            to work as expected.
            If such an event is possible, you must provide your own query.
        """
        if query is not None:
            _query = query
        else:
            _query = sender.objects.exclude(**{col_attr: getattr(instance,col_attr)})

        if instance.pk:
            # Try to detect if a column has been renamed
            _query = _query.filter(pk=instance.pk)
            try:
                old_column_name = _query.values_list(col_attr, flat=True)[0]
                setattr(instance, OLD_COLUMN_NAME_ATTR, old_column_name)

            # Fixture loading will not have an existing value, so we can't use it
            # In any case, this won't have been a renaming event.
            except IndexError:
                return

    return column_pre_save


def build_column_post_save(col_attr, get_model_name, get_table_name, app_label=None):
    def column_post_save(sender, instance, created, **kwargs):
        """ Adapt tables to any relavent changes:
            If the sensor has been renamed (on the same logger), rename the columns.
            Add any necessary columns.
        """

        # NB note that renaming takes place before notification, so that the change is already in the database
        if hasattr(instance, OLD_COLUMN_NAME_ATTR):
            rename_db_column(get_table_name(instance), getattr(instance, OLD_COLUMN_NAME_ATTR), getattr(instance, col_attr))

        # Use of discover the relevant app_label
        if app_label:
            _app_label = app_label
        else:
            _app_label = instance.sender._meta.app_label

        notify_model_change(app_label=_app_label, object_name=get_model_name(instance), invalidate_only=True)

    return column_post_save


def _get_max_deleted_index(names):
    try:
        return max(int(filter(str.isdigit, str(n)) or 0) for n in names)
    except ValueError:
        return 0


def build_column_post_delete(col_attr, get_model_name, get_table_name, app_label=None, soft_delete=True):
    if soft_delete:
        def column_post_delete(sender, instance, **kwargs):
            table_name = get_table_name(instance)
            column_name = getattr(instance, col_attr)
            max_index = _get_max_deleted_index(get_deleted_columns(table_name))

            # Rename column out of the way
            new_column_name = DELETED_PREFIX + str(max_index + 1)
            rename_db_column(table_name, column_name, new_column_name)

            # Log this renaming, if this functionality is available
            if DeletedColumn:
                log = DeletedColumn()
                log.original_table_name = table_name
                log.original_name = column_name
                log.current_name = new_column_name
                log.save()

    else:
        def column_post_delete(sender, instance, **kwargs):
            table_name = get_table_name(instance)
            column_name = getattr(instance, col_attr)
            delete_db_column(table_name, column_name)

            # Log this deletion, if this functionality is available
            if DeletedColumn:
                log = DeletedColumn()
                log.original_table_name = table_name
                log.original_name = column_name
                log.save()

    return column_post_delete


def build_table_pre_save(model_name_attr, table_name_attr=None, query=None):
    """ If table_name_attr is given, identify when a table name changes. 
    """

    def table_pre_save(sender, instance, **kwargs):
        if table_name_attr:
            if query is not None:
                _query = query
            else:
                _query = sender.objects.exclude(**{table_name_attr: getattr(instance,table_name_attr)})

            # Try to detect if the table been renamed
            if instance.pk:
                _query = _query.filter(pk=instance.pk)
                try:
                    old_table_name = _query.values_list(table_name_attr, flat=True)[0]
                    setattr(instance, OLD_TABLE_NAME_ATTR, old_table_name)

                # Fixture loading will not have an existing object in the database,
                # so we can't use it
                except IndexError:
                    return

    return table_pre_save


def build_table_post_save(model_name_attr, table_name_attr=None, app_label=None):

    def table_post_save(sender, instance, created, **kwargs):
        """  
            Rename any tables and notify other processes of a potential model change.
        """
    
        # If table name changes are to be tracked, rename the database table
        if table_name_attr and hasattr(instance, OLD_TABLE_NAME_ATTR):
            old_name = getattr(instance, OLD_TABLE_NAME_ATTR)
            new_name = getattr(instance, table_name_attr)
            rename_db_table(old_name, new_name)
            delattr(instance, OLD_TABLE_NAME_ATTR)

        # Invalidate any old definitions 
        if hasattr(instance, OLD_MODEL_NAME_ATTR):
            model_name = getattr(instance, OLD_MODEL_NAME_ATTR)
        else:
            model_name = getattr(instance, model_name_attr)

        # Use or discover the relevant app_label
        if app_label:
            _app_label = app_label
        else:
            _app_label = sender._meta.app_label

        notify_model_change(app_label=_app_label, object_name=model_name, invalidate_only=True)

    return table_post_save


def build_table_post_delete(model_name_attr, table_name_attr=None, app_label=None):
    """ Delete or optionally rename underlying table, logging the result if that is enabled. """
    def table_post_delete(sender, instance, **kwargs):
        if table_name_attr:
            table_name = getattr(instance, table_name_attr)
            max_index = _get_max_deleted_index(get_deleted_tables())

            # Rename database table out of the way
            new_table_name = DELETED_PREFIX + str(max_index + 1)
            rename_db_table(table_name, new_table_name)

            # Log this renaming, if this functionality is available
            if DeletedTable:
                log = DeletedTable()
                log.original_name = table_name
                log.current_name = new_table_name
                #log.object_count = ?
                log.save()

    return table_post_delete

