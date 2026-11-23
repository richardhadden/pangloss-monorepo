"""The models of the library.

`WeightedAlternative[Person]` is one of several people, not known which, each with how likely it is the one meant, in
per cent (the percentages add up to 100, and the interface keeps them to it).

`Identification[Person]` is a name in a source that someone has identified: who it is (or, with a
`WeightedAlternative`, who it could be), and who said so. `IdentificationByToolchain[Person]` is one that a toolchain
suggested, for a person to confirm (with `pangloss-review`, a task until someone does: it then becomes an
`Identification` by that person).

`IdentificationFromText[Person]` is an identification that keeps what the source wrote (`text`: "Smith", as it stands
there), and `IdentificationByToolchainFromText[Person]` a toolchain's suggestion that does, which becomes one when it
is confirmed.

Each class of suggestion is checked at `initialise()` against the class it becomes (`check_confirmed_classes`, and
`check_fields_take_confirmed` once the fields are made).
"""

import contextvars
import dataclasses
import warnings
from typing import Annotated, Any, ClassVar
from uuid import UUID

from annotated_types import Ge, Le, MaxLen, MinLen
from pangloss_derived import DerivedMeta
from pangloss_library.identity import IdentityClaim
from pangloss_models import (
    Conjunction,
    EdgeModel,
    ModelRegistry,
    PanglossModelError,
    PanglossModelWarning,
    ReifiedRelation,
    ReifiedRelationDocument,
    SumsTo,
    ViaEdge,
    before_update,
    create_validator,
    update_validator,
)
from pangloss_models.creators import requested_creators
from pydantic import AnyHttpUrl

# How the interface shows these, if it is installed (a client of the API, with the SDK, does not have it): the
# percentage as a slider; the alternatives on the item page as their own card (no head, each with its likelihood at
# the end of its chip, the name of the field only for several)
try:
    from pangloss_interface import InterfaceMeta, Slider
except ImportError:
    SLIDER = ()
    INTERFACE_META = {}
    IDENTIFICATION_META = {}
    SUGGESTION_META = {}
    SUGGESTION_FROM_TEXT_META = {}
else:
    SLIDER = (Slider(unit="%"),)
    INTERFACE_META = {
        "_interface_meta": InterfaceMeta(
            collapse=True, view_card="pangloss_library:WeightedAlternativeCard"
        )
    }
    # (on the item page, one person is shown as their chip, then who identified them; a form does not ask who
    # identified it, which the server says, nor its URIs, which are a toolchain's: the library's interface module
    # shows them in the form, not to be changed)
    IDENTIFICATION_META = {
        "_interface_meta": InterfaceMeta(
            collapse=True, hide_on_forms=("identified_by", "uris")
        )
    }
    SUGGESTION_META = {
        "_interface_meta": InterfaceMeta(
            collapse=True,
            hide_on_forms=("identified_by", "toolchain_version", "uris"),
        )
    }
    # (and what the source wrote, which the toolchain read: shown in the form by the module, not to be changed)
    SUGGESTION_FROM_TEXT_META = {
        "_interface_meta": InterfaceMeta(
            collapse=True,
            hide_on_forms=("identified_by", "toolchain_version", "uris", "text"),
        )
    }


class Likelihood(EdgeModel):
    """How likely it is that this is the one meant, out of the alternatives (1 to 100, in per cent)"""

    percent: Annotated[int, Ge(1), Le(100), *SLIDER]


class WeightedAlternative[T](Conjunction):
    """One of several things, not known which, each with how likely it is the one meant: the percentages add up
    to 100"""

    # (one of them, not known which: a derived relation takes one alternative at a time, never two together; and
    # what is derived through "A (60) or B (40)" is not said plainly of A, nor of B: the alternative is in its context.
    # A conjunction that says nothing is read through as if it were not there)
    _derived_meta = DerivedMeta(derivation="qualify", exclusive=True)
    locals().update(INTERFACE_META)

    alternatives: Annotated[list[ViaEdge[T, Likelihood]], MinLen(1), SumsTo("percent")]


def writer() -> str:
    """Who is writing: the first person a write names as its maker (an admin's upload for others), or else the user
    of the request"""
    for creator in requested_creators.get() or ():
        if creator.kind == "user":
            return creator.username
    # (imported here: this runs where the document is written, and a client of the API, which has the models, does
    # not have `pangloss_users`)
    from pangloss_users import current_request_username

    return current_request_username.get()


