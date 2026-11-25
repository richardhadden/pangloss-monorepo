"""Derived documents, as the worker keeps them: the justifications of the rules that derive documents, and the
documents written from them. See implementation_docs/derived.md ("Derived documents").

    (:PGJustification {key, rule, rule_hash, types, nodes, values, context, context_labels, status, derived_at,
                       generation, document_id, document_type, sources})
        -[:evidence]->(head node)

A justification of such a rule justifies no fact: it is **one document**, whose id it keeps (`document_id`). The id
is made once, from the key, and then stored: when the values of a justification change while the nodes of its
patterns stay (an entity merged), the new justification takes the id over, and the document is changed in place.

The work is in two parts, so that a rule that gives a thousand documents holds nothing back:

1. the worker of facts **finds** the justifications (`store_found`), writes those that are new, deletes those that
   are gone, and leaves the id of each document concerned pending (`pangloss_cypher.pending`): kind
   `derive-retractions` for a document whose justification is gone, `derive-documents` for the others. In the
   transaction that wrote or deleted the justification, so that none is forgotten;
2. `reconcile` makes each pending document what its justification says: made, changed (only if what would be
   written differs from what was: the hash of it is kept on the head), deleted when there is no justification,
   undeleted when one is back, published when all it rests on is. Each through the ordinary writes of a document
   (so with a label, history, the text index), as the user `derived`. Retractions first.

A justification is **adopted** when a person makes its document one of their own (`pangloss_derived.convert`): the
document is no longer the worker's, which never writes that id again. The justification is kept as the record of it
(through a rebuild, and when its rule is removed): `adopted`, and `lost` when the rule no longer finds it (the
document stays; its page says that the derivation it was made from does not hold).
"""

import contextlib
import dataclasses
import datetime
import json
import logging
import uuid
from collections.abc import Generator, Sequence
from typing import Any

from pangloss_core import Transaction, storage_of
from pangloss_cypher import fragments, pending
from pangloss_models import ModelRegistry
from pangloss_models.citations import UNPROTECTED
from pangloss_models.exceptions import PanglossWriteError

from pangloss_derived import documents
from pangloss_derived.check import CheckedRule
from pangloss_derived.registry import DerivedRegistry
from pangloss_derived.store import (
    JUSTIFICATION,
    WRITE_CHUNK,
    Found,
    FoundJustification,
    chunks,
    context_json,
    digest,
)
from pangloss_derived.templates import TNode, TVar, TVia, fill

logger = logging.getLogger("pangloss.derived.documents")

DOCUMENTS = "derive-documents"
RETRACTIONS = "derive-retractions"
KINDS = (RETRACTIONS, DOCUMENTS)

# (never changed: the ids of derived documents are made with it)
DOCUMENT_IDS = uuid.UUID("b0a4b0f6-6d0b-5f0e-8a67-51a1c1c5f3d2")

DEFAULT_USER = "derived"


def document_id(key: str, type_name: str, attempt: int = 0) -> str:
    """The id of the document of a justification, when it is first found: of its key and the class. `attempt`: when
    that id is another justification's (it took it over from this key, which is now found beside it)"""
    name = f"{key}/{type_name}" + (f"/{attempt}" if attempt else "")
    return str(uuid.uuid5(DOCUMENT_IDS, name))


# ---------------------------------------------------------------------------
# The justifications
# ---------------------------------------------------------------------------

EXISTING_QUERY = f"""
UNWIND $keys AS key
MATCH (j:{JUSTIFICATION} {{key: key}})
RETURN j.key AS key, j.context AS context, j.rule_hash AS rule_hash, j.document_id AS document,
       j.document_type AS type, j.rule AS rule, j.nodes AS nodes,
       coalesce(j.adopted, false) AS adopted, coalesce(j.lost, false) AS lost
"""

EVIDENCED_QUERY = f"""
UNWIND $heads AS head_id
MATCH (h:HeadNode {{id: head_id}})
WITH h
MATCH (h)<-[:evidence]-(j:{JUSTIFICATION})
WHERE j.document_id IS NOT NULL
RETURN DISTINCT j.key AS key, j.rule AS rule, j.nodes AS nodes, j.document_id AS document, j.document_type AS type,
       coalesce(j.adopted, false) AS adopted, coalesce(j.lost, false) AS lost
"""

