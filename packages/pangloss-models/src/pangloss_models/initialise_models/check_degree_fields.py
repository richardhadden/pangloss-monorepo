"""The checks at `initialise()` of `Degree()` (`pangloss_models.markers`), the marker of the field whose value is a
semantic space's degree, written into the space's entry of the path of what it holds: that it is on a space, once on
a class, on a field of the type `DegreeStep` (or `DegreeStep | None`), and only on a space whose contents are neither
asserted nor denied.

Each class is checked with the fields it has, those it inherits included. A class is refused only for what it says
itself: a fault its nearest checked parent has too is the parent's, and a subclass that makes the fault (a second
marked field, a `"not"` over an inherited field) is refused by its own name"""

import types
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal, TypeAliasType, Union, get_args, get_origin

from pangloss_models.diagnostics import reported
from pangloss_models.exceptions import PanglossModelError
from pangloss_models.initialise_models.check_semantic_spaces import modal_text
from pangloss_models.markers import Degree
from pangloss_models.model_bases.semantic_space import (
    DEGREE_STEPS,
    Modal,
    SemanticSpace,
)

WRITE = "Annotated[DegreeStep | None, Degree()] = None"


@dataclass(frozen=True)
class Fault:
    message: str
    # (what makes it the same fault in a subclass: a fault the parent has too is reported of the parent)
    key: tuple
    # (the fields it may be reported at, the first the class declares itself; at its `_meta` if it declares none)
    at: tuple[str, ...]


def marked_fields(model: type) -> list[str]:
    """The fields of the class marked `Degree()`, those it inherits included, read from what each is annotated with
    (a field of a kind whose definition keeps no markers is caught too)"""
    return [
        name
        for name, info in model.model_fields.items()  # ty: ignore[unresolved-attribute]
        if any(isinstance(m, Degree) for m in info.metadata)
    ]


def _unwrapped(annotation: Any) -> Any:
    while isinstance(annotation, TypeAliasType):
        annotation = annotation.__value__
    return annotation


def is_degree_type(annotation: Any) -> bool:
    """Whether a field's type is `DegreeStep` or `DegreeStep | None`: a `Literal` of exactly the five steps"""
    annotation = _unwrapped(annotation)
    if get_origin(annotation) in (Union, types.UnionType):
        options = [a for a in get_args(annotation) if a is not type(None)]
        if len(options) != 1 or len(get_args(annotation)) != 2:
            return False
        annotation = _unwrapped(options[0])
    if get_origin(annotation) is not Literal:
        return False
    values = get_args(annotation)
    return len(values) == len(DEGREE_STEPS) and set(values) == set(DEGREE_STEPS)


def _type_text(annotation: Any) -> str:
    if isinstance(annotation, type):
        return annotation.__name__
    return repr(annotation).replace("typing.", "")


def _is_space(model: type) -> bool:
    return issubclass(model, SemanticSpace)


def faults(model: type) -> list[Fault]:
    """What is wrong with the `Degree()` fields of the class, in the order of the checks"""
    name = model.__name__
    marked = marked_fields(model)
    if not marked:
        return []
    if not _is_space(model):
        return [
            Fault(
                f"{name}.{field}: Degree() is for a field of a semantic space class (the degree of what the space "
                f"holds), and {name} is not one",
                ("not_a_space", field),
                (field,),
            )
            for field in marked
        ]
    found: list[Fault] = []
    if len(marked) > 1:
        found.append(
            Fault(
                f"{name}: {len(marked)} fields are marked Degree() ({', '.join(marked)}): a space has one degree, "
                "so one field at most is marked",
                ("many", tuple(marked)),
                # (the one added last: of a subclass, the one it adds)
                tuple(reversed(marked)),
            )
        )
    for field in marked:
        annotation = model.model_fields[field].annotation  # ty: ignore[unresolved-attribute]
        if not is_degree_type(annotation):
            found.append(
                Fault(
                    f"{name}.{field}: Degree() is on a field of the type {_type_text(annotation)}, and a degree is "
                    f"one of the five steps {', '.join(repr(s) for s in DEGREE_STEPS)}. Write `{field}: {WRITE}` "
                    "(`DegreeStep` from pangloss_models), or `DegreeStep` alone for a degree always given",
                    ("type", field),
                    (field,),
                )
            )
    meta = model._meta  # ty: ignore[unresolved-attribute]
    if meta.veridicality != 0:
        logical = meta.logical
        why = (
            f"veridical={meta.veridical}"
            if meta.veridical is not None
            else f"logical={modal_text(logical) if isinstance(logical, Modal) else repr(logical)}"
        )
        what = "asserted" if meta.veridicality == 1 else "denied"
        found.append(
            Fault(
                f"{name}.{marked[0]}: Degree() on a space whose contents are {what} ({why}): a degree is only of "
                "contents neither asserted nor denied. Take Degree() off the field, or the field out",
                ("asserted", tuple(marked), meta.veridicality),
                tuple(marked),
            )
        )
    return found


def _is_checked(model: Any) -> bool:
    # (a parametrisation, `Hypothetical[Person]`, has the fields of its generic, which is checked)
    metadata = getattr(model, "__pydantic_generic_metadata__", None) or {}
    return (
        isinstance(model, type)
        and getattr(model, "model_fields", None) is not None
        and getattr(getattr(model, "_meta", None), "fields", None) is not None
        and metadata.get("origin") is None
    )


def _own_fields(model: type) -> set[str]:
    import annotationlib

    return set(
        annotationlib.get_annotations(model, format=annotationlib.Format.FORWARDREF)
    )


def check_degree_fields(models: Iterable[type]) -> None:
    checked = [model for model in models if _is_checked(model)]
    known = set(checked)
    for model in checked:
        parent = next((c for c in model.__mro__[1:] if c in known), None)
        inherited = {f.key for f in faults(parent)} if parent is not None else set()
        own = _own_fields(model)
        for fault in faults(model):
            if fault.key in inherited:
                continue
            # (where the class itself says what is refused: the field if it declares it, else its `_meta`)
            at = next((name for name in fault.at if name in own), "_meta")
            with reported(model, at):
                raise PanglossModelError(fault.message)
