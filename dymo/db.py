#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import logging
from south.db import db
from django.db import connection, DatabaseError
from django.db import models

logger = logging.getLogger('dymo')


def update_table(model_class):
    create_db_table(model_class)
    add_necessary_db_columns(model_class)


def create_db_table(model_class):
    """ Takes a Django model class and create a database table, if necessary.
    """
    table_name = model_class._meta.db_table

    # Introspect the database to see if it doesn't already exist
    if (connection.introspection.table_name_converter(table_name) 
                        not in connection.introspection.table_names()):
        db.start_transaction()

        fields = _get_fields(model_class)

        db.create_table(table_name, fields)
        # Some fields are added differently, after table creation
        # eg GeoDjango fields
        db.execute_deferred_sql()
        db.commit_transaction()
        logger.debug("Created table '%s'" % table_name)

    create_auto_m2m_tables(model_class)

    db.send_create_signal(model_class._meta.app_label, [model_class._meta.object_name])


def create_auto_m2m_tables(model_class):
    " Create tables for ManyToMany fields "
    for f in model_class._meta.many_to_many:
        if f.rel.through:
            try:
                # Django 1.2+
                through = f.rel.through
            except AttributeError:
                # Django 1.1 and below
                through = f.rel.through_model

        if (not f.rel.through) or getattr(through._meta, "auto_created", None):

            # Create the standard implied M2M table
            m2m_table_name = f.m2m_db_table()
            if (connection.introspection.table_name_converter(m2m_table_name) 
                        not in connection.introspection.table_names()):

                db.start_transaction()
                m2m_column_name = f.m2m_column_name()[:-3] # without "_id"
                m2m_reverse_name = f.m2m_reverse_name()[:-3] # without "_id"
                db.create_table(f.m2m_db_table(), (
                    ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
                    (m2m_column_name, models.ForeignKey(model_class, null=False)),
                    (m2m_reverse_name, models.ForeignKey(f.rel.to, null=False))
                ))
                db.create_unique(f.m2m_db_table(), [f.m2m_column_name(), f.m2m_reverse_name()])
                #db.execute_deferred_sql()
                db.commit_transaction()
                logger.debug("Created table '%s'" % m2m_table_name)


DELETED_PREFIX = "_deleted_"

def get_deleted_tables():
    return [t for t in connection.introspection.table_names() 
                                    if t.startswith(DELETED_PREFIX)]

def get_deleted_columns(table_name):
    rows = connection.introspection.get_table_description(connection.cursor(), table_name)
    return [r[0] for r in rows if r[0].startswith(DELETED_PREFIX)]


def delete_db_table(table_name):
    db.delete_table(table_name)
    logger.debug("Deleted table '%s'" % table_name)


def delete_db_column(table_name, column_name):
    db.delete_column(table_name, column_name)
    logger.debug("Deleted column '%s.%s'" % (table_name, column_name))


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


def rename_db_table(old_table_name, new_table_name):
    """ Rename a sensor's database column. """
    db.start_transaction()
    db.rename_table(old_table_name, new_table_name)
    logger.debug("Renamed table '%s' to '%s'" % (old_table_name, new_table_name))
    db.commit_transaction()

