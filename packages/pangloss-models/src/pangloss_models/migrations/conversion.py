"""A stored value as another type, as a migration's change of a literal type makes it (`AlterLiteralType`,
`AlterListItemType`): the same conversion as the Cypher of the backend (`pangloss_cypher.migrations.conversion`),
for what is kept outside the graph's properties: a version in history (`pangloss_history.upgrade`), and the values a
stored search pattern compares (`patterns`).

The types are those of a snapshot (`{"type": "int"}`, `{"type": "enum", "enum": "Colour"}`), and `enums` the
snapshot's enums.
"""

import datetime
from decimal import Decimal, InvalidOperation
from typing import Any


class Unconvertible(Exception):
    pass


def convert_value(
    old: dict, new: dict, value: Any, enums: dict, mapping: dict | None = None
) -> Any:
    """What a stored value is as another type, as the Cypher of the migration makes it
    (`conversion.py`). Raises `Unconvertible` if it cannot be"""
    old_type, new_type = old["type"], new["type"]
    if old_type == new_type and (old_type != "enum" or old["enum"] == new["enum"]):
        return value
    try:
        if new_type == "enum":
            return to_enum(old, new, value, enums, mapping)
        if old_type == "enum":
            if new_type == "str":
                return str(value)
            raise Unconvertible(f"enum to {new_type} is not supported")
        match (old_type, new_type):
            case ("str", "int"):
                return int(str(value).strip())
            case ("str", "float"):
                return float(value)
            case ("str", "bool"):
                lowered = str(value).lower()
                if lowered not in ("true", "false"):
                    raise Unconvertible("not true or false")
                return lowered == "true"
            case ("str", "decimal"):
                Decimal(value)
                return value
            case ("str", "date"):
                return datetime.date.fromisoformat(value).isoformat()
            case ("int", "float"):
                return float(value)
            case ("int" | "float", "str"):
                return str(value)
            case ("int" | "float", "decimal"):
                return str(value)
            case ("int", "bool"):
                return value != 0
            case ("float", "int") | ("decimal", "int"):
                return int(float(value))
            case ("bool", "str"):
                return "true" if value else "false"
            case ("bool", "int"):
                return 1 if value else 0
            case ("decimal", "str") | ("date", "str"):
                return str(value)
            case ("decimal", "float"):
                return float(value)
    except (ValueError, TypeError, InvalidOperation) as error:
        raise Unconvertible(str(error)) from error
    raise Unconvertible(f"{old_type} to {new_type} is not supported")


def to_enum(old: dict, new: dict, value: Any, enums: dict, mapping: dict | None) -> Any:
    members = enums.get(new["enum"], {}).get("members", [])
    by_name = {m["name"]: m["value"] for m in members}
    pairs: dict[str, Any] = {}
    if old["type"] == "enum":
        before = enums.get(old["enum"], {}).get("members", [])
        for member in before:
            if member["name"] in by_name:
                pairs[str(member["value"])] = by_name[member["name"]]
        for old_name, new_name in (mapping or {}).items():
            source = next((m["value"] for m in before if m["name"] == old_name), None)
            if source is not None and new_name in by_name:
                pairs[str(source)] = by_name[new_name]
    else:
        pairs = {str(v): v for v in by_name.values()}
        for old_value, new_name in (mapping or {}).items():
            if new_name in by_name:
                pairs[str(old_value)] = by_name[new_name]
    text = str(value)
    if text not in pairs:
        raise Unconvertible(f"not a value of {new['enum']}")
    return pairs[text]


__all__ = ["Unconvertible", "convert_value", "to_enum"]
