"""The name an incoming relation is read under, against the fields of the model it comes in to.

A relation is two edges, and the target reads the one back under the `reverse_name` (by default `<field>_reverse`) as
a field of its own view. If that name is also a field of the target, the incoming relation takes its place in the view,
and the name is dropped from what a client writes (it is a key only the server fills in). The value is lost without a
word: a `Place` with `name: str` and a relation with `reverse_name="name"` saves `name` as the default or refuses it as
missing, and is read back as a list of the people born there (or not at all, when it holds a string).
"""

from pangloss_models.diagnostics import reported
from pangloss_models.exceptions import AtString, PanglossModelError

# (the keys of a view that every document and entity has, besides its fields)
RESERVED = ("id", "type", "meta", "urls", "label")


def check_reverse_names(models: list[type]) -> None:
    """Raise `PanglossModelError` for a reverse name that is the name of a field of the model it is read on"""
    for target in models:
        definitions = getattr(getattr(target, "_meta", None), "field_definitions", None)
        incoming = getattr(definitions, "incoming_fields", None)
        if not incoming:
            continue
        taken = {*target._meta.fields, *RESERVED}  # type: ignore[attr-defined]
        for name, relations in incoming.items():
            if name not in taken:
                continue
            for relation in relations:
                field = relation.field_definition
                owner = getattr(field, "field_on_model", None) or relation.source
                what = (
                    f"a field of {target.__name__}"
                    if name in target._meta.fields  # type: ignore[attr-defined]
                    else f"a key that every {target.__name__} has"
                )
                with reported(owner, field.field_name):
                    raise PanglossModelError(
                        f"{owner.__name__}.{field.field_name}: the name the relation is read under on "
                        f"{target.__name__}, {name!r}, is also {what}. The relation would take its place, and "
                        f"the value of {name!r} could not be written or read. Give the relation another "
                        f"`reverse_name`.",
                        at_string=AtString("reverse_name", name),
                    )
