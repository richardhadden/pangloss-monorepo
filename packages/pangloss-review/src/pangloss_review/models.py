"""The model of review: `Unreconciled`, someone or something a source names that has not been identified.

    class Person(Entity):
        _review_meta = ReviewMeta(allow_unreconciled=True)

    class Activity(Document):
        carried_out_by: Person

    Activity(label="Lunch", carried_out_by={"type": "Unreconciled", "unreconciled_type": "Person", "label": "John Smith"})

It is part of the document that mentions it (one for each mention), not an entity: it is in no list of people, and
nothing else refers to it. While it is there it is a task of review (`/review/reconciliations`): reconciling it puts
an entity in its place, by an update of the document, and gives its `uris` to that entity.

(An installed app's `models` module is imported as the server and the commands start. Importing `meta` also makes a
new document of a reviewed class unpublished.)
"""

import re
import unicodedata
from typing import Annotated

from pangloss_models import (
    DBField,
    Document,
    WriteEvent,
    create_validator,
    hooks,
    update_validator,
)
from pydantic import AnyHttpUrl

from pangloss_review import meta  # noqa: F401


def after_a_write(event: WriteEvent) -> None:
    """(a listener to writes, on a server) A suggestion that a save of its document confirmed (`identify.on_write`);
    and the URIs its parts name, to be found by (`uris`), brought up to date in the background"""
    from pangloss_review import identify, reconcile, uris

    identify.on_write(event)
    if event.op in ("create", "update") and uris.pending_work_of(event.model):
        reconcile.in_background(uris.drain())


def uris_pending(model: type) -> list[str]:
    """(`hooks.pending_work`, asked by a write on a server) `uris.pending_work_of`"""
    from pangloss_review import uris

    return uris.pending_work_of(model)


def _once(listeners: list, function) -> None:
    """Add to a list of hooks, in the place of the one of an earlier run of this module"""
    listeners[:] = [
        listener
        for listener in listeners
        if getattr(listener, "__qualname__", None) != function.__qualname__
        or getattr(listener, "__module__", None) != __name__
    ] + [function]


_once(hooks.after_write, after_a_write)
_once(hooks.pending_work, uris_pending)


def label_key(label: str) -> str:
    """A label as mentions are compared by: without case, accents, punctuation at its ends, or more than one space
    between words (`  JOHN  Smíth.` is `john smith`)"""
    plain = "".join(
        character
        for character in unicodedata.normalize("NFKD", label)
        if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", plain).strip(" .,;:").casefold()


def interface_meta() -> dict:
    """How the interface shows one, if it is installed (a client of the API, with the SDK, does not have it): as a
    chip with a button that reconciles it, in a view and in a form (the review interface module)"""
    try:
        from pangloss_interface import InterfaceMeta
    except ImportError:
        return {}
    return {
        "_interface_meta": InterfaceMeta(
            colour="rose",
            view_card="pangloss_review:UnreconciledCard",
            edit_card="pangloss_review:UnreconciledEditor",
        )
    }


class Unreconciled(Document):
    """Someone or something named in a source that has not been identified: what it is called there, and what kind
    of thing it is"""

    _meta = Document.Meta(
        create_directly=False, global_search=False, indexes=["label_key"]
    )
    locals().update(interface_meta())

    unreconciled_type: str
    """The name of the entity class it would be, if it were identified: one that the relation takes"""
    uris: list[AnyHttpUrl] = []
    """URIs known for it: given to the entity it is reconciled with"""

    # worked out, and only in the database
    label_key: Annotated[str | None, DBField] = None
    """The label as mentions are compared by (`label_key`)"""

    @create_validator
    @update_validator
    def fold_the_label(self):
        self.label_key = label_key(self.label)  # ty: ignore[unresolved-attribute]
