#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import logging
from south.db import db
from django.db import connection, DatabaseError
from django.db import models

logger = logging.getLogger('dymo')


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

