"""Making a derived document a document of one's own: `DerivedFactoid` -> `Factoid`. See
implementation_docs/derived-edges-and-documents.md ("Converting it into an ordinary document").

The derived document itself changes class, in place (`changing_class_from`): same id, its history goes on. What
carries over is what the two classes share; the rest is for the person to fill in. In the transaction of the write its
justification is **adopted**: the worker never writes that id again, and keeps the justification as the record (which
says when the derivation stops holding). `derived_by` and `derived_context` stay on the document (D19): a rule that
blocks the derived class reads it as what a person wrote, and criteria still know what it rested on.
"""

import datetime
from typing import Any
from uuid import UUID

from pangloss_models import Document, ModelRegistry, hooks
from pangloss_models.citations import CITATION
from pangloss_models.field_definitions import (
    RelationFieldDefinition,
    RelationToCitation,
)
from pydantic.alias_generators import to_camel

from pangloss_derived import documents
from pangloss_derived.registry import PanglossDerivedError

ADOPT_QUERY = """
MATCH (j:PGJustification {document_id: $id})
SET j.adopted = true, j.adopted_by = $user, j.adopted_at = $at
REMOVE j.lost
RETURN count(j) AS adopted, collect(j.rule)[0] AS rule
"""

# What a converted document says of itself to whoever looks after it (`hooks.give_notice`: with `pangloss-review`, an
# open comment on it)
CONVERTED = "converted"

CLEAR_CONTEXT_QUERY = """
MATCH (h:HeadNode {id: $id})
MATCH (j:PGJustification {document_id: $id})
WHERE coalesce(j.adopted, false)
SET h.derived_context = [], j.context_cleared_by = $user, j.context_cleared_at = $at
RETURN h.type AS type
"""

NOT_COPIED = {"id", "meta", "type"}


def derived_class(name: str) -> type:
    model = ModelRegistry._model_dict.get(name)
    if model is None or not documents.is_derived_document(model):
        raise PanglossDerivedError(f"{name} is not a derived document class")
    return model


def targets_of(source: type) -> list[type]:
    """The classes a document of the derived class can be made into: `DerivedDocumentMeta(converts_to=...)`, or the
    concrete classes people write that share a parent (beyond `Document`) with it"""
    given: Any = documents.settings_of(source).converts_to
    if given:
        return [t for t in given if isinstance(t, type)]
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
            # (a document of its own, as the derived one is: not one that is only ever part of another)
            and getattr(model._meta, "create_directly", True)
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


