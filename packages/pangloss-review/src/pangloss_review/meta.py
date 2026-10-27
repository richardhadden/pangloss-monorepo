"""`_review_meta`: whether the documents of a class are reviewed.

    class Letter(Document):
        _review_meta = ReviewMeta(reviewable=True)

A subclass has its parent's unless it sets its own. A class with none is not reviewed (so installing the package
changes nothing until models are marked).
"""

import dataclasses
from typing import Any

from pangloss_models import hooks
from pangloss_models.meta_slots import register_meta_slot
from pangloss_models.model_bases.document import Document

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


def new_head_properties(model: type) -> dict[str, Any]:
    """A new document of a reviewed class is not published, and has not been checked. (Written in the
    transaction that creates it.)"""
    if is_reviewable(model):
        return {"published": False, "review_status": ReviewStatus.UNCHECKED.value}
    return {}


def install() -> None:
    if new_head_properties not in hooks.new_head_properties:
        hooks.new_head_properties.append(new_head_properties)


# (done as soon as a model can say it is reviewed, whether or not the app is installed)
install()
