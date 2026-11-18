"""Making a derived document a document of one's own: `DerivedFactoid` -> `Factoid`. See
implementation_docs/derived-edges-and-documents.md ("Converting it into an ordinary document").

The derived document itself changes class, in place (`changing_class_from`): same id, its history goes on. What
carries over is what the two classes share; the rest is for the person to fill in. In the transaction of the write its
justification is **adopted**: the worker never writes that id again, and keeps the justification as the record (which
says when the derivation stops holding). `derived_by` and `derived_context` stay on the document (D19): a rule that
blocks the derived class reads it as what a person wrote, and criteria still know what it rested on.
"""

import datetime
import uuid
from typing import Any
from uuid import UUID

from pangloss_models import Document, ModelRegistry
from pydantic.alias_generators import to_camel

from pangloss_derived import documents
from pangloss_derived.registry import PanglossDerivedError

ADOPT_QUERY = """
MATCH (j:PGJustification {document_id: $id})
SET j.adopted = true, j.adopted_by = $user, j.adopted_at = $at
REMOVE j.lost
RETURN count(j) AS adopted
"""

NOT_COPIED = {"id", "meta", "type", "sources"}


def derived_class(name: str) -> type:
    model = ModelRegistry._model_dict.get(name)
    if model is None or not documents.is_derived_document(model):
        raise PanglossDerivedError(f"{name} is not a derived document class")
    return model


def targets_of(source: type) -> list[type]:
    """The classes a document of the derived class can be made into: `DerivedDocumentMeta(converts_to=...)`, or the
    concrete classes people write that share a parent (beyond `Document`) with it"""
    settings = documents.settings_of(source)
    if settings.converts_to:
        return [t for t in settings.converts_to if isinstance(t, type)]
    parents = {
        c
        for c in source.__mro__[1:]
        if isinstance(c, type)
        and issubclass(c, Document)
        and c is not Document
        and getattr(c, "__metatype__", None) == "Document"
    }
    found = []
    for model in ModelRegistry._models:
        if (
            isinstance(model, type)
            and issubclass(model, Document)
            and not getattr(model._meta, "abstract", False)
            and model is not source
            and not documents.is_derived_document(model)
            and any(issubclass(model, p) for p in parents)
        ):
            found.append(model)
    return found


def target_class(source: type, name: str) -> type:
    for target in targets_of(source):
        if target.__name__ == name:
            return target
    raise PanglossDerivedError(
        f"A {source.__name__} cannot be made a {name}: it can become "
        + (", ".join(t.__name__ for t in targets_of(source)) or "nothing")
    )


def shared_fields(source: type, target: type) -> list[str]:
    """The fields the two classes have: what carries over"""
    return [
        name
        for name in source._meta.fields  # ty: ignore[unresolved-attribute]
        if name in target._meta.fields  # ty: ignore[unresolved-attribute]
        and name not in NOT_COPIED
        and not source._meta.fields[name].db_field  # ty: ignore[unresolved-attribute]
    ]


def camel(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            (to_camel(k) if isinstance(k, str) and k != "type" else k): camel(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [camel(v) for v in value]
    return value


async def prefill(type_name: str, id: UUID, to: str) -> dict[str, Any]:
    """The form of the target class, filled in: its `initial` (what the two classes share, with the ids of what is in
    it kept, as the document is changed in place) and `version`, and the sources the derivation rested on"""
    source = derived_class(type_name)
    target = target_class(source, to)
    view: Any = await source.get(id)
    if view is None:
        raise PanglossDerivedError(f"There is no {type_name} with id {id}")
    data = view.model_dump(mode="json")
    initial: dict[str, Any] = {"type": target.__name__, "label": data.get("label")}
    for name in shared_fields(source, target):
        if name in data:
            initial[name] = data[name]
    field, _ = documents.source_field(source)
    return {
        "type": target.__name__,
        "id": str(id),
        "version": view.meta.version,
        "initial": camel(initial),
        "sources": camel(data.get(field) or []),
        "derivedBy": data.get("derived_by"),
        "derivedContext": data.get("derived_context") or [],
    }


async def convert(
    type_name: str, id: UUID, to: str, data: dict[str, Any], version: int
) -> dict[str, Any]:
    """Make the document a `to`, with what the form gives. In one transaction: the class changes, and the
    justification is adopted. Gives the new item as a summary"""
    from pangloss_cypher import fragments  # noqa: F401
    from pangloss_users import current_request_username

    source = derived_class(type_name)
    target: Any = target_class(source, to)
    user = current_request_username.get() or ""
    body = {k: v for k, v in data.items() if k not in ("meta", "type")}
    update = target.Update.model_validate({**body, "id": id})

    async def adopt(tx: Any) -> None:
        result = await tx.run(
            ADOPT_QUERY,
            id=str(id),
            user=user,
            at=datetime.datetime.now(datetime.UTC).isoformat(),
        )
        await result.consume()

    saved = await update.save(
        expected_version=version, changing_class_from=source, before_write=adopt
    )
    return {"id": str(saved.id), "type": target.__name__, "label": saved.label}


# (the derivation stays recorded on the document it made)
KEPT = ["derived_by", "derived_context"]
_ = uuid
