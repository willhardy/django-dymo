#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from optparse import make_option

from django.core.management.base import BaseCommand, CommandError
from django.db.models.fields import NOT_PROVIDED
from south.db import db

from .registry import get_dynamic_models

class Command(BaseCommand):
    """
    Management Command for django
    """

    option_list = BaseCommand.option_list + (
        make_option('--sql', '-s', default=False, action="store_true", dest="show_sql",
            help='Show the generated SQL schema for the given model.'),
    )
    help = 'Inspect the django definition or SQL schema of dynamic models.'

    def handle(self, *args, **options):
        if options['show_sql']:
            get_definition = get_sql_schema
        else:
            get_definition = get_model_definition

        already_defined = set()

        for model in get_dynamic_models():
            print get_definition(model, already_defined)

        # raise CommandError("")


def get_model_definition(model, already_defined):
    """ Returns a string representing how the model would have looked if it was coded in the normal way.
        Additional 
        eg.
        
        class ModelName(bases):
            field = models.CharField(max_length=20)
    """
    if model in already_defined:
        return ''

    name = model._meta.object_name
    parents = ",".join(m._meta.object_name for m in model._meta.parents) or "models.Model"

    lines = []

    for parent in model._meta.parents:
        defn = get_model_definition(parent, already_defined)
        if defn:
            lines.append(defn)

    lines.append("class {0}({1}):".format(name, parents))

    fields = []
    for field in model._meta.local_fields:
        if field.auto_created:
            continue
        name = field.attname
        mod = field.__class__.__module__
        _class = field.__class__.__name__
        attrs = ", ".join("=".join(v) for v in get_init_attributes(field))
        if mod.startswith("django."):
            mod = "models"
        fields.append("    {0:16} = {1}.{2}({3})".format(name, mod, _class, attrs))
    if fields:
        lines.append('\n'.join(fields))
    else:
        lines.append('    pass')

    lines.append('')

    already_defined.add(model)

    return "\n".join(lines)


def get_init_attributes(field):
    attrs = []
    if field.rel:
        if field.rel.to._meta.object_name:
            attrs.append((repr(field.rel.to._meta.object_name),))
        if field.rel.related_name:
            attrs.append(('related_name', repr(field.rel.related_name)))
        if field.verbose_name:
            attrs.append(('verbose_name', repr(field.verbose_name)))
    else:
        if field.verbose_name:
            attrs.append((repr(field.verbose_name),))
    if field.choices:
        attrs.append(('choices', repr(field.choices)))
    if field.max_length is not None:
        attrs.append(('max_length', repr(field.max_length)))
    if field.default is not NOT_PROVIDED:
        attrs.append(('default', repr(field.default)))
    if field.null:
        attrs.append(('null', repr(field.null)))
    if field.editable:
        attrs.append(('editable', repr(field.editable)))
    if field.blank:
        attrs.append(('blank', repr(field.blank)))
        
    return attrs


def get_sql_schema(model, already_defined):
    """ Returns a string with the database schema (SQL create table statement).
    """
    if model in already_defined:
        return ''

    lines = []

    table_name = model._meta.db_table

    for parent in model._meta.parents:
        defn = get_sql_schema(parent, already_defined)
        if defn:
            lines.append(defn)

    columns = [
        db.column_sql(table_name, field.db_column, field)
        for field in model._meta.local_fields
    ]

    lines.append("--")
    lines.append("-- %s" % model._meta.object_name)
    lines.append("--")
    lines.append("")
    lines.append('CREATE TABLE %s (\n    %s\n);' % (
            db.quote_name(table_name),
            ',\n    '.join([col for col in columns if col]),
        ))
    lines.append("\n".join(db.deferred_sql))
    lines.append("")

    already_defined.add(model)

    return '\n'.join(lines)