TAKEN_QUERY = f"""
UNWIND $ids AS id
MATCH (j:{JUSTIFICATION} {{document_id: id}})
RETURN id
"""

WRITE_QUERY = f"""
UNWIND $justifications AS j
MERGE (n:{JUSTIFICATION} {{key: j.key}})
ON CREATE SET n.rule = j.rule, n.rule_hash = j.rule_hash, n.types = j.types, n.nodes = j.nodes,
              n.context = j.context, n.context_labels = j.context_labels, n.status = j.status, n.`values` = j.`values`,
              n.sources = j.sources, n.document_id = j.document, n.document_type = j.type, n.derived_at = $at,
              n.adopted = j.adopted, n.adopted_by = j.adopted_by, n.adopted_at = j.adopted_at
SET n.generation = $generation
WITH n, j
UNWIND j.heads AS head_id
MATCH (h:HeadNode {{id: head_id}})
MERGE (n)-[:evidence]->(h)
"""

CHANGED_QUERY = f"""
UNWIND $justifications AS j
MATCH (n:{JUSTIFICATION} {{key: j.key}})
SET n.context = j.context, n.context_labels = j.context_labels, n.status = j.status, n.types = j.types,
    n.rule_hash = j.rule_hash
"""

TOUCH_QUERY = f"""
UNWIND $keys AS key
MATCH (n:{JUSTIFICATION} {{key: key}})
SET n.generation = $generation
"""

DELETE_QUERY = f"""
UNWIND $keys AS key
MATCH (j:{JUSTIFICATION} {{key: key}})
DETACH DELETE j
"""

# (what is retracted: never one that has been adopted since it was read. Gives the documents of those that went)
DELETE_UNADOPTED_QUERY = f"""
UNWIND $keys AS key
MATCH (j:{JUSTIFICATION} {{key: key}})
WHERE NOT coalesce(j.adopted, false)
WITH j, j.document_id AS document
DETACH DELETE j
RETURN document
"""

# (those of the keys that are adopted, whatever was read before: they are kept, and said to be lost)
LOSE_ADOPTED_QUERY = f"""
UNWIND $keys AS key
MATCH (j:{JUSTIFICATION} {{key: key}})
WHERE coalesce(j.adopted, false) AND NOT coalesce(j.lost, false)
SET j.lost = true
RETURN j.document_id AS document
"""

LOSE_QUERY = f"""
UNWIND $keys AS key
MATCH (j:{JUSTIFICATION} {{key: key}})
SET j.lost = true
"""

FOUND_AGAIN_QUERY = f"""
UNWIND $keys AS key
MATCH (j:{JUSTIFICATION} {{key: key}})
REMOVE j.lost
"""

ADOPTED_QUERY = f"""
UNWIND $keys AS key
MATCH (j:{JUSTIFICATION} {{key: key}})
RETURN j.key AS key, j.adopted_by AS adopted_by, j.adopted_at AS adopted_at,
       coalesce(j.adopted, false) AS adopted
"""

OF_RULE_QUERY = f"""
MATCH (j:{JUSTIFICATION} {{rule: $rule}})
WHERE j.document_id IS NOT NULL AND ($generation IS NULL OR j.generation IS NULL OR j.generation <> $generation)
  AND NOT coalesce(j.adopted, false)
WITH j LIMIT $limit
WITH j, j.document_id AS document
DETACH DELETE j
RETURN document
"""

# (an adopted one that the rule does not find: it is kept, and said to be lost)
LOSE_OF_RULE_QUERY = f"""
MATCH (j:{JUSTIFICATION} {{rule: $rule}})
WHERE j.document_id IS NOT NULL AND ($generation IS NULL OR j.generation IS NULL OR j.generation <> $generation)
  AND coalesce(j.adopted, false) AND NOT coalesce(j.lost, false)
SET j.lost = true
RETURN j.document_id AS document
"""