class Identification[T](ReifiedRelation[T]):
    """A name in the source that has been identified: the source says "Smith", and this says who that is, or (the
    target being a `WeightedAlternative`) which people it could be"""

    locals().update(IDENTIFICATION_META)

    identified_by: str | None = None
    """The username of who identified it: said by the server (whoever first saves it), not asked in a form"""
    target: Annotated[list[T], MinLen(1), MaxLen(1)]
    uris: list[AnyHttpUrl] = []
    """URIs for who it is, as a toolchain gave them with its suggestion. They belong to the one who is identified:
    an identification of one candidate gives them to that candidate (with `pangloss-review`), and one that a
    person confirmed with several candidates still open keeps them here until it is of one"""

    @create_validator
    @update_validator
    def say_who_identified_it(self):
        if not self.identified_by:
            self.identified_by = self.identifier()

    def identifier(self) -> str:
        return writer()

    @before_update
    async def note_if_confirmed(self: Any, previous: Any):
        """A suggestion of a toolchain that is written again as an identification (the same node: its id is kept)
        has been confirmed, by whoever saves the document. That is noted (`confirmed_in_write`) for what acts on
        it once the write is made (`pangloss-review` gives the URIs to the one who was identified, and tells
        `hooks.confirmed`): every one, with URIs or not. So is an identification written with URIs it still keeps
        (confirmed with several candidates): it may now be of one, but that confirms nothing."""
        if _is_suggestion(type(self)):
            return
        was = getattr(previous, "type", None)
        if not _descends(
            ModelRegistry._model_dict.get(str(was)), "IdentificationByToolchain"
        ):
            was = None
        named = [*(getattr(previous, "uris", None) or ()), *(self.uris or ())]
        uris = list(dict.fromkeys(str(uri) for uri in named))
        if uris or was is not None:
            confirmed_in_write.set(
                [
                    *(confirmed_in_write.get() or ()),
                    ConfirmedInWrite(self.id, uris, was, self.type, writer()),
                ]
            )


@dataclasses.dataclass(frozen=True)
class ConfirmedInWrite:
    """An identification that a write makes of a suggestion, or that has URIs to give: the node, and the URIs the
    toolchain gave for who it is"""

    id: UUID
    uris: list[str]
    was: str | None = None
    """The class of the suggestion it was, when the write confirms one (`None`: an identification that was one
    already, written again with URIs it keeps)"""
    type: str | None = None
    """The class it is written as"""
    by: str | None = None
    """Who is writing it (`writer`): who confirms it"""


# What the write being made confirms (noted before it is written: whoever reads it takes it, and checks that the
# write was made)
confirmed_in_write: contextvars.ContextVar[list[ConfirmedInWrite] | None] = (
    contextvars.ContextVar("confirmed_in_write", default=None)
)


def _is_suggestion(model: type) -> bool:
    """Whether a generated model is of a class of suggestions (`IdentificationByToolchain`, or one below it)"""
    return _descends(getattr(model, "_owner", model), "IdentificationByToolchain")


class IdentificationByToolchain[T](Identification[T]):
    """An identification that a toolchain suggested, for a person to check: `identified_by` is the toolchain (a
    user of kind `toolchain`). A person who confirms it makes it an `Identification` of their own.

    A project may subclass it, to say more of a suggestion. A subclass names the class that a confirmed one becomes
    (`confirmed_as`: a subclass of `Identification` that is not a suggestion, or its name), which keeps the fields
    the two have in common; a field that takes the subclass has to take that class too:

        class Reading[T](Identification[T]):
            note: str | None = None

        class SuggestedReading[T](IdentificationByToolchain[T]):
            confirmed_as = Reading
            note: str | None = None
            model: str | None = None        # (of the suggestion only: not kept)
    """

    # (a machine's guess, not yet looked at: what is derived through it is not plain, as it is through an
    # identification a person made, which is read through as if it were not there)
    _derived_meta = DerivedMeta(derivation="qualify")

    # (all of them are read, by `pangloss-review`: the identifications to confirm)
    _meta = ReifiedRelation.Meta(label_index=True)
    confirmed_as: ClassVar[type | str] = "Identification"
    locals().update(SUGGESTION_META)

    toolchain_version: str | None = None

    def toolchain_run(self) -> Any | None:
        """The toolchain that the write names as a maker of the document, if it names one"""
        return next(
            (c for c in requested_creators.get() or () if c.kind == "toolchain"), None
        )

    def identifier(self) -> str:
        run = self.toolchain_run()
        if run is None:
            raise ValueError(
                "An IdentificationByToolchain needs its toolchain: give identified_by, or write the document as "
                "made by one (save(toolchain=...))"
            )
        return run.username

    @create_validator
    @update_validator
    def say_which_version(self):
        run = self.toolchain_run()
        if self.toolchain_version is None and run is not None:
            if run.username == self.identified_by:
                self.toolchain_version = run.version


