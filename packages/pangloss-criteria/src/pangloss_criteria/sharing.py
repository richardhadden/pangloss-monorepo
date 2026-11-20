"""Criteria made a shared description (implementation_docs/matches-criteria.md, "Shared descriptions", and "Identical
criteria": "offers to make them one shared description"): a `Description` is made with them, and every document
holding mentions whose own criteria are exactly these and that cite nothing is updated to cite it instead (the
mention's `description` the new one, its `criteria` none). Each document is an ordinary update by the user, one at a
time (a new version, a write event, history as any edit); one that cannot be written (it changed since it was read,
it does not validate, another description in it is broken) is left as it was, and said.

The route is `POST /api/criteria/share` (`api.py`), refused past `MAX_DOCUMENTS`; from Python, and through the SDK,
`pangloss_criteria.share(label, pattern)` (`access`).
"""

import logging
from typing import Any
from uuid import UUID

from pangloss_core import Transaction, backend
from pangloss_cypher import fragments
from pangloss_models import ModelRegistry, PanglossSearchError
from pangloss_models.citations import CITATION
from pangloss_models.utils import editable

from pangloss_criteria import holders
from pangloss_criteria.access import Reference, ShareFailed, ShareResult
from pangloss_criteria.effective import FIELD, cited_id
from pangloss_criteria.models import DESCRIPTION, NAME
from pangloss_criteria.pattern import SearchPattern
from pangloss_criteria.reading import checked_pattern
from pangloss_criteria.resolving import replaced_where

logger = logging.getLogger("pangloss.criteria.sharing")

MAX_DOCUMENTS = 500
"""The most documents the route updates in one request: more is a job for Python, `pangloss_criteria.share`"""

# The documents holding mentions whose own criteria are these and that cite nothing
HOLDING_QUERY = f"""
    MATCH (d:{NAME})
    WHERE d.criteria = $text
    WITH d, {cited_id("d")} AS cites
    WHERE cites IS NULL
    MATCH (head:HeadNode {{id: d.head_node_id}})
    WHERE {fragments.not_deleted("head")}
    RETURN DISTINCT head.id AS id, head.type AS type, head.label AS label
    ORDER BY label, id
"""


async def holding(pattern: SearchPattern) -> list[Reference]:
    """The documents (not deleted) holding mentions whose own criteria are exactly these, and that cite nothing"""

    @backend.current().database().read_transaction
    async def read(tx: Transaction) -> list[dict[str, Any]]:
        return [
            dict(row) async for row in await tx.run(HOLDING_QUERY, text=pattern.text())
        ]

    return [Reference(**row) for row in await read()]


async def read_view(model: Any, id: UUID) -> Any:
    """A document as it is now, to be written again (an entity without what refers to it)"""
    read = model.get_for_edit if model.__metatype__ == "Entity" else model.get
    return await read(id)


def citing(description_id: Any, pattern: SearchPattern, kinds: set[str]):
    """Which nodes of a document are to cite the description, and what each becomes"""

    def chosen(node: dict[str, Any]) -> bool:
        if node.get("type") not in kinds or node.get(FIELD) is not None:
            return False
        criteria = node.get("criteria")
        try:
            return criteria is not None and SearchPattern(criteria) == pattern
        except ValueError:
            return False

    def made(node: dict[str, Any]) -> dict[str, Any]:
        return {
            **node,
            # (as a new citation, not as a reference: in an update, `{type, id}` is taken for a citation node that
            # is there, of that id)
            FIELD: {
                "type": CITATION,
                "target_id": str(description_id),
                "target_type": DESCRIPTION,
            },
            "criteria": None,
        }

    return chosen, made


async def share(
    label: str,
    pattern: Any,
    except_: UUID | str | None = None,
    limit: int | None = None,
) -> ShareResult:
    """A shared description made of criteria (`pattern`), and every document holding mentions whose own criteria are
    exactly these and that cite nothing updated to cite it (a mention's own criteria become none), one at a time, as
    the user of the request. `except_`: a head that is not updated (the document open in a form, which cites the new
    description when it is saved). `limit`: the most documents it may touch (`PanglossSearchError` past it, before
    anything is written); none, from Python. Raises `PanglossSearchError` for criteria a description could not
    store"""
    criteria = checked_pattern(pattern)
    documents = [
        document
        for document in await holding(criteria)
        if except_ is None or str(document.id) != str(except_)
    ]
    if limit is not None and len(documents) > limit:
        raise PanglossSearchError(
            f"These criteria are held by mentions in {len(documents)} documents, more than {limit} are updated in one "
            "request: make the shared description from Python (`pangloss_criteria.share(label, pattern)`)"
        )
    models = ModelRegistry.all_models()
    made = await models[DESCRIPTION].Create(label=label, criteria=criteria).save()  # ty: ignore[unresolved-attribute]
    chosen, replace = citing(made.id, criteria, set(holders.description_labels()))
    updated = 0
    failed: list[ShareFailed] = []
    for document in documents:
        model: Any = models.get(document.type)
        try:
            if model is None:
                raise LookupError(f"{document.type} is no class of the models")
            view = await read_view(model, document.id)
            if view is None:
                raise LookupError("it is not there any more")
            data, found = replaced_where(editable(view.model_dump()), chosen, replace)
            if not found:
                # (changed since it was found: nothing of it holds the criteria now)
                continue
            await model.Update(**data).save(expected_version=view.meta.version)
            updated += 1
        except Exception as error:
            # (said, and the others go on: each is a write of its own)
            logger.info(
                "Criteria: %s %s not made to cite the shared description",
                document.type,
                document.id,
            )
            failed.append(
                ShareFailed(head=document, detail=f"{type(error).__name__}: {error}")
            )
    return ShareResult(
        description=Reference(type=DESCRIPTION, id=made.id, label=made.label),
        updated=updated,
        failed=failed,
    )


__all__ = ["MAX_DOCUMENTS", "holding", "share"]