COUNTS_QUERY = f"""
MATCH (j:{JUSTIFICATION})
WHERE j.document_id IS NOT NULL AND NOT coalesce(j.adopted, false)
RETURN j.rule AS rule, count(j) AS documents
"""

ADOPTED_COUNTS_QUERY = f"""
MATCH (j:{JUSTIFICATION})
WHERE j.document_id IS NOT NULL AND coalesce(j.adopted, false)
RETURN j.rule AS rule, count(j) AS documents,
       sum(CASE WHEN coalesce(j.lost, false) THEN 1 ELSE 0 END) AS lost
"""

LOST_QUERY = f"""
MATCH (j:{JUSTIFICATION})
WHERE j.document_id IS NOT NULL AND coalesce(j.adopted, false) AND coalesce(j.lost, false)
MATCH (h:HeadNode {{id: j.document_id}})
WHERE {fragments.not_deleted("h")}
RETURN h.id AS id, h.type AS type, h.label AS label, j.rule AS rule
ORDER BY label, id
LIMIT $limit
"""


def row_of(
    justification: FoundJustification,
    document: str,
    type_name: str,
    adopted: dict[str, Any] | None = None,
) -> dict:
    """`adopted`: of a justification that takes over the document of one that was adopted (who made the document
    their own, and when): it is adopted as that one was"""
    return {
        "adopted": True if adopted else None,
        "adopted_by": adopted["adopted_by"] if adopted else None,
        "adopted_at": adopted["adopted_at"] if adopted else None,
        "key": justification.key,
        "rule": justification.rule,
        "rule_hash": justification.rule_hash,
        "types": justification.types,
        "nodes": justification.nodes,
        "heads": justification.heads,
        "context": context_json(justification),
        "context_labels": justification.context_labels,
        "status": justification.status,
        "values": json.dumps(justification.values, sort_keys=True, default=str),
        "sources": justification.sources,
        "document": document,
        "type": type_name,
    }


def _any(tx: Any) -> Any:
    # (the transaction of the backend, which the Cypher functions take; `pangloss_core.Transaction` is the protocol)
    return tx


def type_of(rule_name: str) -> str:
    return DerivedRegistry.documents[rule_name].model.__name__


async def run(tx: Transaction, query: str, **params: Any) -> list[dict[str, Any]]:
    result = await tx.run(query, **params)
    return [dict(record) async for record in result]


