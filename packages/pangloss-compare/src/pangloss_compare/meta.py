"""`_compare_meta`: which statements are compared, and by which fields they tell of one event
(implementation_docs/spaces-and-comparison-plan.md, step 6.1).

    class Birth(Statement):
        person: Person
        _compare_meta = CompareMeta(identifying=["person"], once_per="person")

    class Transfer(Statement):
        given_by: Agent
        given_to: Agent
        _compare_meta = CompareMeta(identifying=["given_by", "given_to"], recurs=True)

    class Ordered[T](SemanticSpace[T]):
        _meta = SemanticSpace.Meta(logical=Modal("necessity", "command"), fit="prescribes")
        _compare_meta = CompareMeta(orientation="after")       # (the default)

A subclass has its parent's setting unless it sets its own, which replaces it whole (a trait's counts for the
documents that have it). With none anywhere, a class is not compared.

- `identifying`: the fields whose entities say which event a statement tells of. A document class with none is not
  compared. Each is a relation that reaches an entity: directly, in a list, or through wrappers (`InRole[Agent]`,
  `ViaEdge`, an `Identification` of `WeightedAlternative`s), as search reaches them. A field a subclass narrows
  (`RelationConfig(subclasses_parent_fields=[FieldSubclassing("made", ...)])`) counts as the field it narrows: the
  narrowed field is no longer one of the subclass's, and the field that narrows it stands for it
  (`identifying_fields`).
- `once_per`: one of `identifying`; there is one event of the class for each entity in that field (a birth for a
  person).
- `recurs`: the same entities do this again and again (dues paid each year). Not with `once_per`.
- `compared`: `False` leaves the class out. On a semantic space, the statements inside it are left out of comparison;
  on a document class, that class, and its subclasses unless they set their own.
- `orientation`: only on a semantic space: whether what answers a prescription of the space comes `"after"` it was
  prescribed (an order) or `"before"` (D5).

Negation and strength are not here: they are the core's (`SemanticSpaceMeta`: `logical`, `veridical`, `degree`).

Refused at `initialise()`, each a `PanglossMetaError` by the name of the class that says it: the slot on anything but
a class of documents, a trait documents have, or a semantic space; on a space anything but `compared` and
`orientation`; on a document `orientation`; `identifying` that is not a list of names; a name that is not a field of
a class that has the setting, or a field that reaches no entity; `once_per` not one of `identifying`; `once_per` with
`recurs=True`.
"""

import dataclasses
from collections.abc import Sequence
from inspect import isclass
from typing import Any, Literal

from pangloss_models import ModelRegistry, PanglossMetaError, register_meta_slot
from pangloss_models.exceptions import did_you_mean
from pangloss_models.meta_slots import declared_slots

SLOT = "_compare_meta"

ORIENTATIONS = ("after", "before")

# (the fields of the setting that a semantic space may not set: what a statement inside it is, not the space's)
OF_STATEMENTS = ("identifying", "once_per", "recurs")


@dataclasses.dataclass(frozen=True)
class CompareMeta:
    identifying: Sequence[str] = ()
    """The fields whose entities say which event a statement tells of. A document class with none is not compared"""

    once_per: str | None = None
    """One of `identifying`: there is one event of the class for each entity in that field (a birth for a person)"""

    recurs: bool = False
    """The same entities do this again and again (dues paid each year)"""

    compared: bool = True
    """`False` leaves the class out (on a semantic space: the statements inside it)"""

    orientation: Literal["after", "before"] = "after"
    """Only on a semantic space: whether what answers a prescription of the space comes after it was prescribed (an
    order) or before"""


register_meta_slot(SLOT, CompareMeta)

DEFAULT = CompareMeta()

# (what a class that is not one of documents or spaces is, in a refusal)
WHAT = {
    "Entity": "an entity",
    "EdgeModel": "an edge model",
    "ReifiedRelation": "a reified relation",
    "ReifiedRelationDocument": "a reified relation",
    "Conjunction": "a conjunction",
    "Embedded": "an embedded model",
    "AnnotatedValue": "an annotated value",
}


