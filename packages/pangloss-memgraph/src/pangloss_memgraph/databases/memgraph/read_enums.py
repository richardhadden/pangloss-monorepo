"""Reading enums.

Memgraph sends an enum value to the driver as a dict, wherever it is in the data (in a
list or a map as well):

    {"__type": "mg_enum", "__value": "Colour::RED"}

`convert_enums` replaces each with the member of the `Enum` that the models use.
"""

import typing
from enum import Enum

from pangloss_models.exceptions import PanglossRuntimeError

from pangloss_memgraph.databases.memgraph.initialise_database import (
    enums_used_by_models,
)

MEMGRAPH_ENUM_TYPE = "mg_enum"


def convert_enums(data: typing.Any) -> typing.Any:
    """Replace the enums in data from Memgraph with members of the models' enums"""
    enum_classes: dict[str, type[Enum]] | None = None

    def convert(value: typing.Any) -> typing.Any:
        nonlocal enum_classes
        if isinstance(value, dict):
            if value.get("__type") == MEMGRAPH_ENUM_TYPE:
                enum_name, _, member_name = value["__value"].partition("::")
                if enum_classes is None:
                    enum_classes = {e.__name__: e for e in enums_used_by_models()}
                enum_class = enum_classes.get(enum_name)
                if enum_class is None or member_name not in enum_class.__members__:
                    raise PanglossRuntimeError(
                        f"The database has an enum value {value['__value']}, which "
                        "no enum of the models has"
                    )
                return enum_class[member_name]
            return {key: convert(item) for key, item in value.items()}
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value

    return convert(data)
