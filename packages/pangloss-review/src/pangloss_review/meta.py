"""`_review_meta`: whether the documents of a class are reviewed, and whether an entity class may be left unreconciled.

    class Letter(Document):
        _review_meta = ReviewMeta(reviewable=True)

    class Person(Entity):
        _review_meta = ReviewMeta(allow_unreconciled=True)

A subclass has its parent's unless it sets its own. A class with none is not reviewed (so installing the package
changes nothing until models are marked).

`allow_unreconciled`: every relation that takes the entity class also takes an `Unreconciled` (`pangloss_review.models`)
in its place, for someone a source names who has not been identified. One field refuses it with a marker:
`Annotated[Person, NoUnreconciled()]`.

`reconcile_together` (on the class of a head document): which other unreconciled mentions are offered to be reconciled
with one of this document's in one go: the names of fields of the head that must hold the same entities
(`("source",)`), or a function of the two head views that says whether they go together.
"""

import contextlib
import dataclasses
import datetime
from collections.abc import Callable, Generator
from typing import Any

from pangloss_models import (
    Document,
    Entity,
    ModelRegistry,
    PanglossModelError,
    hooks,
    register_meta_slot,
)
from pangloss_models.markers import FieldMarker

from pangloss_review import config
from pangloss_review.exceptions import PanglossAssignmentError, PanglossSelfReviewError
from pangloss_review.status import ReviewStatus

SLOT = "_review_meta"


type TogetherRule = Callable[[Any, Any], bool]


@dataclasses.dataclass(frozen=True)
class ReviewMeta:
    reviewable: bool = False
    allow_unreconciled: bool = False
    reconcile_together: tuple[str, ...] | TogetherRule | None = None


register_meta_slot(SLOT, ReviewMeta)


class NoUnreconciled(FieldMarker):
    """On a relation: it does not take an `Unreconciled` in place of an entity, whatever the entity's class allows
    (`Annotated[Person, NoUnreconciled()]`)"""


UNRECONCILED = "Unreconciled"


def allows_unreconciled(model: type) -> bool:
    """Whether a relation that takes the entity class also takes an `Unreconciled` in its place"""
    meta = getattr(model, SLOT, None)
    return (
        isinstance(meta, ReviewMeta)
        and meta.allow_unreconciled
        and issubclass(model, Entity)
    )


def check_unreconciled(value: Any, names: frozenset[str]) -> None:
    """(`hooks.StandIn.check`) What an `Unreconciled` says it is must be one of the entity classes of the relation
    that may be left unreconciled"""
    if value.unreconciled_type not in names:
        raise ValueError(
            f"an Unreconciled here stands for {' or '.join(sorted(names))}, not "
            f"{value.unreconciled_type!r} (unreconciled_type)"
        )


def check_unreconciled_is_declared() -> None:
    """(before the models are initialised) A class that allows unreconciled mentions needs the `Unreconciled` model.
    On a server it is declared by `pangloss_review` being an installed app (which also gives its migrations and
    routes), and it is an error if it is not. A client of the API (the SDK) has only the models,
    and the project's say `ReviewMeta` without importing `pangloss_review.models`: there it is imported here"""
    models = ModelRegistry._model_dict
    if UNRECONCILED in models:
        return
    allowing = sorted(
        name for name, model in models.items() if allows_unreconciled(model)
    )
    if not allowing:
        return
    from pangloss_core import settings

    # (a server's settings are `BaseSettings`; a client's only `ClientSettings`)
    if isinstance(getattr(settings, "SETTINGS", None), settings.BaseSettings):
        raise PanglossModelError(
            f"{', '.join(allowing)}: ReviewMeta(allow_unreconciled=True) needs the Unreconciled model of "
            "pangloss_review: add 'pangloss_review' to INSTALLED_APPS (or import pangloss_review.models)"
        )
    import pangloss_review.models  # noqa: F401


def reconcile_rule(model: type) -> tuple[str, ...] | TogetherRule | None:
    meta = getattr(model, SLOT, None)
    return meta.reconcile_together if isinstance(meta, ReviewMeta) else None