def _kind(model: type) -> str | None:
    return getattr(model, "__metatype__", None)


def _is_generic(model: type) -> bool:
    """A generic base (`class Wrapper[T](Document)`) or a use of one (`Wrapper[Person]`)"""
    metadata = getattr(model, "__pydantic_generic_metadata__", None) or {}
    return (
        bool(metadata.get("parameters"))
        or metadata.get("origin") is not None
        or "[" in model.__name__
    )


def _setting(model: type) -> CompareMeta | None:
    """The class's setting, its parent's or a trait's, or None"""
    meta = getattr(model, SLOT, None)
    return meta if isinstance(meta, CompareMeta) else None


def _model(model: type | str) -> type:
    if isinstance(model, str):
        found = ModelRegistry._model_dict.get(model)
        if found is None:
            raise KeyError(f"no class {model!r} is registered")
        return found
    return model


def declarer(model: type) -> str:
    """The name of the class that sets the setting `model` has (itself, a parent or a trait)"""
    for cls in model.__mro__:
        if SLOT in declared_slots(cls):
            return cls.__name__
    return model.__name__


def document_classes() -> list[tuple[str, type]]:
    """The registered classes of documents a node can be of, by name: not abstract, no generics"""
    return [
        (name, model)
        for name, model in sorted(ModelRegistry._model_dict.items())
        if isclass(model)
        and _kind(model) == "Document"
        and not _is_generic(model)
        and not getattr(getattr(model, "_meta", None), "abstract", False)
    ]


def _fields_of(model: type) -> dict[str, Any]:
    fields = getattr(getattr(model, "_meta", None), "fields", None)
    return dict(fields) if fields is not None else {}


def _narrowed_by(definition: Any) -> set[str]:
    """The names of the fields above that a relation field narrows (`subclasses_parent_fields`), and those they
    narrow in turn"""
    from pangloss_models.field_definitions import FieldSubclassing

    names: set[str] = set()
    for subclassing in getattr(definition, "subclasses_parent_fields", ()):
        if isinstance(subclassing, FieldSubclassing):
            names.add(subclassing.field_name)
            names |= _narrowed_by(subclassing.subclassed_field_definition)
    return names


def _holders(model: type, name: str) -> list[str]:
    """The fields of `model` whose values count as the field `name`: itself if the class has it, and every field
    that narrows it"""
    fields = _fields_of(model)
    found = [name] if name in fields else []
    found += [
        field
        for field, definition in fields.items()
        if field != name and name in _narrowed_by(definition)
    ]
    return found


def identifying_fields(model: type | str) -> dict[str, list[str]]:
    """For each identifying field of the class's setting, the names of the fields of the class whose values count as
    it: itself, where the class has it, and each field of the class that narrows it. A narrowed field is not a field
    of the class that narrows it (its field definitions hold the narrowing field in its place), so for
    `MakingOfPicture` (`picture_made` narrows `Making.made`) this is `{"made_by": ["made_by"], "made":
    ["picture_made"]}`. Empty for a class that is not compared"""
    model = _model(model)
    meta = compare_meta(model)
    if meta is None:
        return {}
    return {name: _holders(model, name) for name in dict.fromkeys(meta.identifying)}


def compare_meta(model: type | str) -> CompareMeta | None:
    """The class's setting (its own, a parent's or a trait's), or None where it is not compared: no `identifying`,
    `compared=False`, or not a class of documents"""
    model = _model(model)
    meta = _setting(model)
    if (
        meta is None
        or _kind(model) != "Document"
        or not meta.compared
        or not meta.identifying
    ):
        return None
    return meta


def compared_classes() -> dict[str, CompareMeta]:
    """Every class of documents that is compared (not abstract, not generic), by name, with its setting"""
    return {
        name: meta
        for name, model in document_classes()
        if (meta := compare_meta(model)) is not None
    }


