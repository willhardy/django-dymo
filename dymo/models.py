#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from django.db import models
from datetime import datetime
from django.utils.translation import gettext_lazy as _
from django.conf import settings

# These models will only be installed if explicitly requested
MANAGE_DELETIONS = getattr(settings, "DYMO_MANAGE_DELETIONS", False)

if MANAGE_DELETIONS:

    class DeletedTable(models.Model):
        """ Log of orphaned tables from deleted dynamic models. 
            These were renamed to avoid future conflicts and are linked here.
        """
        original_name = models.CharField(_("original name"), max_length=127)
        current_name  = models.CharField(_("current name"), max_length=127)
        datetime      = models.DateTimeField(_("date/time"), db_index=True,
                                    default=datetime.now, editable=False)

        #object_count  = models.PositiveIntegerField(_("count"), editable=False)
        #columns       = models.TextField(_("columns"), default="", blank=True)
        #deleted_by    = models.CharField(_("deleted by"), 
        #                            max_length=127, default="", blank=True)
        # The output from dymo_inspect
        #definition    = models.TextField(_("model definition"), 
        #                            default="", blank=True)

        def __unicode__(self):
            return self.current_name

        class Meta:
            verbose_name = _("deleted table")
            verbose_name_plural = _("deleted tables")
            ordering = ('datetime',)
        

    class DeletedColumn(models.Model):
        """ Log of orphaned columns from deleted attributes on dynamic models. 
            These were renamed to avoid future conflicts and are linked here.
        """
        original_table_name = models.CharField(_("original table name"), max_length=127)
        original_name       = models.CharField(_("original name"), max_length=127)
        current_name        = models.CharField(_("current name"), max_length=127)
        datetime            = models.DateTimeField(_("date/time"), db_index=True,
                                        default=datetime.now, editable=False)

        # If we are able to accurately track renames and deletions, the current
        # table name should be known
        current_table_name  = models.CharField(_("current table name"), 
                                        max_length=127, default="", blank=True)
        #deleted_by          = models.CharField(_("deleted by"), 
        #                                max_length=64, default="", blank=True)
        # The output from dymo_inspect
        #definition          = models.CharField(_("model definition"), 
        #                                max_length=512, default="", blank=True)

        def __unicode__(self):
            return self.current_name

        class Meta:
            verbose_name = _("deleted column")
            verbose_name_plural = _("deleted columns")
            ordering = ('datetime',)

else:
    DeletedTable = None
    DeletedColumn = None
