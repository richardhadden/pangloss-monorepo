"""Values as the driver gives them, and as they are written"""

import typing
from enum import Enum

from pangloss_models import literals


def native_datetime(value: typing.Any) -> typing.Any:
    """Convert a neo4j DateTime to a Python datetime"""
    return value.to_native() if hasattr(value, "to_native") else value


def convert_type_for_writing(value):
    """Convert a Python value to something the database can store as a property.

    - `Enum` members are stored as their values (a string or a number), so the
      database holds nothing of the enum but what it means.
    - Containers (including TypedDicts) are converted recursively; a set or a tuple is a list.
    - A scalar is stored as its literal codec says (`pangloss_models.literals`): a `Decimal` as a
      string, to keep its exact value, a `UUID`, a URL or a path as its text; the natives as they are."""
    match value:
        case Enum():
            return convert_type_for_writing(value.value)
        case set() | frozenset() | tuple() | list():
            return [convert_type_for_writing(v) for v in value]
        case dict():
            return {k: convert_type_for_writing(v) for k, v in value.items()}
        case _:
            return literals.to_storage(value)
