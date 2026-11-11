"""The models of the library.

`WeightedAlternative[Person]` is one of several people, not known which, each with how likely it is the one meant, in
per cent (the percentages add up to 100, and the interface keeps them to it).

`Identification[Person]` is a name in a source that someone has identified: who it is (or, with a
`WeightedAlternative`, who it could be), and who said so. `IdentificationByToolchain[Person]` is one that a toolchain
suggested, for a person to confirm (with `pangloss-review`, a task until someone does: it then becomes an
`Identification` by that person).
"""

import contextvars
import dataclasses
from typing import Annotated, Any, ClassVar
from uuid import UUID

from annotated_types import Ge, Le, MaxLen, MinLen
from pangloss_derived import DerivedMeta
from pangloss_models import (
    Conjunction,
    EdgeModel,
    ModelRegistry,
    PanglossModelError,
    ReifiedRelation,
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


class Likelihood(EdgeModel):
    """How likely it is that this is the one meant, out of the alternatives (1 to 100, in per cent)"""

    percent: Annotated[int, Ge(1), Le(100), *SLIDER]


class WeightedAlternative[T](Conjunction):
    """One of several things, not known which, each with how likely it is the one meant: the percentages add up
    to 100"""

    # (one of them, not known which: a derived relation takes one alternative at a time, never two together)
    _derived_meta = DerivedMeta(exclusive=True)
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
        it once the write is made (`pangloss-review` gives the URIs to the one who was identified). So is an
        identification written with URIs it still keeps (confirmed with several candidates): it may now be of
        one."""
        if _is_suggestion(type(self)):
            return
        named = [*(getattr(previous, "uris", None) or ()), *(self.uris or ())]
        uris = list(dict.fromkeys(str(uri) for uri in named))
        if uris:
            confirmed_in_write.set(
                [
                    *(confirmed_in_write.get() or ()),
                    ConfirmedInWrite(self.id, uris),
                ]
            )


@dataclasses.dataclass(frozen=True)
class ConfirmedInWrite:
    """An identification that a write makes of a suggestion, or that has URIs to give: the node, and the URIs the
    toolchain gave for who it is"""

    id: UUID
    uris: list[str]


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


def check_confirmed_classes() -> None:
    """(before the models are initialised) Every class of suggestion names a class to become that there is, that is
    an identification, and that is not itself a suggestion"""
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


# (once, though the tests run this module again for a fresh registry)
ModelRegistry.before_finalise[:] = [
    check
    for check in ModelRegistry.before_finalise
    if getattr(check, "__qualname__", None) != check_confirmed_classes.__qualname__
    or getattr(check, "__module__", None) != __name__
] + [check_confirmed_classes]
