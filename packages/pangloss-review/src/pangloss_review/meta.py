"""`_review_meta`: whether the documents of a class are reviewed.

    class Letter(Document):
        _review_meta = ReviewMeta(reviewable=True)

A subclass has its parent's unless it sets its own. A class with none is not reviewed (so installing the package
changes nothing until models are marked).
"""

import contextlib
import dataclasses
import datetime
from collections.abc import Generator
from typing import Any

from pangloss_models import hooks
from pangloss_models.meta_slots import register_meta_slot
from pangloss_models.model_bases.document import Document
from pangloss_users import current_request_username

from pangloss_review import config
from pangloss_review.exceptions import PanglossSelfReviewError
from pangloss_review.status import ReviewStatus

SLOT = "_review_meta"


@dataclasses.dataclass(frozen=True)
class ReviewMeta:
    reviewable: bool = False


register_meta_slot(SLOT, ReviewMeta)


def is_reviewable(model: type) -> bool:
    """Whether the head documents of the class are checked before they are published"""
    meta = getattr(model, SLOT, None)
    return (
        isinstance(meta, ReviewMeta) and meta.reviewable and issubclass(model, Document)
    )


@contextlib.contextmanager
def with_status(status: ReviewStatus | str) -> Generator[None]:
    """Documents of reviewed classes created or updated inside the block get this status (`checked` publishes
    them), written with the document; for a script that loads data it has checked itself (it is what
    `save(review_status=...)` does for one):

        with with_status("checked"):
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
    user = current_request_username.get()
    if not config.allow_self_review():
        raise PanglossSelfReviewError(
            f"{user} cannot set the review status of what they write: "
            "self-review is not allowed"
        )
    return state_properties(status, user)


def new_head_properties(model: type) -> dict[str, Any]:
    """A new document of a reviewed class is not published, and has not been checked (unless the writer asked
    for a status). Written in the transaction that creates it."""
    if not is_reviewable(model):
        return {}
    return requested_properties(model) or {
        "published": False,
        "review_status": ReviewStatus.UNCHECKED.value,
    }


def install() -> None:
    if new_head_properties not in hooks.new_head_properties:
        hooks.new_head_properties.append(new_head_properties)
    if requested_properties not in hooks.updated_head_properties:
        hooks.updated_head_properties.append(requested_properties)


# (done as soon as a model can say it is reviewed, whether or not the app is installed)
install()
