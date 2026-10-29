"""Cypher to turn a stored value into another type, for a change of the type of a field.

Each gives an expression of the value (`ref`) that is `null` when it cannot be converted, so
that what does not convert can be found; except `date`, which Neo4j reports as an error.
Decimals are stored as strings; enums as the values of their members.
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

    if old_type == new_type and (old_type != "enum" or old["enum"] == new["enum"]):
        return ref, params

    if new_type == "enum":
        return _to_enum(old, new, ref, enums, mapping, params)

    if old_type == "enum":
        # (a member is stored as its value)
        if new_type == "str":
            return f"toString({ref})", params
        raise PanglossMigrationNotSupported(
            f"Converting an enum to {new_type} is not supported: write it by hand"
        )

    table = {
        ("str", "int"): f"toInteger({ref})",
        ("str", "float"): f"toFloat({ref})",
        ("str", "bool"): (
            f"CASE toLower({ref}) WHEN 'true' THEN true WHEN 'false' THEN false ELSE null END"
        ),
        (
            "str",
            "decimal",
        ): f"CASE WHEN toFloat({ref}) IS NULL THEN null ELSE {ref} END",
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
    """The value of a member of the new enum from a stored value. From a string: the string if it is
    the value of a member (or, for a number, its text). From another enum: the member of the same
    name, unless `mapping` (old member name to new member name) says otherwise."""
    members = enums.get(new["enum"], {}).get("members", [])
    by_name = {m["name"]: m["value"] for m in members}
    pairs: dict[str, object] = {}
    if old["type"] == "enum":
        before = enums.get(old["enum"], {}).get("members", [])
        for member in before:
            if member["name"] in by_name:
                pairs[str(member["value"])] = by_name[member["name"]]
        for old_name, new_name in (mapping or {}).items():
            source = next((m["value"] for m in before if m["name"] == old_name), None)
            if source is None or new_name not in by_name:
                raise PanglossMigrationNotSupported(
                    f"The mapping {old_name!r} -> {new_name!r} is not between members of "
                    f"{old['enum']} and {new['enum']}"
                )
            pairs[str(source)] = by_name[new_name]
    else:
        pairs = {str(value): value for value in by_name.values()}
        for old_value, new_name in (mapping or {}).items():
            if new_name not in by_name:
                raise PanglossMigrationNotSupported(
                    f"{new_name!r} is not a member of {new['enum']}"
                )
            pairs[str(old_value)] = by_name[new_name]

    params["enum_map"] = pairs
    expression = f"CASE WHEN toString({ref}) IN keys($enum_map) THEN $enum_map[toString({ref})] ELSE null END"
    return expression, params
