"""Values as the driver gives them, and as they are written"""

import typing
import uuid
from decimal import Decimal
from enum import Enum

from pydantic import AnyUrl


def native_datetime(value: typing.Any) -> typing.Any:
    """Convert a neo4j DateTime to a Python datetime"""
    return value.to_native() if hasattr(value, "to_native") else value


def convert_type_for_writing(value):
    """Convert a Python value to something the database can store as a property.

    - `Decimal` is stored as a string, to keep its exact value (Memgraph has no
      decimal type).
    - `Enum` members are stored as their values (a string or a number), so the
      database holds nothing of the enum but what it means.
    - Containers (including TypedDicts) are converted recursively."""
    match value:
        case uuid.UUID():
            return str(value)
        case AnyUrl():
            return str(value)
        case Enum():
            return convert_type_for_writing(value.value)
        case Decimal():
            return str(value)
        case set() | tuple() | list():
            return [convert_type_for_writing(v) for v in value]
        case dict():
            return {k: convert_type_for_writing(v) for k, v in value.items()}
        case _:
            return value
