"""Cypher to turn a stored value into another type, for a change of the type of a field.

Each gives an expression of the value (`ref`) that is `null` when it cannot be converted, so
that what does not convert can be found; except `date`, which Memgraph reports as an error.
Decimals are stored as strings; enums as native enum values (see `docs/memgraph.md`).
"""

from pangloss_models.exceptions import PanglossMigrationNotSupported

SCALARS = {"str", "int", "float", "bool", "decimal", "date"}


def convert_expression(
    old: dict, new: dict, ref: str, enums: dict[str, dict], mapping: dict | None = None
) -> tuple[str, dict]:
    """`(expression, parameters)` that converts `ref`, of the type `old`, to the type `new`.

    A type is a descriptor of the snapshot (`{"type": "int"}`, `{"type": "enum", "enum":
    "Colour"}`). `mapping` gives the member of an enum for each value, where it is not to be
    found from the enum's values."""
    old_type, new_type = old["type"], new["type"]
    params: dict = {}

    if old_type == new_type and old_type != "enum":
        return ref, params

    if new_type == "enum":
        return _to_enum(old, new, ref, enums, mapping, params)

    if old_type == "enum":
        # (a member is stored as `Colour::RED`)
        text = f"split(toString({ref}), '::')[1]"
        if new_type == "str":
            return text, params
        raise PanglossMigrationNotSupported(
            f"Converting an enum to {new_type} is not supported: write it by hand"
        )

    table = {
        ("str", "int"): f"toInteger({ref})",
        ("str", "float"): f"toFloat({ref})",
        ("str", "bool"): (
            f"CASE toLower({ref}) WHEN 'true' THEN true WHEN 'false' THEN false ELSE null END"
        ),
        ("str", "decimal"): f"CASE WHEN toFloat({ref}) IS NULL THEN null ELSE {ref} END",
        ("str", "date"): f"date({ref})",
        ("int", "float"): f"toFloat({ref})",
        ("int", "str"): f"toString({ref})",
        ("int", "decimal"): f"toString({ref})",
        ("int", "bool"): f"{ref} <> 0",
        ("float", "int"): f"toInteger({ref})",
        ("float", "str"): f"toString({ref})",
        ("float", "decimal"): f"toString({ref})",
        ("bool", "str"): f"toString({ref})",
        ("bool", "int"): f"CASE WHEN {ref} THEN 1 ELSE 0 END",
        ("decimal", "str"): ref,
        ("decimal", "float"): f"toFloat({ref})",
        ("decimal", "int"): f"toInteger({ref})",
        ("date", "str"): f"toString({ref})",
    }
    try:
        return table[(old_type, new_type)], params
    except KeyError:
        raise PanglossMigrationNotSupported(
            f"Converting {old_type} to {new_type} is not supported: write it by hand"
        ) from None


def _to_enum(old, new, ref, enums, mapping, params) -> tuple[str, dict]:
    """An enum member from a value: by the mapping given, or the value of a member"""
    enum_name = new["enum"]
    members = enums.get(enum_name, {}).get("members", [])
    by_value = {m["value"]: m["name"] for m in members}
    pairs = dict(mapping) if mapping else {}
    if old["type"] == "enum":
        # an enum to another: by the name of the member, unless it is mapped
        source = f"split(toString({ref}), '::')[1]"
        pairs = {**{m["name"]: m["name"] for m in members}, **pairs}
    else:
        source = ref
        pairs = {**by_value, **pairs}

    params["enum_name"] = enum_name
    params["enum_map"] = {str(key): value for key, value in pairs.items()}
    expression = (
        f"CASE WHEN {source} IN keys($enum_map) "
        f"THEN ToEnum($enum_name, $enum_map[{source}]) ELSE null END"
    )
    return expression, params
