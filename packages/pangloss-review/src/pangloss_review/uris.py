"""Which parts of documents name a URI: the unreconciled mentions and the identifications a toolchain suggested that
were given URIs for who is meant (`uris`).

Two parts that name the same URI are of the same person, whoever that is, so they are found by it. The URIs of a part
are a list on its node, which no index finds a member of (55 ms to look at 500,000 parts, measured 2026-11-11:
implementation_docs/large-data.md). So each is also a node of its own, found by an index in 0.3 ms:

    (:PGUriClaim {uri, part_id, head_id, kind})         kind: "mention" or "suggestion"

It has no edges: nothing that reads or rewrites a document meets it. It is brought up to date after a write, not in
it: a write of a document marks its head as pending in its own transaction (`pangloss_cypher.pending`, kind
`review-uris`), so no write is forgotten, and the marks are worked off (`drain`) by the process that wrote, in the
background, and by whatever asks who names a URI, first. A claim is only where to look: what is found by one is read
again as it is now (`graph.mentions_by_id`, `suggestions_by_id`).
"""

import asyncio
import logging
from typing import Any

from pangloss_core.backend import Transaction
from pangloss_cypher import pending
from pangloss_models import Document, ModelRegistry

from pangloss_review import graph
from pangloss_review.meta import UNRECONCILED

logger = logging.getLogger("pangloss.review")

KIND = "review-uris"
LABEL = "PGUriClaim"
# How many heads are brought up to date in one transaction
BATCH = 200
# How many parts that name a URI are read at most (a URI of someone famous may be named by thousands)
NAMED_LIMIT = 200


def has_parts() -> bool:
    """Whether the project's models have parts that name URIs at all"""
    return UNRECONCILED in ModelRegistry._model_dict or bool(graph.suggestion_labels())


def pending_work_of(model: type) -> list[str]:
    """(`hooks.pending_work`) A write of a document leaves its URIs to be brought up to date"""
    if isinstance(model, type) and issubclass(model, Document) and has_parts():
        return [KIND]
    return []


def _is_part(node: str) -> str:
    return graph.has_a_label(node, [UNRECONCILED, *graph.suggestion_labels()])


def _claims_of(heads: str) -> str:
    """Replace the claims of the heads (a list parameter) by what their parts name now"""
    return f"""
    UNWIND {heads} AS head_id
    MATCH (part:PGIndexableNode {{head_node_id: head_id}})
    WHERE {_is_part("part")} AND size(coalesce(part.uris, [])) > 0
    UNWIND part.uris AS uri
    CREATE (:{LABEL} {{
        uri: uri, part_id: part.id, head_id: head_id,
        kind: CASE WHEN part:{UNRECONCILED} THEN 'mention' ELSE 'suggestion' END
    }})
    """


async def _replace(tx: Transaction, heads: list[str]) -> None:
    await (
        await tx.run(
            f"UNWIND $heads AS head_id MATCH (claim:{LABEL} {{head_id: head_id}}) DELETE claim",
            heads=heads,
        )
    ).consume()
    await (await tx.run(_claims_of("$heads"), heads=heads)).consume()


# (one at a time in a process: two that claim the same marks conflict, and the second would wait to be run again)
_draining: dict[int, asyncio.Lock] = {}


def _one_at_a_time() -> asyncio.Lock:
    loop = id(asyncio.get_running_loop())
    if loop not in _draining:
        _draining.clear()
        _draining[loop] = asyncio.Lock()
    return _draining[loop]


async def drain() -> int:
    """Bring the claims of every head that was written since up to date. Gives how many heads"""
    if not has_parts():
        return 0
    database = graph._database()
    done = 0
    async with _one_at_a_time():
        while True:

            @database.write_transaction
            async def batch(tx: Transaction) -> int:
                # (claimed, done and completed in one transaction: one that fails leaves the marks as they were)
                claimed = await pending.claim(tx, KIND, BATCH, lease=60)
                if claimed:
                    await _replace(tx, [head_id for head_id, _ in claimed])
                    await pending.complete(tx, KIND, claimed)
                return len(claimed)

            count = await batch()
            done += count
            if count < BATCH:
                return done


async def rebuild() -> int:
    """Make every claim again from the parts there are (after a bulk load, or data from before there were claims).
    Gives how many claims there are then"""
    database = graph._database()

    @database.write_transaction
    async def forget(tx: Transaction) -> int:
        result = await tx.run(
            f"MATCH (claim:{LABEL}) WITH claim LIMIT 50000 DELETE claim RETURN count(*) AS gone"
        )
        record = await result.single()
        return record["gone"] if record else 0

    while await forget():
        pass
    if not has_parts():
        return 0

    @database.write_transaction
    async def make(tx: Transaction) -> int:
        made = 0
        for label in [UNRECONCILED, *graph.suggestion_labels()]:
            kind = "mention" if label == UNRECONCILED else "suggestion"
            result = await tx.run(
                f"""
                MATCH (part:{label})
                WHERE size(coalesce(part.uris, [])) > 0
                UNWIND part.uris AS uri
                CREATE (:{LABEL} {{uri: uri, part_id: part.id, head_id: part.head_node_id, kind: $kind}})
                RETURN count(*) AS made
                """,
                kind=kind,
            )
            record = await result.single()
            made += record["made"] if record else 0
        return made

    return await make()


async def naming(uris: list[str], except_id: str | None = None) -> dict[str, list[str]]:
    """The parts that name one of the URIs, but for one: the ids of the mentions and of the suggestions (`"mention"`,
    `"suggestion"`), as the claims have them, brought up to date first"""
    found: dict[str, list[str]] = {"mention": [], "suggestion": []}
    uris = list(dict.fromkeys(str(uri) for uri in uris))
    if not uris:
        return found
    await drain()
    database = graph._database()

    @database.read_transaction
    async def read(tx: Transaction) -> list[dict[str, Any]]:
        result = await tx.run(
            f"""
            UNWIND $uris AS uri
            MATCH (claim:{LABEL} {{uri: uri}})
            WHERE claim.part_id <> $except_id
            RETURN DISTINCT claim.part_id AS id, claim.kind AS kind
            LIMIT $limit
            """,
            uris=uris,
            except_id=except_id or "",
            limit=NAMED_LIMIT,
        )
        return [dict(record) async for record in result]

    for row in await read():
        found.setdefault(row["kind"], []).append(row["id"])
    return found


async def entities_with(uris: list[str]) -> list[dict[str, Any]]:
    """The entities that have one of the URIs as a URL of their own: who the URI is, in the database"""
    uris = list(dict.fromkeys(str(uri) for uri in uris))
    if not uris:
        return []
    database = graph._database()
    fragments = graph._fragments()

    @database.read_transaction
    async def read(tx: Transaction) -> list[dict[str, Any]]:
        result = await tx.run(
            f"""
            UNWIND $uris AS uri
            MATCH (:PGUrl {{url: uri}})<-[:has_url]-(entity:HeadNode)
            WHERE {fragments.visible("entity")}
            RETURN DISTINCT entity.id AS id, entity.type AS type, entity.label AS label
            """,
            uris=uris,
            see_unpublished=graph._see_unpublished(),
        )
        return [dict(record) async for record in result]

    return await read()