def related(a: type | str, b: type | str) -> bool:
    """Whether two classes are related for comparison: the same, or one an ancestor of the other (two siblings below
    one class are not)"""
    a, b = _model(a), _model(b)
    return a is b or issubclass(a, b) or issubclass(b, a)


def common_class(a: type | str, b: type | str) -> type | None:
    """The nearest class both are: the more general of two related classes (`related`), else None"""
    a, b = _model(a), _model(b)
    if issubclass(a, b):
        return b
    if issubclass(b, a):
        return a
    return None


def _space(model: type | str) -> CompareMeta:
    model = _model(model)
    if _kind(model) != "SemanticSpace":
        raise ValueError(f"{model.__name__} is not a semantic space")
    return _setting(model) or DEFAULT


def space_compared(space_model: type | str) -> bool:
    """Whether the statements inside a semantic space of this class are compared (`CompareMeta(compared=False)`
    leaves them out)"""
    return _space(space_model).compared


def orientation_of(space_model: type | str) -> str:
    """Whether what answers a prescription of a semantic space of this class comes `"after"` it was prescribed (the
    default) or `"before"`"""
    return _space(space_model).orientation


def definition_extras(model: type) -> dict[str, Any]:
    """What the interface is told of a class (`hooks.definition_extras`): `compared` where a statement of it is
    compared (`compare_meta`; abstract classes too, as the route takes one), so that the module's section asks the
    route only of those; `judgement` on each class below `EventJudgement` that is not abstract, so that the page of
    two statements finds the project's class to record one with (its `statement` and `other` say what each may
    cite); nothing for any other"""
    if _is_generic(model):
        return {}
    found: dict[str, Any] = {}
    if compare_meta(model) is not None:
        found["compared"] = True
    if is_judgement_class(model):
        found["judgement"] = True
    return found


def is_judgement_class(model: type) -> bool:
    """A class below `EventJudgement` that is not abstract: a project's class of judgement"""
    from pangloss_compare.models import EventJudgement

    meta = getattr(model, "_meta", None)
    return (
        isinstance(model, type)
        and issubclass(model, EventJudgement)
        and model is not EventJudgement
        and not getattr(meta, "abstract", False)
    )


def never_updated(model: type) -> bool:
    """(`hooks.not_updated`) a judgement is never changed once made (`EventJudgement.refuse_any_update`): the
    interface offers no Edit of one"""
    from pangloss_compare.models import EventJudgement

    return isinstance(model, type) and issubclass(model, EventJudgement)


def _check_declared(name: str, model: Any, meta: CompareMeta) -> None:
    """What a class's own setting cannot mean, whatever has it"""
    from pangloss_models.utils import model_is_trait

    kind = _kind(model)
    is_trait = model_is_trait(model)
    if kind not in ("Document", "SemanticSpace") and not is_trait:
        raise PanglossMetaError(
            f"{name}: CompareMeta is for a class of documents (or a trait documents have) or a semantic space, and "
            f"{name} is {WHAT.get(kind or '', 'neither')}"
        )
    if isinstance(meta.identifying, str) or not isinstance(meta.identifying, Sequence):
        raise PanglossMetaError(
            f"{name}: CompareMeta(identifying=...) is a list of the names of fields ([{meta.identifying!r}]), not "
            f"{meta.identifying!r}"
        )
    if not all(isinstance(field, str) for field in meta.identifying):
        raise PanglossMetaError(
            f"{name}: CompareMeta(identifying=...) is a list of the names of fields, and {list(meta.identifying)!r} "
            "has something else in it"
        )
    if meta.orientation not in ORIENTATIONS:
        raise PanglossMetaError(
            f"{name}: CompareMeta(orientation={meta.orientation!r}) is 'after' or 'before'"
        )
    if kind == "SemanticSpace":
        set_here = [
            field
            for field in OF_STATEMENTS
            if getattr(meta, field) != getattr(DEFAULT, field)
        ]
        if set_here:
            raise PanglossMetaError(
                f"{name}: on a semantic space CompareMeta takes only `compared` and `orientation`, and this sets "
                f"{', '.join(f'`{field}`' for field in set_here)}: what tells of an event is said by the classes of "
                "the statements inside it"
            )
        return
    if meta.orientation != DEFAULT.orientation:
        raise PanglossMetaError(
            f"{name}: CompareMeta(orientation=...) is only for a semantic space (whether what answers a prescription "
            "of it comes after or before), and this is a class of documents"
        )
    if meta.once_per is not None and meta.once_per not in meta.identifying:
        raise PanglossMetaError(
            f"{name}: CompareMeta(once_per={meta.once_per!r}) is not one of identifying "
            f"({', '.join(meta.identifying) or 'none'}).{did_you_mean(meta.once_per, meta.identifying)}"
        )
    if meta.once_per is not None and meta.recurs:
        raise PanglossMetaError(
            f"{name}: CompareMeta(once_per={meta.once_per!r}, recurs=True) says both that there is one for each "
            f"{meta.once_per!r} and that it happens again and again: say one"
        )


