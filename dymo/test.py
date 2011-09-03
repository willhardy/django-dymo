#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from django.test import TestCase as DjangoTestCase
from django.core.management import call_command
from django.db import connection, transaction, models
from django.contrib.contenttypes.models import ContentType 
from django.contrib.auth.models import Permission 
from django.core.management.color import no_style
from django.core.management.sql import sql_flush
from south.db import db

from dymo.registry import get_dynamic_models

class TestCase(DjangoTestCase):

    def _fixture_setup(self):
        # This is partially copied from the parent (in the Django source)
        # But loads the base test data fixture before loading the rest.

        # TODO: Reenable when using multi_db #####
        # If the test case has a multi_db=True flag, flush all databases.
        # Otherwise, just flush default.
        #if getattr(self, 'multi_db', False):
        #    databases = connections
        #else:
        #    databases = [DEFAULT_DB_ALIAS]
        #databases = connections

        ContentType.objects.clear_cache() 

        # Delete dynamic models first, tests should make their own
        # It's slower, but the tests must be independent
        #flush_dynamic_tables()
        delete_dynamic_tables()
        
        # Clear the content type cache
        connection.cursor().execute('SET CONSTRAINTS ALL IMMEDIATE') 
        connection.cursor().execute('SET CONSTRAINTS ALL DEFERRED') 

        # Flush the rest
        call_command('flush', only_django=False, verbosity=0, interactive=False)#, database=db)

        # build all models between fixture loading
        if getattr(self, 'fixtures', None):
            for fixture in self.fixtures:
                call_command('loaddata', fixture, verbosity=0)#, database=db)
                all(get_dynamic_models())


def delete_dynamic_tables(*names):
    db.start_transaction()
    for model in get_dynamic_models(*names):
        for f in model._meta.fields:
            if isinstance(f, models.ForeignKey):
                try:
                    db.delete_foreign_key(model._meta.db_table, f.column)
                except ValueError:
                    pass
    transaction.commit_unless_managed()

    db.start_transaction()
    for model in get_dynamic_models(*names):
        db.delete_table(model._meta.db_table, cascade=True)
    #db.commit_transaction()
    transaction.commit_unless_managed()

def flush_dynamic_tables(*names):
    db.start_transaction()
    tables = [] #connection.introspection.django_table_names(only_existing=True)
    for model in get_dynamic_models(*names):
        #for f in model._meta.fields:
        #    if isinstance(f, models.ForeignKey):
        #        db.delete_foreign_key(model._meta.db_table, f.db_column)
        tables.append(model._meta.db_table)

    statements = connection.ops.sql_flush(
        no_style(), tables, connection.introspection.sequence_list()
    )

    try:
        cursor = connection.cursor()
        for sql in statements:
            cursor.execute(sql)
    except Exception, e:
        transaction.rollback_unless_managed()#using=db)
        raise
    transaction.commit_unless_managed()#using=db)