def shared_fields(source: Any, target: Any) -> list[str]:
    """The fields the two classes have: what carries over. Not the `DerivedFrom` field (whatever it is called), nor
    what the worker records"""
    own = set(documents.source_fields(source))
    return [
        name
        for name in source._meta.fields
        if name in target._meta.fields
        and name not in NOT_COPIED
        and name not in own
        and not source._meta.fields[name].db_field
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


def citing_fields(target: Any) -> list[tuple[str, bool, RelationToCitation]]:
    """The fields of the class that cite (`Cites[...]`, protecting what they cite), in the order declared: the name,
    whether it takes several, and what it takes"""
    found = []
    for name, definition in target._meta.fields.items():
        if not isinstance(definition, RelationFieldDefinition):
            continue
        for option in definition.type_options:
            if isinstance(option, RelationToCitation) and option.protect:
                found.append((name, definition.wrapper is not None, option))
                break
    return found


def cited_sources(target: Any, sources: list[dict[str, Any]]) -> dict[str, Any]:
    """The sources of the derived document as citations of the target's own, where it has a `Cites` field that takes
    them: each in the first field that takes its class. They are then cited as anything is (and protected). A source
    no field takes is left for the person, as the sources are shown beside the form"""
    fields = citing_fields(target)
    given: dict[str, Any] = {}
    for source in sources:
        if source.get("target_state", "there") != "there":
            continue
        model = ModelRegistry._model_dict.get(str(source.get("target_type")))
        if model is None:
            continue
        for name, several, option in fields:
            if not issubclass(model, tuple(option.cited)):
                continue
            if not several and name in given:
                continue
            citation = {
                "type": CITATION,
                "changed_since_cited": False,
                **{
                    key: source.get(key)
                    for key in (
                        "target_id",
                        "target_type",
                        "target_label",
                        "target_head_id",
                        "target_head_type",
                        "target_head_label",
                        "target_spaces",
                        "target_state",
                    )
                },
            }
            if several:
                given.setdefault(name, []).append(citation)
            else:
                given[name] = citation
            break
    return given


async def prefill(type_name: str, id: UUID, to: str) -> dict[str, Any]:
    """The form of the target class, filled in: its `initial` (what the two classes share, with the ids of what is in
    it kept, as the document is changed in place) and `version`, and the sources the derivation rested on"""
    source: Any = derived_class(type_name)
    target: Any = target_class(source, to)
    view: Any = await source.get(id)
    if view is None:
        raise PanglossDerivedError(f"There is no {type_name} with id {id}")
    data = view.model_dump(mode="json")
    # (the id: the document stays the one it is, and so do the nodes in it)
    initial: dict[str, Any] = {"type": target.__name__, "id": str(id)}
    # (a label the derived class worked out is not carried into a class that works out its own)
    if not (
        data.get("label_auto") is True and "label_auto" in target.Update.model_fields
    ):
        initial["label"] = data.get("label")
    for name in shared_fields(source, target):
        if name in data:
            initial[name] = data[name]
    from pangloss_derived import why

    about = await why.of_document(source.__name__, id)
    field, _ = documents.source_field(source)
    # (a field the two share is as it is; one only the target has, that cites, is given the sources it takes)
    for name, citations in cited_sources(target, data.get(field) or []).items():
        if name not in initial:
            initial[name] = citations
    return {
        "type": target.__name__,
        "id": str(id),
        "version": view.meta.version,
        "initial": camel(initial),
        "sources": camel(data.get(field) or []),
        # (from what is recorded of it: the whole view of a document does not have what the worker records)
        "derivedBy": about["rule"] if about else None,
        "derivedContext": about["context"] if about else [],
    }


async def convert(
    type_name: str, id: UUID, to: str, data: dict[str, Any], version: int
) -> dict[str, Any]:
    """Make the document a `to`, with what the form gives. In one transaction: the class changes, and the
    justification is adopted. Gives the new item as a summary"""
    from pangloss_users import current_request_username

    source = derived_class(type_name)
    target: Any = target_class(source, to)
    type_name = source.__name__
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
        record = await result.single()
        if not record or not record["adopted"]:
            # (its justification is gone, and the worker is about to delete it: nothing is written)
            raise PanglossDerivedError(
                f"The derivation of {type_name} {id} no longer holds: it cannot be made a {to}"
            )
        # (it keeps whether it is published, and whoever reviews it is told what it was)
        await hooks.give_notice(
            tx,
            hooks.Notice(
                head_id=id,
                head_type=target.__name__,
                kind=CONVERTED,
                text=f"Made from a derived document (a {type_name}, by the rule {record['rule']})",
                user=user or None,
            ),
        )

    with documents.converting(id):
        saved = await update.save(
            expected_version=version, changing_class_from=source, before_write=adopt
        )
    return {"id": str(saved.id), "type": target.__name__, "label": saved.label}


async def clear_context(type_name: str, id: UUID) -> bool:
    """The author of a converted document says that it no longer rests on the derivation it was made from: what the
    derivation passed through (`derived_context`) is taken off it. Rules that read the document then read it as
    plain, so it is marked for them as a write of it is. Gives whether it was a converted document"""
    from pangloss_cypher import pending
    from pangloss_users import current_request_username

    from pangloss_derived.read import database

    model = ModelRegistry._model_dict.get(type_name)
    if model is None or documents.is_derived_document(model):
        raise PanglossDerivedError(
            f"{type_name} {id} is not a document made from a derived one: only that has a context to clear"
        )
    user = current_request_username.get() or ""

    @database().write_transaction
    async def clear(tx: Any) -> bool:
        result = await tx.run(
            CLEAR_CONTEXT_QUERY,
            id=str(id),
            user=user,
            at=datetime.datetime.now(datetime.UTC).isoformat(),
        )
        record = await result.single()
        if record is None or record["type"] != type_name:
            return False
        await pending.mark_written(tx, model, id)
        return True

    cleared = await clear()
    if cleared:
        hooks.emit_work_marked(model)
    return cleared


# (the derivation stays recorded on the document it made)
KEPT = ["derived_by", "derived_context"]