def confirmed_class_name(model: type) -> str:
    """The name of the class that a confirmed suggestion of this class becomes (`confirmed_as`)"""
    named = getattr(model, "confirmed_as", "Identification")
    return named if isinstance(named, str) else named.__name__


def _descends(model: Any, ancestor: str) -> bool:
    return any(base.__name__ == ancestor for base in getattr(model, "__mro__", ()))


class IdentificationFromText[T](Identification[T]):
    """An identification that keeps what the source wrote: the source says "Smith" (`text`), and this says who that
    is. A person may make one in a form; a confirmed `IdentificationByToolchainFromText` becomes one"""

    text: str
    """What the source wrote, as it stands there"""


class IdentificationByToolchainFromText[T](IdentificationByToolchain[T]):
    """A toolchain's suggestion of who a name in the source is, which keeps what the source wrote (`text`, as the
    toolchain read it: not changed in a form). Confirmed, it becomes an `IdentificationFromText` with the same text"""

    confirmed_as = IdentificationFromText
    # (its own label index, as every class of suggestion has. And it reads, in the label of what holds it, as what the
    # source wrote, not as the toolchain's guesses: a head whose label template names the field keeps the name the
    # source wrote until a person confirms who it is, `pangloss-reconcile`'s worker writing one in a stand-in's place
    # changes no label. Confirmed, it is an `IdentificationFromText`, which reads as who was identified)
    _meta = ReifiedRelation.Meta(label_index=True, label_template="{text}")
    locals().update(SUGGESTION_FROM_TEXT_META)

    text: str
    """What the source wrote, as it stands there"""


# What a confirmation does not take from a suggestion (`pangloss-review` makes the identification without them):
# what it is, who made it, what it is of, and what is the toolchain's. The other fields of the class it becomes are
# taken from the suggestion, so the two have to agree on them
NOT_KEPT = frozenset(
    {"type", "id", "identified_by", "target", "toolchain_version", "uris"}
)


def _declared_fields(model: Any) -> dict[str, Any]:
    return dict(getattr(model, "model_fields", {}))


def _as_declared(field: Any) -> tuple[Any, str]:
    """A declared field's type, as the two classes can be compared by: its annotation and what is `Annotated` on
    it (by how it reads: a marker need not compare equal to another made the same way)"""
    return field.annotation, repr(list(field.metadata))


def check_confirmed_classes() -> None:
    """(before the models are initialised) Every class of suggestion names a class to become that there is, that is
    an identification, and that is not itself a suggestion; that class needs no field the suggestion lacks (a
    confirmation keeps only the fields the two have), and the fields the two have are of the same type"""
    models = ModelRegistry._model_dict
    for name, model in sorted(models.items()):
        if not name.isidentifier() or not _descends(model, "IdentificationByToolchain"):
            continue
        becomes = confirmed_class_name(model)
        found = models.get(becomes)
        if found is None:
            raise PanglossModelError(
                f"{name}: confirmed_as names {becomes!r}, which is not a model: name a subclass of Identification"
            )
        if not _descends(found, "Identification") or _descends(
            found, "IdentificationByToolchain"
        ):
            raise PanglossModelError(
                f"{name}: confirmed_as is {becomes}, which a confirmed suggestion cannot become: it has to be a "
                "subclass of Identification that is not an IdentificationByToolchain"
            )
        own = _declared_fields(model)
        for field_name, field in sorted(_declared_fields(found).items()):
            if field_name in NOT_KEPT:
                continue
            if field_name not in own:
                if field.is_required():
                    raise PanglossModelError(
                        f"{name}: a confirmed {name} becomes a {becomes}, whose field {field_name!r} has no default "
                        f"and is not a field of {name} (a confirmation keeps only the fields the two have): give "
                        f"{name} the field {field_name!r}, or give {becomes}.{field_name} a default"
                    )
                continue
            if _as_declared(own[field_name]) != _as_declared(field):
                raise PanglossModelError(
                    f"{name}: the field {field_name!r} is {_type_text(own[field_name])} in {name} and "
                    f"{_type_text(field)} in {becomes}, the class it becomes (a confirmation keeps the value): "
                    f"declare {field_name!r} with the same type in both"
                )


def _type_text(field: Any) -> str:
    annotation = field.annotation
    text = (
        annotation.__name__
        if isinstance(annotation, type) and not getattr(annotation, "__args__", None)
        else str(annotation).replace("typing.", "")
    )
    return f"`{text}`" + (f" {list(field.metadata)}" if field.metadata else "")


