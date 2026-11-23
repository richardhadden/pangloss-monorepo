"""Why a candidate is offered: the entities the payload names that are also named in a stored document together with
the candidate (step 10.3 of implementation_docs/similarity-build-plan.md, "reasons"). Since step 11.2 their number is
in the score too (`score.shared_score`), so they are asked once for every candidate found of a request, before the
cut to `limit`, and uncut: what is shown of them is cut afterwards (`RECONCILE_REASONS`, `api.answer`).

The entities of the payload are those its plan refers to (each `ReferenceToExisting`, a URL as the node it names)
and those written in it that exist, as the write would resolve them (`pangloss_cypher.validate_write.resolved_plan`:
an entity merged into another is its survivor). A stored document shares one with a candidate when, below or in its
head, one node has a forward relation to the candidate and one has a forward relation to that entity.

One query for every candidate of a request, as the reader may see it: the document a head document the reader may
look through (`fragments.listed`: not deleted, published unless the reader may see what is not), not a class whose
references do not count (`fragments.counted`: a derived document), and not the plan's own head (the stored route's
document); the shared entity looked through too; forward edges of fields only (`fragments.forward`), not those of a
relation the server computes (`fragments.reference`), as `pangloss_vectors.search._used` counts a use."""

from collections.abc import Mapping, Sequence
from typing import Any


def _query(fragments: Any) -> str:
    """What the candidates `$candidates` share with the entities `$entities`: each pair, and in how many documents"""
    return f"""
        UNWIND $entities AS xid
        MATCH (x:PGIndexableNode {{id: xid}})
        WHERE {fragments.listed("x")}
        MATCH (x)<-[e2]-(n2:PGIndexableNode)
        WHERE {fragments.forward("e2")}{fragments.reference("e2")}
        WITH xid, collect(DISTINCT coalesce(n2.head_node_id, n2.id)) AS heads
        WITH collect(xid) AS xs, collect(heads) AS hs
        UNWIND $candidates AS cid
        MATCH (c:PGIndexableNode {{id: cid}})<-[e1]-(n1:PGIndexableNode)
        WHERE {fragments.forward("e1")}{fragments.reference("e1")}
        WITH DISTINCT xs, hs, cid, coalesce(n1.head_node_id, n1.id) AS hid
        WHERE hid <> $own
        MATCH (h:HeadNode {{id: hid}})
        WHERE h:Document AND {fragments.listed("h")}{fragments.counted("h")}
        UNWIND range(0, size(xs) - 1) AS i
        WITH cid, hid, xs[i] AS xid, hs[i] AS heads
        WHERE xid <> cid AND hid IN heads
        RETURN cid, xid, count(hid) AS documents
    """


def named_entities(
    plan: Any, existing: Mapping[Any, Any], urls: Mapping[str, str]
) -> list[str]:
    """The ids of the entities a resolved plan refers to, and of those written in it that exist"""
    from pangloss_cypher.write_plan import InlineEntity, ReferenceToExisting

    found: set[str] = set()
    for _, relation, _ in plan.walk(existing):
        target = relation.target
        if isinstance(target, ReferenceToExisting):
            found.add(
                urls.get(target.value, target.value) if target.is_url else target.value
            )
        elif isinstance(target, InlineEntity) and target.key in existing:
            found.add(str(existing[target.key].id))
    return sorted(found)


async def shared(
    plan: Any,
    candidates: Sequence[str],
    see_unpublished: bool,
    most: int | None = None,
) -> dict[str, list[tuple[str, int]]]:
    """For each candidate, every entity of the plan it is named with in stored documents (at most `most`, if given:
    the service gives none, and cuts what it shows itself), each with in how many, those of the most documents first,
    then by id. Nothing is asked with no candidate. (In one read transaction: the plan resolved, and the query)"""
    from pangloss_core import backend
    from pangloss_cypher.validate_write import resolved_plan

    if not candidates:
        return {}
    current = backend.current()
    database = current.database()
    query = _query(current.fragments)

    @database.read_transaction
    async def read(tx: Any) -> list[tuple[str, str, int]]:
        resolved, existing, urls = await resolved_plan(tx, plan)
        entities = named_entities(resolved, existing, urls)
        if not entities:
            return []
        result = await tx.run(
            query,
            candidates=sorted(set(candidates)),
            entities=entities,
            own=str(plan.head.id),
            see_unpublished=see_unpublished,
        )
        return [
            (str(r["cid"]), str(r["xid"]), int(r["documents"])) async for r in result
        ]

    found: dict[str, list[tuple[str, int]]] = {}
    for candidate, entity, documents in await read():
        found.setdefault(candidate, []).append((entity, documents))
    return {
        candidate: sorted(pairs, key=lambda pair: (-pair[1], pair[0]))[:most]
        for candidate, pairs in found.items()
    }
