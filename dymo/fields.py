#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from django.db import models, connection
from django.utils.translation import ugettext_lazy as _

from .validation import validate_identifier_slug


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


class ManyToManyField(models.ManyToManyField):
    def _get_m2m_attr(self, related, attr):
        "Function that can be curried to provide the source accessor or DB column name for the m2m table"
        cache_attr = '_m2m_%s_cache' % attr
        related_tuple = (related.model._meta.app_label, related.model._meta.object_name)
        if hasattr(self, cache_attr):
            return getattr(self, cache_attr)
        for f in self.rel.through._meta.fields:
            if hasattr(f,'rel') and f.rel:
                if (f.rel.to._meta.app_label, f.rel.to._meta.object_name) == related_tuple:
                    setattr(self, cache_attr, getattr(f, attr))
                    return getattr(self, cache_attr)