def is_reviewable(model: type) -> bool:
    """Whether the head documents of the class are checked before they are published"""
    meta = getattr(model, SLOT, None)
    return (
        isinstance(meta, ReviewMeta) and meta.reviewable and issubclass(model, Document)
    )


@contextlib.contextmanager
def assigned_to(username: str) -> Generator[None]:
    """Documents of reviewed classes created inside the block are given to this user to review (what
    `save(review_assigned_to=...)` does for one)"""
    with hooks.requesting_review_assignee(username):
        yield


@contextlib.contextmanager
def with_status(status: ReviewStatus | str) -> Generator[None]:
    """Documents of reviewed classes created or updated inside the block get this status (`published`
    publishes them), written with the document; for a script that loads data it has checked itself (it is what
    `save(review_status=...)` does for one):

        with with_status("published"):
            await Letter.Create(...).save()
    """
    with hooks.requesting_review_status(ReviewStatus(status).value):
        yield


def state_properties(status: ReviewStatus, user: str) -> dict[str, Any]:
    return {
        "review_status": status.value,
        "published": status.published,
        "reviewed_by": user,
        "reviewed_at": datetime.datetime.now(datetime.UTC),
    }


def requested_properties(model: type) -> dict[str, Any]:
    """What a write must set for the status asked for, if there is one and the class is reviewed. The writer is
    the author, so with `REVIEW_ALLOW_SELF_REVIEW` false the request is refused, as setting the status is."""
    asked = hooks.requested_review_status.get()
    if asked is None or not is_reviewable(model):
        return {}
    status = ReviewStatus(asked)
    # (imported here: this runs where the document is written, and a client of the API, which has the models
    # and so this module, does not have `pangloss_users`)
    from pangloss_users import current_request_username

    user = current_request_username.get()
    if not config.allow_self_review():
        raise PanglossSelfReviewError(
            f"{user} cannot set the review status of what they write: "
            "self-review is not allowed"
        )
    return state_properties(status, user)


def assignment_properties(assignee: str | None, by: str) -> dict[str, Any]:
    """What says who is to review a document (None: no one), who said so, and when"""
    return {
        "review_assigned_to": assignee,
        "review_assigned_by": by if assignee else None,
        "review_assigned_at": datetime.datetime.now(datetime.UTC) if assignee else None,
    }


def requested_assignment(model: type) -> dict[str, Any]:
    """What a create must set for the reviewer asked for (`save(review_assigned_to=...)`), if there is one and the
    class is reviewed. Only an admin gives a document to someone else; anyone takes their own."""
    assignee = hooks.requested_review_assignee.get()
    if assignee is None or not is_reviewable(model):
        return {}
    from pangloss_users import current_request_is_admin, current_request_username

    user = current_request_username.get()
    if assignee != user and not current_request_is_admin.get():
        raise PanglossAssignmentError(
            f"Only an admin can give a document to someone else to review ({assignee})"
        )
    return assignment_properties(assignee, user)


def new_head_properties(model: type) -> dict[str, Any]:
    """A new document of a reviewed class is not published, and has not been checked (unless the writer asked
    for a status); and is given to whoever the writer asked to review it. Written in the transaction that creates
    it."""
    if not is_reviewable(model):
        return {}
    state = requested_properties(model) or {
        "published": False,
        "review_status": ReviewStatus.UNCHECKED.value,
    }
    return {**state, **requested_assignment(model)}


STAND_IN = hooks.StandIn(
    document=UNRECONCILED,
    stands_for=allows_unreconciled,
    check=check_unreconciled,
    refused_by=NoUnreconciled,
)


def install() -> None:
    if new_head_properties not in hooks.new_head_properties:
        hooks.new_head_properties.append(new_head_properties)
    if requested_properties not in hooks.updated_head_properties:
        hooks.updated_head_properties.append(requested_properties)
    if STAND_IN not in hooks.stand_ins:
        hooks.stand_ins.append(STAND_IN)
    if check_unreconciled_is_declared not in ModelRegistry.before_finalise:
        ModelRegistry.before_finalise.append(check_unreconciled_is_declared)


# (done as soon as a model can say it is reviewed, whether or not the app is installed)
install()
