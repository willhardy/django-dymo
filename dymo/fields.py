#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from django.db import models, connection
from django.utils.translation import ugettext_lazy as _

from dymo.validation import validate_identifier_slug


class IdentifierSlugField(models.CharField):
    description = _("A slug that can be used as an identifier")

    def __init__(self, *args, **kwargs):
        # Default max_length is DB identifier limit (PG=63 Oracle=30 MySQL=64)
        # Explicitly set the lowest of DBs that will host dynamic tables
        kwargs.setdefault('max_length', connection.ops.max_name_length())
        super(IdentifierSlugField, self).__init__(*args, **kwargs)
        self.validators.append(validate_identifier_slug)

    def south_field_triple(self):
        " Returns a description of this field for DB migrations with South. "
        from south.modelsinspector import introspector
        args, kwargs = introspector(self)
        return ('django.db.models.fields.CharField', args, kwargs)
