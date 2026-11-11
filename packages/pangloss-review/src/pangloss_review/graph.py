"""What review reads from the graph for its tasks: the unreconciled mentions and the identifications a toolchain made,
with the documents they are in. (The state of a document, its comments and the queue are the backend's own functions:
`service`.) Through `pangloss_core.backend`, so on any backend that runs Cypher.

A task is not stored: an `Unreconciled` in a document *is* one while it is there, so there is nothing to keep in step
with writes. What a query finds is a node of a document; whether the reader sees it is the rule of its head
(`fragments.visible`).

The head of a part is found by its id **after a `WITH`** (`MATCH (u:Unreconciled) WITH u MATCH (head:HeadNode {id:
u.head_node_id})`). Without it Memgraph, given a condition on the head, joins the parts to a scan of every head node
(145,000 of them: 110 ms to count 24,000 mentions, against 29 ms by the index of ids; measured 2026-11-10,
implementation_docs/large-data.md).
"""

from typing import Any

from pangloss_core import backend
from pangloss_core.backend import Transaction

from pangloss_review.meta import UNRECONCILED

# (the class of `pangloss-library`, by its name: review does not need the library, and has these tasks only when the
# project's models have the class)
SUGGESTED = "IdentificationByToolchain"


def suggestion_labels() -> list[str]:
    """The classes whose nodes are suggestions: `IdentificationByToolchain` and a project's subclasses of it. Each by
    its own label, as a node does not have the label of a generic class its class is made from"""
    from pangloss_models import ModelRegistry

    return sorted(
        name
        for name, model in ModelRegistry._model_dict.items()
        # (the classes as declared: one bound to what it holds, `Name[...]`, is written with the label of its class)
        if name.isidentifier()
        and any(base.__name__ == SUGGESTED for base in getattr(model, "__mro__", ()))
    )


def has_a_label(node: str, labels: list[str]) -> str:
    """(of a node already found) That it has one of the labels. Not `node:A OR node:B`: where both labels have an
    index, Memgraph plans that as a union of two scans by label, and what was bound before it (the `id` of an
    `UNWIND $ids AS id`) is lost to the conditions after it, so that only one of the ids is found"""
    if len(labels) == 1:
        return f"{node}:{labels[0]}"
    names = ", ".join(f"'{label}'" for label in labels)
    return f"any(label IN labels({node}) WHERE label IN [{names}])"


def _is_suggestion(node: str) -> str:
    """(of a node already found) That it is a suggestion"""
    return has_a_label(node, suggestion_labels())


def _match_suggestions(node: str) -> str:
    """All the suggestions, each class from its own label index: the plain match where there is one class (as
    measured: `large-data.md`), a union of them where a project has its own"""
    labels = suggestion_labels()
    if len(labels) == 1:
        return f"MATCH ({node}:{labels[0]})"
    union = " UNION ALL ".join(
        f"MATCH ({node}:{label}) RETURN {node}" for label in labels
    )
    return f"CALL {{ {union} }}"


# How many candidates a search for similar mentions reads at most (they are scored afterwards)
CANDIDATE_LIMIT = 3000


def _database():
    return backend.current().database()


def _fragments():
    return backend.current().fragments


def _see_unpublished() -> bool:
    return backend.current().unpublished_visible()


def _mention_fields(node: str, head: str) -> str:
    return f"""{{
        id: {node}.id, label: {node}.label, label_key: {node}.label_key,
        unreconciled_type: {node}.unreconciled_type, uris: coalesce({node}.uris, []),
        head_id: {head}.id, head_type: {head}.type, head_label: {head}.label,
        assigned_to: {head}.review_assigned_to
    }}"""


async def mention(id: str) -> dict[str, Any] | None:
    """An unreconciled mention the reader sees, with the head of the document it is in"""
    database = _database()
    fragments = _fragments()

    @database.read_transaction
    async def read(tx: Transaction) -> dict[str, Any] | None:
        result = await tx.run(
            f"""
            MATCH (u:PGIndexableNode {{id: $id}})
            WHERE u:{UNRECONCILED}
            WITH u
            MATCH (head:HeadNode {{id: u.head_node_id}})
            WHERE {fragments.visible("head")}
            RETURN {_mention_fields("u", "head")} AS mention
            """,
            id=id,
            see_unpublished=_see_unpublished(),
        )
        record = await result.single()
        return dict(record["mention"]) if record else None

    return await read()