async def store_found(
    database: Any,
    found: Found,
    *,
    replace_for_heads: Sequence[str] = (),
    generation: str = "",
    chunk: int = WRITE_CHUNK,
) -> dict[str, int]:
    """Write the justifications of documents that were found and are not there (each with the id of its document);
    delete those with evidence in `replace_for_heads` that were not found. Each document concerned is left pending:
    to be made, looked at again, or (its justification gone) deleted. Gives counts of what was done.

    A justification that is gone and one that is new, of the same rule and the same nodes, and the only ones so: the
    new one takes the document over (its values changed: the document is changed, and keeps its id).

    An adopted justification (its document is a person's own now) is never deleted: one that is not found is marked
    `lost`, and found again it is not; the citations made through its document are marked as for any other. Its
    document is not left pending, and one that takes it over is adopted as it was.

    In short transactions, each safe to run again (as `store.write_found`)."""
    at = datetime.datetime.now(datetime.UTC)
    keys = list(found.documents)

    @database.read_transaction
    async def read(tx: Transaction, query: str, **params: Any) -> list[dict[str, Any]]:
        return await run(tx, query, **params)

    existing: dict[str, dict[str, Any]] = {}
    for part in chunks(keys, 5000):
        existing.update(
            {row["key"]: row for row in await read(EXISTING_QUERY, keys=part)}
        )

    stale: dict[str, dict[str, Any]] = {}
    if replace_for_heads:
        for row in await read(EVIDENCED_QUERY, heads=list(replace_for_heads)):
            if row["key"] not in found.documents:
                stale[row["key"]] = row
    # (a rule that now derives another class: the document it has cannot become one of it. It goes, and one is made)
    for key, row in existing.items():
        if row["type"] != type_of(found.documents[key].rule) and not row["adopted"]:
            stale[key] = row
    for key in stale:
        existing.pop(key, None)

    new = [j for key, j in found.documents.items() if key not in existing]

    # -- which new one takes the document of which that is gone
    def group(
        rule: str, nodes: Any, type_name: str
    ) -> tuple[str, tuple[str, ...], str]:
        return rule, tuple(str(n) for n in nodes), type_name

    gone_by: dict[Any, list[dict[str, Any]]] = {}
    for row in stale.values():
        gone_by.setdefault(group(row["rule"], row["nodes"], row["type"]), []).append(
            row
        )
    new_by: dict[Any, list[FoundJustification]] = {}
    for j in new:
        new_by.setdefault(group(j.rule, j.nodes, type_of(j.rule)), []).append(j)
    ids: dict[str, str] = {}
    taken_over: dict[str, str] = {}
    """The key of each new justification that takes a document over: the key of the one it had"""
    for where, justifications in new_by.items():
        gone = gone_by.get(where, [])
        if (
            len(justifications) == 1
            and len(gone) == 1
            and gone[0]["key"] != justifications[0].key
        ):
            ids[justifications[0].key] = gone[0]["document"]
            taken_over[justifications[0].key] = gone[0]["key"]

    # -- an id for each of the others: of its key, unless another justification has that one
    waiting = [j for j in new if j.key not in ids]
    attempt = 0
    while waiting:
        candidates = {
            j.key: document_id(j.key, type_of(j.rule), attempt) for j in waiting
        }
        taken: set[str] = set()
        for part in chunks(list(candidates.values()), 5000):
            taken |= {row["id"] for row in await read(TAKEN_QUERY, ids=part)}
        for j in waiting:
            if candidates[j.key] not in taken:
                ids[j.key] = candidates[j.key]
        waiting = [j for j in waiting if j.key not in ids]
        attempt += 1

    # -- retractions first: what is gone, and the documents to delete (but an adopted one, which is kept, and said
    # to be lost)
    gone = [row for row in stale.values() if row["key"] not in taken_over.values()]
    retract = [row for row in gone if not row["adopted"]]
    lose = [row for row in gone if row["adopted"] and not row["lost"]]
    from pangloss_cypher import citations

    @database.write_transaction
    async def mark_lost(tx: Any, part: list[dict[str, Any]]) -> None:
        await (await tx.run(LOSE_QUERY, keys=[r["key"] for r in part])).consume()
        for row in part:
            await citations.mark_via(_any(tx), row["document"], "lost")

    for part in chunks(lose, chunk):
        await mark_lost(part)

    @database.write_transaction
    async def delete(tx: Transaction, part: list[dict[str, Any]]) -> None:
        # (whether one is adopted is asked here, in the transaction that deletes: a person may have made the
        # document their own since the justifications were read)
        keys = [r["key"] for r in part]
        went = await run(tx, DELETE_UNADOPTED_QUERY, keys=keys)
        await pending.mark(tx, RETRACTIONS, [row["document"] for row in went])
        for row in await run(tx, LOSE_ADOPTED_QUERY, keys=keys):
            await citations.mark_via(_any(tx), row["document"], "lost")

    for part in chunks(retract, chunk):
        await delete(part)

    @database.write_transaction
    async def write(tx: Transaction, part: list[FoundJustification]) -> None:
        replaced = [taken_over[j.key] for j in part if j.key in taken_over]
        # (which of those taken over are adopted is asked here, in the transaction that replaces them: a person
        # may have made the document their own since they were read)
        adopted_now: dict[str, dict[str, Any]] = {}
        if replaced:
            adopted_now = {
                row["key"]: row
                for row in await run(tx, ADOPTED_QUERY, keys=replaced)
                if row["adopted"]
            }
            await (await tx.run(DELETE_QUERY, keys=replaced)).consume()

        def adopted_of(j: FoundJustification) -> dict[str, Any] | None:
            return adopted_now.get(taken_over.get(j.key, ""))

        await (
            await tx.run(
                WRITE_QUERY,
                justifications=[
                    row_of(j, ids[j.key], type_of(j.rule), adopted_of(j)) for j in part
                ],
                at=at,
                generation=generation,
            )
        ).consume()
        await pending.mark(
            tx, DOCUMENTS, [ids[j.key] for j in part if adopted_of(j) is None]
        )
        for j in part:
            old = taken_over.get(j.key)
            if old is not None and stale[old]["adopted"] and stale[old]["lost"]:
                # (the derivation a person's document was made from holds again, with other values)
                await citations.mark_via(_any(tx), ids[j.key], "")

    for part in chunks(new, chunk):
        await write(part)

    # -- those found again: what they passed through may have changed; their documents are looked at again (what
    # they rest on may have been published, or its own context changed)
    again = [found.documents[key] for key in existing]
    changed = [
        j
        for j in again
        if existing[j.key]["context"] != context_json(j)
        or existing[j.key]["rule_hash"] != j.rule_hash
    ]

    @database.write_transaction
    async def rewrite(tx: Transaction, part: list[FoundJustification]) -> None:
        await (
            await tx.run(
                CHANGED_QUERY,
                justifications=[row_of(j, "", "") for j in part],
            )
        ).consume()

    for part in chunks(changed, chunk):
        await rewrite(part)

    @database.write_transaction
    async def look_again(tx: Transaction, part: list[FoundJustification]) -> None:
        if generation:
            await (
                await tx.run(
                    TOUCH_QUERY, keys=[j.key for j in part], generation=generation
                )
            ).consume()
        await pending.mark(
            tx,
            DOCUMENTS,
            [
                existing[j.key]["document"]
                for j in part
                if not existing[j.key]["adopted"]
            ],
        )
        # (an adopted one that was lost holds again)
        back = [j.key for j in part if existing[j.key]["lost"]]
        if back:
            await (await tx.run(FOUND_AGAIN_QUERY, keys=back)).consume()
            for key in back:
                await citations.mark_via(_any(tx), existing[key]["document"], "")

    for part in chunks(again, 2000):
        await look_again(part)
    citations.flush_marks()

    return {
        "new": len(new),
        "removed": len(retract),
        "taken_over": len(taken_over),
        "again": len(again),
        "lost": len(lose),
    }


