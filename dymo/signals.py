#!/usr/bin/env python
# -*- coding: UTF-8 -*-

""" Signal builders to catch renamed tables and columns.
"""

from dymo.db import rename_db_column, rename_db_table
from dymo.sync import notify_model_change

OLD_COLUMN_NAME_ATTR = "_dymo_old_column_name"
OLD_TABLE_NAME_ATTR = "_dymo_old_table_name"
OLD_MODEL_NAME_ATTR = "_dymo_old_model_name"

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


def build_column_post_delete(col_attr, get_model_name, get_table_name, app_label=None):
    return


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
    return