def _option_levels(options: Any) -> Any:
    """The options of a relation, and those of each type parameter of a wrapper among them (`InRole[...]`), each
    set by itself: what one place of the field takes"""
    yield options
    for option in options:
        for parameter in (
            getattr(option, "parameter_type_options", None) or {}
        ).values():
            yield from _option_levels(parameter.type_options)


def _declarer(model: Any, field_name: str) -> Any:
    """The most basic registered class that has the field: where it was declared"""
    for cls in reversed(getattr(model, "__mro__", ())):
        fields = getattr(getattr(cls, "_meta", None), "fields", None)
        if (
            cls.__name__ in ModelRegistry._model_dict
            and fields is not None
            and field_name in fields
        ):
            return cls
    return model


def check_fields_take_confirmed() -> None:
    """(`ModelRegistry.after_finalise`, when the fields are made) A field that takes a class of suggestion and not
    the class it becomes would refuse it once confirmed: a warning, as a project's fields may say only
    `IdentificationByToolchain[...]` (one for each field, with the classes to add)"""
    models = ModelRegistry._model_dict
    warned: set[tuple[str, str]] = set()
    for name, model in sorted(models.items()):
        fields = getattr(getattr(model, "_meta", None), "fields", None)
        if not name.isidentifier() or fields is None:
            continue
        for field_name, definition in sorted(fields.relation_fields.items()):
            missing: dict[str, str] = {}
            for options in _option_levels(definition.type_options):
                taken = {
                    option.base_type.__name__
                    for option in options
                    if getattr(option, "base_type", None) is not None
                }
                for suggestion in sorted(taken):
                    if not _descends(
                        models.get(suggestion), "IdentificationByToolchain"
                    ):
                        continue
                    becomes = confirmed_class_name(models[suggestion])
                    if becomes not in taken:
                        missing[suggestion] = becomes
            if not missing:
                continue
            declarer = _declarer(model, field_name)
            if (declarer.__name__, field_name) in warned:
                continue
            warned.add((declarer.__name__, field_name))
            pairs = "; ".join(
                f"{suggestion} becomes {becomes}"
                for suggestion, becomes in sorted(missing.items())
            )
            # (a class whose parent is added too is taken with it: a field takes the subclasses of what it names)
            wanted = set(missing.values())
            to_add = " and ".join(
                sorted(
                    becomes
                    for becomes in wanted
                    if not any(
                        other != becomes and _descends(models.get(becomes), other)
                        for other in wanted
                    )
                )
            )
            warnings.warn(
                PanglossModelWarning(
                    f"{declarer.__name__}.{field_name} takes a suggestion that it does not take once it is confirmed "
                    f"({pairs}): confirming one would be refused. Add {to_add} to what {field_name!r} takes",
                    model=declarer,
                    member=field_name,
                ),
                stacklevel=2,
            )


def _registered_once(hooks: list, check: Any) -> None:
    # (once, though the tests run this module again for a fresh registry)
    hooks[:] = [
        hook
        for hook in hooks
        if getattr(hook, "__qualname__", None) != check.__qualname__
        or getattr(hook, "__module__", None) != __name__
    ] + [check]


_registered_once(ModelRegistry.before_finalise, check_confirmed_classes)
_registered_once(ModelRegistry.after_finalise, check_fields_take_confirmed)


def suggestion_classes() -> list[str]:
    """(`hooks.unconfirmed`) Every class of suggestion, by its name (`IdentificationByToolchain` and the classes below
    it, a project's too: each has its own label): a guess no person has confirmed, so what is below one is not
    evidence (the graph part of similarity does not walk it, reconciliation does not count what it names) until it is
    confirmed, as an `Identification`"""
    return sorted(
        name
        for name, model in ModelRegistry._model_dict.items()
        # (the classes as declared: one bound to what it holds, `Name[...]`, is written with the label of its class)
        if name.isidentifier() and _descends(model, "IdentificationByToolchain")
    )


def _register_suggestion_classes() -> None:
    from pangloss_models import hooks as model_hooks

    _registered_once(model_hooks.unconfirmed, suggestion_classes)


_register_suggestion_classes()


class SameEntity[T](ReifiedRelationDocument[T]):
    """A claim that two entities are one and the same: "the John Smith of this charter is the John Smith of that
    one". A statement like any other: it has a label, goes where a project's statements go
    (`statements: list[Statement | SameEntity[Person]]`), and in a semantic space says what the space says
    (`Negative[SameEntity[Person]]`: they are *not* the same).

    The two stay two. If someone later merges them (`Person.merge`), the claim still names both, the second as
    merged into the first: its relation is an `IdentityClaim()`, which a merge leaves where it is."""

    target: Annotated[list[T], MinLen(2), MaxLen(2), IdentityClaim()]
    argument: str | None = None
    """Why they are taken to be the same, in words"""