async def remove_of_rule(
    tx: Transaction, rule: str, generation: str | None, limit: int
) -> int:
    """Delete up to `limit` justifications of documents of the rule (with `generation`: those not of it), and leave
    their documents to be deleted. Gives how many went"""
    rows = await run(tx, OF_RULE_QUERY, rule=rule, generation=generation, limit=limit)
    await pending.mark(tx, RETRACTIONS, [row["document"] for row in rows])
    if len(rows) < limit:
        # (with the last of the others: the adopted ones the rule does not find are kept, and said to be lost)
        from pangloss_cypher import citations

        for row in await run(tx, LOSE_OF_RULE_QUERY, rule=rule, generation=generation):
            await citations.mark_via(_any(tx), row["document"], "lost")
    return len(rows)


async def counts(tx: Transaction) -> dict[str, int]:
    """How many documents each rule has a justification for (not those people have made their own)"""
    return {row["rule"]: row["documents"] for row in await run(tx, COUNTS_QUERY)}


async def adopted_counts(tx: Transaction) -> dict[str, dict[str, int]]:
    """Of each rule, how many of its documents people have made their own (`converted`), and of how many of those
    the derivation no longer holds (`lost`)"""
    return {
        row["rule"]: {"converted": row["documents"], "lost": row["lost"]}
        for row in await run(tx, ADOPTED_COUNTS_QUERY)
    }


async def lost(tx: Transaction, limit: int = 100) -> list[dict[str, Any]]:
    """The documents people made their own whose derivation no longer holds: `id`, `type`, `label`, `rule`"""
    return await run(tx, LOST_QUERY, limit=limit)


# ---------------------------------------------------------------------------
# The documents
# ---------------------------------------------------------------------------

STATE_QUERY = f"""
UNWIND $ids AS id
OPTIONAL MATCH (j:{JUSTIFICATION} {{document_id: id}})
OPTIONAL MATCH (h:HeadNode {{id: id}})
RETURN id, j.key AS key, j.rule AS rule, j.`values` AS `values`, j.sources AS sources,
       j.context_labels AS context_labels,
       h.type AS type, {fragments.deleted("h")} AS deleted, {fragments.published("h")} AS published,
       h.{documents.CONTENT} AS content, h IS NOT NULL AS there
"""