def _check_fields(name: str, model: type, meta: CompareMeta) -> None:
    """That each identifying field is a field of the class (or narrowed by one) that reaches an entity"""
    from pangloss_models.field_definitions import RelationFieldDefinition
    from pangloss_models.initialise_models.check_attributions import (
        reaches_an_entity,
    )

    said = declarer(model)
    fields = _fields_of(model)
    for field in dict.fromkeys(meta.identifying):
        holders = _holders(model, field)
        if not holders:
            narrowed = {n for d in fields.values() for n in _narrowed_by(d)}
            raise PanglossMetaError(
                f"{said}: CompareMeta(identifying=...) names {field!r}, which is not a field of {name}."
                f"{did_you_mean(field, [*fields, *narrowed])}"
            )
        for holder in holders:
            definition = fields[holder]
            if reaches_an_entity(definition):
                continue
            what = (
                "a relation that reaches no entity"
                if isinstance(definition, RelationFieldDefinition)
                else "not a relation"
            )
            as_ = "" if holder == field else f" (as {holder!r}, which narrows it)"
            raise PanglossMetaError(
                f"{said}: CompareMeta(identifying=...) names {field!r}, which in {name}{as_} is {what}. An "
                "identifying field is a relation that reaches an entity (`Person`, `list[Person]`, `Person | None`, "
                "or through a wrapper: `InRole[Person]`, `Identification[WeightedAlternative[Person]]`)"
            )


def check_meta() -> None:
    """(`ModelRegistry.after_finalise`, when the fields of every class are known) refuse what a `CompareMeta` cannot
    mean, by the name of the class that says it"""
    from pangloss_models.utils import model_is_trait

    for name, model in sorted(ModelRegistry._model_dict.items()):
        if isclass(model) and SLOT in declared_slots(model):
            _check_declared(name, model, getattr(model, SLOT))
    for name, model in sorted(ModelRegistry._model_dict.items()):
        if not isclass(model) or model_is_trait(model):
            continue
        meta = _setting(model)
        if meta is None:
            continue
        kind = _kind(model)
        if kind not in ("Document", "SemanticSpace"):
            # (what only a trait can give it: a class that says it itself was refused above)
            raise PanglossMetaError(
                f"{declarer(model)}: CompareMeta is for documents, and {name}, which has the trait, is "
                f"{WHAT.get(kind or '', 'not a document')}"
            )
        if kind == "SemanticSpace":
            if SLOT not in declared_slots(model):
                # (a trait's, or a parent space's, which was checked as a space's only if it is one)
                _check_declared(name, model, meta)
            continue
        if _is_generic(model):
            continue
        if getattr(getattr(model, "_meta", None), "abstract", False):
            continue
        if compare_meta(model) is not None:
            _check_fields(name, model, meta)


def install() -> None:
    if check_meta not in ModelRegistry.after_finalise:
        ModelRegistry.after_finalise.append(check_meta)


# (done as soon as a model can say it, whether or not the app is installed)
install()
