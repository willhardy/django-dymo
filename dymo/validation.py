#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from django.utils.translation import ugettext as _
from django.core.exceptions import ValidationError
from django.db import models

""" Validation functions

    TODO: 
        IdentifierField()  - slug field to be used as an identifier
                             with methods such as "to_slug", "to_identifier", "to_model_field_name"
"""


# Keys belonging to the model, cannot be field names
# Some are more likely than others
RESERVED_ATTRIBUTES = (
    models.Model.__dict__.keys()   # Model class methods, attributes
    + ['objects', '_base_manager'] # Added by manager
    + ['MultipleObjectsReturned', 'DoesNotExist'] # Added by base
    + ['_order', 'id', '_meta', 'pk'] # Added by options
    )

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