async def mentions(
    type: str | None,
    key: str | None,
    assigned_to: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """A page of the unreconciled mentions the reader sees, by label: of an entity class (`type`), whose folded label
    has `key` in it, in documents given to a user to review (`assigned_to`; an empty name: to no one)"""
    database = _database()
    fragments = _fragments()

    @database.read_transaction
    async def read(tx: Transaction) -> dict[str, Any]:
        result = await tx.run(
            f"""
            MATCH (u:{UNRECONCILED})
            WHERE ($type IS NULL OR u.unreconciled_type = $type)
              AND ($key IS NULL OR u.label_key CONTAINS $key)
            WITH u
            MATCH (head:HeadNode {{id: u.head_node_id}})
            WHERE {fragments.visible("head")}
              AND ($assigned_to IS NULL OR coalesce(head.review_assigned_to, '') = $assigned_to)
            WITH u, head
            ORDER BY u.label_key, u.id
            WITH collect([u, head]) AS found
            RETURN size(found) AS count,
                   [pair IN found[$start .. $end] | {_mention_fields("pair[0]", "pair[1]")}] AS results
            """,
            type=type,
            key=key,
            assigned_to=assigned_to,
            start=(page - 1) * page_size,
            end=page * page_size,
            see_unpublished=_see_unpublished(),
        )
        record = await result.single()
        assert record is not None
        return {
            "count": record["count"],
            "results": [dict(r) for r in record["results"]],
        }

    return await read()


async def task_counts(statuses: list[str], assigned_to: str | None) -> dict[str, int]:
    """How many tasks the reader sees of each kind: documents in the statuses, unreconciled mentions, identifications a
    toolchain suggested (if the models have them); of everyone, or in documents given to a user (an empty name: to no
    one). Counted, with nothing of them read"""
    database = _database()
    fragments = _fragments()
    assigned = (
        "($assigned_to IS NULL OR coalesce(head.review_assigned_to, '') = $assigned_to)"
    )

    def of_parts(match: str) -> str:
        return f"""
            {match}
            WITH part
            MATCH (head:HeadNode {{id: part.head_node_id}})
            WHERE {fragments.visible("head")} AND {assigned}
            RETURN count(part) AS count
            """

    @database.read_transaction
    async def read(tx: Transaction) -> dict[str, int]:
        params = {"assigned_to": assigned_to, "see_unpublished": _see_unpublished()}
        documents = await tx.run(
            f"""
            MATCH (head:HeadNode)
            WHERE NOT head:Entity AND head.review_status IN $statuses
              AND {fragments.visible("head")} AND {assigned}
            RETURN count(head) AS count
            """,
            statuses=statuses,
            **params,
        )
        counts = {"documents": (await documents.single())["count"]}
        from pangloss_models import ModelRegistry

        for kind, label, match in (
            ("reconciliations", UNRECONCILED, f"MATCH (part:{UNRECONCILED})"),
            ("identifications", SUGGESTED, None),
        ):
            if label not in ModelRegistry._model_dict:
                counts[kind] = 0
                continue
            result = await tx.run(
                of_parts(match or _match_suggestions("part")), **params
            )
            counts[kind] = (await result.single())["count"]
        return counts

    return await read()


async def mention_types() -> list[dict[str, Any]]:
    """How many unreconciled mentions the reader sees of each entity class"""
    database = _database()
    fragments = _fragments()

    @database.read_transaction
    async def read(tx: Transaction) -> list[dict[str, Any]]:
        result = await tx.run(
            f"""
            MATCH (u:{UNRECONCILED})
            WITH u
            MATCH (head:HeadNode {{id: u.head_node_id}})
            WHERE {fragments.visible("head")}
            RETURN u.unreconciled_type AS type, count(u) AS count
            ORDER BY type
            """,
            see_unpublished=_see_unpublished(),
        )
        return [dict(record) async for record in result]

    return await read()


async def same_label(id: str, type: str, key: str) -> list[str]:
    """The ids of the other mentions of the same entity class with the same folded label: by the index of it, so all
    of them (up to `CANDIDATE_LIMIT`), however many mentions there are"""
    database = _database()

    @database.read_transaction
    async def read(tx: Transaction) -> list[str]:
        result = await tx.run(
            f"""
            MATCH (u:{UNRECONCILED} {{label_key: $key}})
            WHERE u.unreconciled_type = $type AND u.id <> $id
            RETURN u.id AS id
            LIMIT {CANDIDATE_LIMIT}
            """,
            id=id,
            type=type,
            key=key,
        )
        return [record["id"] async for record in result]

    return await read()


async def near_labels(id: str, type: str, key: str, words: list[str]) -> dict[str, str]:
    """The other mentions of the same entity class whose folded label has one of `words` in it and is not `key`: the
    id and the folded label of each, to be scored. Those with the most of the words first, and no more than
    `CANDIDATE_LIMIT` (a common word is in thousands of labels). Nothing else of them is read here: what is kept
    after scoring is read by `mentions_by_id`"""
    if not words:
        return {}
    database = _database()

    @database.read_transaction
    async def read(tx: Transaction) -> dict[str, str]:
        result = await tx.run(
            f"""
            MATCH (u:{UNRECONCILED})
            WHERE u.unreconciled_type = $type AND u.id <> $id AND u.label_key <> $key
            WITH u, size([word IN $words WHERE u.label_key CONTAINS word]) AS shared
            WHERE shared > 0
            RETURN u.id AS id, u.label_key AS label_key
            ORDER BY shared DESC
            LIMIT {CANDIDATE_LIMIT}
            """,
            id=id,
            type=type,
            key=key,
            words=words,
        )
        return {record["id"]: record["label_key"] async for record in result}

    return await read()


async def mentions_by_id(ids: list[str]) -> list[dict[str, Any]]:
    """Those of the mentions (by id) that the reader sees, each with the head of its document"""
    if not ids:
        return []
    database = _database()
    fragments = _fragments()

    @database.read_transaction
    async def read(tx: Transaction) -> list[dict[str, Any]]:
        result = await tx.run(
            f"""
            UNWIND $ids AS id
            MATCH (u:PGIndexableNode {{id: id}})
            WHERE u:{UNRECONCILED}
            WITH u
            MATCH (head:HeadNode {{id: u.head_node_id}})
            WHERE {fragments.visible("head")}
            RETURN {_mention_fields("u", "head")} AS mention
            """,
            ids=ids,
            see_unpublished=_see_unpublished(),
        )
        return [dict(record["mention"]) async for record in result]

    return await read()


async def holders(ids: list[str]) -> dict[str, dict[str, Any]]:
    """For each node of a document (by id), the document it is directly in: the nearest node above it that is a
    document (what is between is wrappers: a reified relation, a conjunction, a space). A step up is the reverse edge
    of the relation that holds a node; a few steps, a query for each, whatever the number of nodes"""
    database = _database()

    @database.read_transaction
    async def read(tx: Transaction) -> dict[str, dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        # (where the climb of each node has got to)
        at = {id: id for id in ids}
        for _ in range(12):
            if not at:
                break
            result = await tx.run(
                """
                UNWIND $ids AS id
                MATCH (node:PGIndexableNode {id: id})-[edge]->(above:PGIndexableNode)
                WHERE edge.reverse = true AND NOT above:Entity
                RETURN id, above.id AS above_id, above.type AS type, above.label AS label,
                       above:Document AS is_document
                """,
                ids=sorted(set(at.values())),
            )
            above = {record["id"]: dict(record) async for record in result}
            still: dict[str, str] = {}
            for start, current in at.items():
                step = above.get(current)
                if step is None:
                    continue
                if step["is_document"]:
                    found[start] = {
                        "id": step["above_id"],
                        "type": step["type"],
                        "label": step["label"],
                    }
                else:
                    still[start] = step["above_id"]
            at = still
        return found

    return await read()


async def urls_taken(urls: list[str], entity_id: str) -> dict[str, str]:
    """Of the URLs, those that another entity has (a URL is of one entity): each with the id of the entity"""
    if not urls:
        return {}
    database = _database()

    @database.read_transaction
    async def read(tx: Transaction) -> dict[str, str]:
        result = await tx.run(
            """
            UNWIND $urls AS url
            MATCH (:PGUrl {url: url})<-[:has_url]-(entity)
            WHERE entity.id <> $entity_id
            RETURN url, entity.id AS id
            """,
            urls=urls,
            entity_id=entity_id,
        )
        return {record["url"]: record["id"] async for record in result}

    return await read()


async def head_entities(head_ids: list[str], fields: list[str]) -> dict[str, dict]:
    """For each head document, the ids of the entities each of the fields holds, directly or in a wrapper (a reified
    relation: a source at a page) (for a rule that two documents go together when they have the same:
    `ReviewMeta(reconcile_together=("source",))`)"""
    database = _database()

    @database.read_transaction
    async def read(tx: Transaction) -> dict[str, dict]:
        result = await tx.run(
            """
            UNWIND $ids AS id
            MATCH (head:HeadNode {id: id})-[edge]->(held)
            WHERE type(edge) IN $fields AND NOT coalesce(edge.reverse, false)
            // (through a wrapper: a source at a page is the source)
            OPTIONAL MATCH (held)-[inner]->(within:Entity)
            WHERE NOT held:Entity AND NOT coalesce(inner.reverse, false)
            WITH id, type(edge) AS field, coalesce(within, held) AS entity
            WHERE entity:Entity
            RETURN id, field, collect(DISTINCT entity.id) AS held
            """,
            ids=head_ids,
            fields=fields,
        )
        found: dict[str, dict] = {id: {} for id in head_ids}
        async for record in result:
            found[record["id"]][record["field"]] = frozenset(record["held"])
        return found

    return await read()


# --- identifications that a toolchain suggested ----------------------------------------------------------------------


def _suggestion_fields(node: str, head: str) -> str:
    return f"""{{
        id: {node}.id, type: {node}.type, identified_by: {node}.identified_by, toolchain_version: {node}.toolchain_version,
        uris: coalesce({node}.uris, []),
        head_id: {head}.id, head_type: {head}.type, head_label: {head}.label,
        assigned_to: {head}.review_assigned_to
    }}"""


async def suggestions(
    assigned_to: str | None, page: int, page_size: int
) -> dict[str, Any]:
    """A page of the identifications a toolchain suggested that the reader sees, the oldest first (an id says when it
    was made), in documents given to a user to review (`assigned_to`; an empty name: to no one)"""
    database = _database()
    fragments = _fragments()

    @database.read_transaction
    async def read(tx: Transaction) -> dict[str, Any]:
        result = await tx.run(
            f"""
            {_match_suggestions("i")}
            WITH i
            MATCH (head:HeadNode {{id: i.head_node_id}})
            WHERE {fragments.visible("head")}
              AND ($assigned_to IS NULL OR coalesce(head.review_assigned_to, '') = $assigned_to)
            WITH i, head
            ORDER BY i.id
            WITH collect([i, head]) AS found
            RETURN size(found) AS count,
                   [pair IN found[$start .. $end] | {_suggestion_fields("pair[0]", "pair[1]")}] AS results
            """,
            assigned_to=assigned_to,
            start=(page - 1) * page_size,
            end=page * page_size,
            see_unpublished=_see_unpublished(),
        )
        record = await result.single()
        assert record is not None
        return {
            "count": record["count"],
            "results": [dict(r) for r in record["results"]],
        }

    return await read()


async def suggestions_by_id(ids: list[str]) -> list[dict[str, Any]]:
    """Those of the identifications a toolchain suggested (by id) that the reader sees"""
    if not ids:
        return []
    database = _database()
    fragments = _fragments()

    @database.read_transaction
    async def read(tx: Transaction) -> list[dict[str, Any]]:
        result = await tx.run(
            f"""
            UNWIND $ids AS id
            MATCH (i:PGIndexableNode {{id: id}})
            WHERE {_is_suggestion("i")}
            WITH i
            MATCH (head:HeadNode {{id: i.head_node_id}})
            WHERE {fragments.visible("head")}
            RETURN {_suggestion_fields("i", "head")} AS suggestion
            """,
            ids=ids,
            see_unpublished=_see_unpublished(),
        )
        return [dict(record["suggestion"]) async for record in result]

    return await read()


async def candidates(ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """For each identification (by id), who it could be: the entity that is its target, or the entities its target
    holds (the alternatives of a `WeightedAlternative`, each with its `percent`), in the order written"""
    if not ids:
        return {}
    database = _database()

    @database.read_transaction
    async def read(tx: Transaction) -> dict[str, list[dict[str, Any]]]:
        result = await tx.run(
            """
            UNWIND $ids AS id
            MATCH (i:PGIndexableNode {id: id})-[:target]->(held)
            OPTIONAL MATCH (held)-[edge]->(one:Entity)
            WHERE NOT held:Entity AND NOT coalesce(edge.reverse, false)
            WITH id, coalesce(one, held) AS candidate, edge
            WHERE candidate:Entity
            RETURN id, candidate.id AS candidate_id, candidate.type AS type, candidate.label AS label,
                   edge.percent AS percent, coalesce(edge.pg_position, 0) AS position
            """,
            ids=ids,
        )
        found: dict[str, list[dict[str, Any]]] = {id: [] for id in ids}
        async for record in result:
            found[record["id"]].append(
                {
                    "id": record["candidate_id"],
                    "type": record["type"],
                    "label": record["label"],
                    "percent": record["percent"],
                    "position": record["position"],
                }
            )
        for held in found.values():
            held.sort(
                key=lambda candidate: (candidate.pop("position"), candidate["id"])
            )
        return found

    return await read()


async def suggestions_of(entity_id: str) -> list[str]:
    """The ids of the identifications a toolchain suggested that have the entity as a candidate: it is their target,
    or held by their target. From the entity, so that the others are not read"""
    database = _database()

    @database.read_transaction
    async def read(tx: Transaction) -> list[str]:
        result = await tx.run(
            f"""
            MATCH (candidate:HeadNode {{id: $id}})<-[edge]-(holder)
            WHERE NOT coalesce(edge.reverse, false)
            OPTIONAL MATCH (holder)<-[:target]-(above)
            WHERE {_is_suggestion("above")}
            WITH CASE WHEN {_is_suggestion("holder")} THEN holder ELSE above END AS suggestion
            WHERE suggestion IS NOT NULL
            RETURN DISTINCT suggestion.id AS id
            """,
            id=entity_id,
        )
        return [record["id"] async for record in result]

    return await read()