NODES_QUERY = f"""
UNWIND $ids AS id
MATCH (n:PGIndexableNode {{id: id}})
RETURN n.id AS id, n.type AS type, {fragments.deleted("n")} AS deleted, {fragments.published("n")} AS published,
       n.derived_context AS derived_context, n.merged_into AS merged_into
"""


@contextlib.contextmanager
def acting_as(username: str) -> Generator[None]:
    from pangloss_users import current_request_username

    token = current_request_username.set(username)
    try:
        yield
    finally:
        current_request_username.reset(token)


def user() -> str:
    from pangloss_core import settings as core_settings

    settings = core_settings.__dict__.get("SETTINGS")
    return getattr(settings, "DERIVED_USER", DEFAULT_USER) or DEFAULT_USER


async def ensure_user() -> str:
    """The user the worker writes documents as. It must exist (a write by one that does not is refused); it is made
    with a password nobody is told, so nobody logs in as it"""
    import secrets

    from pangloss_users import service
    from pangloss_users import PanglossUserExistsError

    username = user()
    # (asked each time, one read for the documents of a batch: the user may have been removed, or the database
    # emptied, since)
    if await service.get_user(username) is None:
        with contextlib.suppress(PanglossUserExistsError):
            await service.create_user(
                username,
                f"{username}@example.com",
                secrets.token_urlsafe(48),
                full_name="Derived documents",
            )
        logger.info(
            "Made the user %s, which derived documents are written as", username
        )
    return username


def entity_variables(node: TNode) -> set[str]:
    """The variables of a template that are of entities (their values are ids, written as references)"""
    found: set[str] = set()

    def item(value: Any) -> None:
        if isinstance(value, tuple):
            for member in value:
                item(member)
        elif isinstance(value, TNode):
            for member in value.fields.values():
                item(member)
        elif isinstance(value, TVia):
            item(value.target)
            for member in value.edge.values():
                item(member)
        elif isinstance(value, TVar) and value.entity:
            found.add(value.name)

    item(node)
    return found


@dataclasses.dataclass
class Wanted:
    """What the document of a justification is to be"""

    payload: dict[str, Any]
    context: list[str]
    published: bool
    content: str


class LeftOut(Exception):
    """The document cannot be written now (something it rests on, or names, is gone): the write that removed that
    left the work that settles it"""


def wanted(
    rule: CheckedRule, state: dict[str, Any], nodes: dict[str, dict[str, Any]]
) -> Wanted:
    """What the document of the justification is to be: the template of its rule filled with its values, its sources,
    what it passed through (with what the derived documents it rests on passed through), and whether it is published
    (all it rests on is)"""
    values = json.loads(state["values"]) if state["values"] else {}
    entities = entity_variables(rule.template)
    bindings: dict[str, Any] = {}
    for name in rule.head:
        value = values.get(name)
        if name in entities:
            node = nodes.get(str(value))
            if node is None or node["deleted"] or node["merged_into"] is not None:
                raise LeftOut(f"{name} ({value}) is not there")
            bindings[name] = {"type": node["type"], "id": str(value)}
        else:
            bindings[name] = value
    payload = fill(rule.template, bindings)
    field, _ = documents.source_field(rule.model)
    context = set(state["context_labels"] or [])
    published = True
    sources = []
    for source in sorted(str(s) for s in state["sources"] or []):
        node = nodes.get(source)
        if node is None or node["deleted"]:
            raise LeftOut(f"the source {source} is not there")
        sources.append(
            {"type": UNPROTECTED, "target_type": node["type"], "target_id": source}
        )
        context.update(node["derived_context"] or [])
        published = published and bool(node["published"])
    payload[field] = sources
    labels = sorted(context)
    return Wanted(payload, labels, published, digest(rule.name, payload, labels))


