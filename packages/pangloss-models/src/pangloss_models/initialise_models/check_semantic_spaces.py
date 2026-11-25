"""The checks at `initialise()` of what a semantic space class says of its contents (`SemanticSpaceMeta`): that
`veridical`, `unary` and `degree` do not contradict `logical` or each other. They read what is set (`None` where the
class says nothing), not what follows from it. A class is refused only for what it says itself: a fault it inherits
whole is its parent's. And a warning where two flavours of `Modal` differ only in case"""

import warnings
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pangloss_models.diagnostics import reported
from pangloss_models.exceptions import PanglossModelError, PanglossModelWarning
from pangloss_models.model_bases.semantic_space import (
    Modal,
    SemanticSpace,
    SemanticSpaceMeta,
)

# The fix of each value that can be refused (`pangloss_models.diagnostics.FIXES`): `logical` is kept, the other changed
FIX_OF = {
    "veridical": "space_veridical",
    "unary": "space_unary",
    "degree": "space_degree",
}


@dataclass(frozen=True)
class Fault:
    message: str
    # (the value that is to change, and all the values it is between)
    keyword: str
    between: tuple[str, ...]


def modal_text(modal: Modal) -> str:
    """As it would be written"""
    of_not = ", of_not=True" if modal.of_not else ""
    return f'Modal("{modal.force}", "{modal.flavour}"{of_not})'


def _logical_text(logical: Any) -> str:
    return modal_text(logical) if isinstance(logical, Modal) else repr(logical)


def faults(model: type) -> list[Fault]:
    """What the class's meta says that contradicts itself, in the order of the checks"""
    meta: SemanticSpaceMeta = model._meta  # ty: ignore[unresolved-attribute]
    name = model.__name__
    veridical, logical, unary, degree = (
        meta.veridical,
        meta.logical,
        meta.unary,
        meta.degree,
    )
    modal = logical if isinstance(logical, Modal) else None
    found: list[Fault] = []

    if logical == "not" and veridical is not None and veridical != -1:
        found.append(
            Fault(
                f"{name}: logical='not' with veridical={veridical}: what is under a 'not' is denied, so veridical "
                "can only be -1 (or left out)",
                "veridical",
                ("logical", "veridical"),
            )
        )
    if modal is not None and modal.force == "possibility":
        if veridical is not None and veridical != 0:
            found.append(
                Fault(
                    f"{name}: logical={modal_text(modal)} with veridical={veridical}: what may be so is neither "
                    "asserted nor denied, so veridical can only be 0 (or left out)",
                    "veridical",
                    ("logical", "veridical"),
                )
            )
    elif modal is not None and veridical == -1 and not modal.of_not:
        found.append(
            Fault(
                f"{name}: logical={modal_text(modal)} with veridical=-1: only what is necessarily not "
                "(a necessity with of_not=True) is denied, so veridical can only be 1 or 0 (or left out)",
                "veridical",
                ("logical", "veridical"),
            )
        )
    if (
        modal is not None
        and modal.force == "necessity"
        and modal.of_not
        and veridical == 1
    ):
        found.append(
            Fault(
                f"{name}: logical={modal_text(modal)} with veridical=1: what is necessarily not is not asserted, "
                "so veridical can only be -1 or 0 (or left out)",
                "veridical",
                ("logical", "veridical"),
            )
        )
    if unary is False and (logical == "not" or (modal is not None and modal.of_not)):
        found.append(
            Fault(
                f"{name}: logical={_logical_text(logical)} with unary=False: of two items under a 'not', neither is "
                "denied by itself, so the space holds one item: unary can only be True (or left out)",
                "unary",
                ("logical", "unary"),
            )
        )
    if degree is not None and meta.veridicality != 0:
        why = (
            f"veridical={veridical}"
            if veridical is not None
            else f"logical={_logical_text(logical)}"
        )
        what = "asserted" if meta.veridicality == 1 else "denied"
        found.append(
            Fault(
                f"{name}: degree={degree!r}, but its contents are {what} ({why}): a degree is only of contents "
                "neither asserted nor denied. Leave degree out",
                "degree",
                ("logical", "veridical", "degree"),
            )
        )
    return found


def _parent_meta(model: type) -> SemanticSpaceMeta:
    """The meta the class would have if it said nothing itself"""
    for parent in model.__mro__[1:]:
        if isinstance(meta := parent.__dict__.get("_meta"), SemanticSpaceMeta):
            return meta
    return SemanticSpaceMeta()


def correction(model: type, keyword: str) -> tuple[Any, bool]:
    """What `keyword` is to be for the class's meta to say nothing against `logical`, and whether leaving it out (and
    so inheriting it) gives that"""
    meta: SemanticSpaceMeta = model._meta  # ty: ignore[unresolved-attribute]
    if keyword == "veridical":
        value: Any = -1 if meta.logical == "not" else 0
    elif keyword == "unary":
        value = True
    else:
        value = None
    inherited = getattr(_parent_meta(model), keyword)
    return value, inherited is None or inherited == value


def _is_space(model: Any) -> bool:
    return (
        isinstance(model, type)
        and issubclass(model, SemanticSpace)
        and model is not SemanticSpace
        # (a parametrisation, `Not[Person]`, is its generic, which is checked)
        and model.__pydantic_generic_metadata__["origin"] is None
    )


def _parent(model: type, checked: set[type]) -> type | None:
    return next((c for c in model.__mro__[1:] if c in checked), None)


def check_semantic_space(model: type, parent: type | None) -> None:
    for fault in faults(model):
        # (a fault the class inherits whole is reported of the parent)
        if parent is not None and all(
            getattr(model._meta, name) == getattr(parent._meta, name)  # ty: ignore[unresolved-attribute]
            for name in fault.between
        ):
            continue
        raise PanglossModelError(fault.message, fix=FIX_OF[fault.keyword])


def _warn_of_flavours(spaces: list[type], checked: set[type]) -> None:
    """Flavours are compared as they are written: two that differ only in case are two modalities, and likely a slip"""
    by_folded: dict[str, dict[str, list[type]]] = {}
    for model in spaces:
        logical = model._meta.logical  # ty: ignore[unresolved-attribute]
        if not isinstance(logical, Modal):
            continue
        parent = _parent(model, checked)
        inherited = parent._meta.logical if parent is not None else None  # ty: ignore[unresolved-attribute]
        users = by_folded.setdefault(logical.flavour.casefold(), {}).setdefault(
            logical.flavour, []
        )
        # (a subclass of the same flavour is the class that set it)
        if not (isinstance(inherited, Modal) and inherited.flavour == logical.flavour):
            users.append(model)
    for flavours in by_folded.values():
        if len(flavours) < 2:
            continue
        written = sorted(flavours)
        uses = "; ".join(
            f"{flavour!r} by {', '.join(sorted(m.__name__ for m in flavours[flavour]))}"
            for flavour in written
        )
        first = min(flavours[written[0]], key=lambda m: m.__name__)
        warnings.warn(
            PanglossModelWarning(
                f"The flavours {' and '.join(repr(f) for f in written)} of Modal differ only in case, and so are "
                f"different modalities ({uses}). Write them alike if they are to be one",
                model=first,
                member="_meta",
            ),
            stacklevel=2,
        )


def check_semantic_spaces(models: Iterable[type]) -> None:
    spaces = [model for model in models if _is_space(model)]
    checked = set(spaces)
    for model in spaces:
        with reported(model, "_meta"):
            check_semantic_space(model, _parent(model, checked))
    _warn_of_flavours(spaces, checked)