@dataclasses.dataclass
class Counts:
    made: int = 0
    changed: int = 0
    deleted: int = 0
    undeleted: int = 0
    published: int = 0
    unpublished: int = 0
    left_out: int = 0
    failed: int = 0
    same: int = 0

    def add(self, other: Counts) -> None:
        for field in dataclasses.fields(self):
            setattr(
                self,
                field.name,
                getattr(self, field.name) + getattr(other, field.name),
            )

    @property
    def written(self) -> int:
        return (
            self.made
            + self.changed
            + self.deleted
            + self.undeleted
            + self.published
            + self.unpublished
        )


async def reconcile(database: Any, ids: Sequence[str]) -> Counts:
    """Make each of the documents what its justification says (see the module). Gives what was done. A document that
    cannot be written (what its template gives is refused) is logged, and counted: it is tried again when what it
    rests on is written again"""
    counts = Counts()
    if not ids:
        return counts

    @database.read_transaction
    async def read(tx: Transaction, query: str, **params: Any) -> list[dict[str, Any]]:
        return await run(tx, query, **params)

    states = await read(STATE_QUERY, ids=list(ids))
    needed: set[str] = set()
    for state in states:
        if state["key"] is None:
            continue
        needed.update(str(s) for s in state["sources"] or [])
        rule = DerivedRegistry.documents.get(state["rule"])
        if rule is not None:
            values = json.loads(state["values"]) if state["values"] else {}
            needed.update(str(values[n]) for n in entity_variables(rule.template))
    nodes: dict[str, dict[str, Any]] = {}
    for part in chunks(sorted(needed), 5000):
        nodes.update({row["id"]: row for row in await read(NODES_QUERY, ids=part)})

    username = await ensure_user()
    with acting_as(username):
        for state in states:
            try:
                await reconcile_one(state, nodes, counts)
            except LeftOut as reason:
                counts.left_out += 1
                logger.debug("Derived document %s left out: %s", state["id"], reason)
            except PanglossWriteError as error:
                counts.failed += 1
                logger.error(
                    "The derived document %s of the rule %s could not be written: %s",
                    state["id"],
                    state["rule"],
                    error,
                )
            except ValueError as error:
                # (what the template gave is not a document of its class: a pydantic `ValidationError`)
                counts.failed += 1
                logger.error(
                    "The derived document %s of the rule %s is not one its class takes: %s",
                    state["id"],
                    state["rule"],
                    error,
                )
    return counts


async def reconcile_one(
    state: dict[str, Any], nodes: dict[str, dict[str, Any]], counts: Counts
) -> None:
    id = uuid.UUID(state["id"])
    stored: Any = (
        ModelRegistry._model_dict.get(state["type"]) if state["there"] else None
    )
    if state["there"] and not documents.is_derived_document(stored):
        # (it has been made a document of someone's own, or its class is no longer one of these: not the worker's)
        return
    if state["key"] is None:
        # -- no justification: the document goes
        if stored is not None and not state["deleted"]:
            with documents.writing_derived(""):
                await stored.delete(id)
            counts.deleted += 1
        return
    rule = DerivedRegistry.documents.get(state["rule"])
    if rule is None:
        # (a rule that is not there any more: what it derived is removed when the rules are brought up to date)
        return
    model: Any = rule.model
    want = wanted(rule, state, nodes)

    def writing() -> Any:
        return documents.writing_derived(
            rule.name,
            want.context,
            id=id,
            published=want.published,
            content=want.content,
        )

    if stored is None:
        with writing():
            await model.Create.model_validate(want.payload).save()
        counts.made += 1
        return
    if stored is not model:
        # (`store_found` gives a rule that derives another class new documents: this is one whose turn has not come)
        raise LeftOut(
            f"it is a {stored.__name__}, and the rule derives {model.__name__}"
        )
    if state["deleted"]:
        with writing():
            await model.undelete(id)
        counts.undeleted += 1
    if state["content"] != want.content:
        with writing():
            await model.Update.model_validate({**want.payload, "id": id}).save()
        counts.changed += 1
    elif bool(state["published"]) != want.published:
        await storage_of().operations.set_published_in_db(model, id, want.published)
        if want.published:
            counts.published += 1
        else:
            counts.unpublished += 1
    elif not state["deleted"]:
        counts.same += 1
