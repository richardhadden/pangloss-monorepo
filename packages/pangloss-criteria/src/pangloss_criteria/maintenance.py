"""What the commands of `pangloss criteria` do, beside the worker (implementation_docs/matches-criteria.md, "7.
Commands"): evaluate every description again (`rebuild`), say how many there are of each kind (`description_status`),
say what one is and how the worker treats it (`explain`), and find those whose criteria no longer hold (`check`).

`rebuild` writes, and so holds the worker's lease while it runs, as the worker does: nothing else evaluates
descriptions of the database meanwhile, and a worker that is running is not interrupted (it is refused, and says so).
The others only read."""

import dataclasses
import datetime
import json
from typing import Any

from pangloss_core import Transaction, storage_of
from pangloss_cypher import fragments
from pangloss_cypher.search_query import build_search_ids_query
from pangloss_models import ComputedWrite, PanglossSearchError
from pangloss_models.search import check_excluded, check_match, resolve_search_type

from pangloss_criteria import analysis
from pangloss_criteria.evaluate import (
    MAX_AMONG,
    MAX_HEADS,
    Counts,
    Job,
    evaluate_many,
    from_anchors,
    max_candidates,
    referring_heads,
)
from pangloss_criteria.holders import KIND
from pangloss_criteria.models import EXCLUDED, NAME
from pangloss_criteria.pattern import SearchPattern, check_stored, ids_named, with_ids
from pangloss_criteria.worker import (
    EVERY_HEAD_QUERY,
    Description,
    Head,
    Worker,
    database,
    read_heads,
    same_result,
    values_of,
)


class CriteriaWorkerBusy(RuntimeError):
    """Another worker of the same database holds the lease: a rebuild does not run beside it"""


@dataclasses.dataclass
class Rebuilt:
    """What a rebuild did"""

    descriptions: int = 0
    """Looked at (of the class asked for, in documents that are not deleted)"""
    evaluated: int = 0
    """Of those, evaluated (their criteria fit the models)"""
    changed: int = 0
    """Of those evaluated or broken, the ones whose stored result was not what was found: written"""
    broken: int = 0
    """Whose criteria no longer fit the models: marked so, as the worker marks them"""
    refused: int = 0
    """Not written: their document was saved meanwhile (the save marked it: the worker does it again)"""
    anchored: int = 0
    root_first: int = 0


async def _every_head() -> list[str]:
    @database().read_transaction
    async def read(tx: Transaction) -> list[str]:
        return [row["head"] async for row in await tx.run(EVERY_HEAD_QUERY)]

    return sorted(await read())


def _of_class(description: Description, model: type | None) -> bool:
    """Whether a description's criteria are of the class, or a class below it (any, without a class)"""
    if model is None:
        return True
    try:
        found = resolve_search_type(SearchPattern(description.criteria).type)
    except PanglossSearchError, ValueError:
        return False
    return isinstance(found, type) and issubclass(found, model)


async def rebuild(type: str | None = None, chunk: int = 200) -> Rebuilt:
    """Every description (or those whose criteria are of the class `type` or one below it) evaluated in full, and
    written where the result is not what it has: after a bulk load, a migration that touches a class the patterns
    name, or a change of `CRITERIA_MAX_CANDIDATES`. Holds the worker's lease while it runs: raises
    `CriteriaWorkerBusy` if another worker holds it"""
    model = resolve_search_type(type) if type is not None else None
    holder = Worker()
    if not await holder.take_lease():
        raise CriteriaWorkerBusy(
            "Another criteria worker is working on this database (a server, or `pangloss criteria worker`): stop it, "
            "or wait for its lease to run out"
        )
    found = Rebuilt()
    try:
        heads = await _every_head()
        for start in range(0, len(heads), chunk):
            some = heads[start : start + chunk]

            @database().read_transaction
            async def read(
                tx: Transaction, some: list[str] = some
            ) -> tuple[dict[str, Head], list[Description]]:
                return await read_heads(tx, some)

            read_now, descriptions = await read()
            await _rebuild_chunk(read_now, descriptions, model, found)
            if not await holder.take_lease():
                raise CriteriaWorkerBusy(
                    "The lease ran out during the rebuild and another worker took it: the rebuild stopped"
                )
    finally:
        await holder.give_up_lease()
    return found


async def _rebuild_chunk(
    heads: dict[str, Head],
    descriptions: list[Description],
    model: type | None,
    found: Rebuilt,
) -> None:
    when = datetime.datetime.now(datetime.UTC)
    jobs: list[Job] = []
    results: dict[str, Any] = {}
    kept: list[Description] = []
    for description in descriptions:
        head = heads.get(description.head)
        if head is None or head.deleted or description.criteria is None:
            continue
        if not _of_class(description, model):
            continue
        kept.append(description)
        try:
            jobs.append(
                Job(
                    description.id, SearchPattern(description.criteria), set(head.named)
                )
            )
        except ValueError as error:
            results[description.id] = error
    counts = Counts()
    results.update(await evaluate_many(jobs, counts=counts))
    found.descriptions += len(kept)
    found.anchored += counts.anchored
    found.root_first += counts.root_first
    writes: list[ComputedWrite] = []
    for description in kept:
        result = results[description.id]
        if isinstance(result, Exception):
            found.broken += 1
            values: dict[str, Any] = {"broken": str(result), "evaluated_when": when}
        else:
            found.evaluated += 1
            values = values_of(result, when)
        if same_result(description, values):
            continue
        writes.append(
            ComputedWrite(description.id, values, heads[description.head].version)
        )
    if writes:
        # (never `criteria`, as the worker writes them: no description searches through candidates)
        written = await storage_of().operations.set_computed_batch(writes, less=[KIND])
        found.changed += sum(written)
        found.refused += len(written) - sum(written)


# --- what there is ----------------------------------------------------------------------------------------------------


EVERY_DESCRIPTION_QUERY = f"""
    MATCH (d:{NAME})
    WHERE d.criteria IS NOT NULL
    OPTIONAL MATCH (head:HeadNode {{id: d.head_node_id}})
    WITH d, head WHERE head IS NOT NULL AND {fragments.not_deleted("head")}
    RETURN d.id AS id, d.head_node_id AS head, d.criteria AS criteria, d.broken AS broken,
           coalesce(d.candidate_count, 0) AS count,
           size([(d)-[edge:target]->() WHERE {fragments.forward("edge")} | 1]) AS linked
    ORDER BY id
"""


async def _every_description() -> list[dict[str, Any]]:
    @database().read_transaction
    async def read(tx: Transaction) -> list[dict[str, Any]]:
        return [dict(row) async for row in await tx.run(EVERY_DESCRIPTION_QUERY)]

    return await read()


async def description_status() -> dict[str, int]:
    """How many descriptions there are (in documents that are not deleted), and of them: `far` (any write of a class
    they depend on has them evaluated in full); `no_anchor` (evaluated in full root first: every entity of the
    class tested), of which `far_no_anchor` are so after every such write; `too_broad` (more candidates than are
    linked); `broken` (said so on the description by the worker); `not_fitting` (whose criteria do not fit the
    models now, said so or not yet)"""
    found = {
        "descriptions": 0,
        "far": 0,
        "no_anchor": 0,
        "far_no_anchor": 0,
        "too_broad": 0,
        "broken": 0,
        "not_fitting": 0,
    }
    for row in await _every_description():
        found["descriptions"] += 1
        found["broken"] += row["broken"] is not None
        found["too_broad"] += row["count"] > row["linked"]
        try:
            what = analysis.of(SearchPattern(row["criteria"]))
        except ValueError:
            what = None
        if what is None:
            found["not_fitting"] += 1
            continue
        far = what.reach == analysis.FAR
        found["far"] += far
        found["no_anchor"] += not what.anchors
        found["far_no_anchor"] += far and not what.anchors
    return found


# --- one description --------------------------------------------------------------------------------------------------


DESCRIPTION_QUERY = f"""
    MATCH (d:{NAME} {{id: $id}})
    RETURN d.id AS id, d.head_node_id AS head, d.criteria AS criteria, d.broken AS broken,
           d.reach AS reach, d.anchors AS anchors, d.depends_on AS depends_on,
           coalesce(d.candidate_count, 0) AS count, coalesce(d.candidate_count_everyone, 0) AS count_everyone,
           size([(d)-[edge:target]->() WHERE {fragments.forward("edge")} | 1]) AS linked
"""


@dataclasses.dataclass
class Explained:
    """What a description is, and how the worker treats it (`explain`)"""

    id: str
    head: str
    criteria: str
    count: int
    count_everyone: int
    linked: int
    broken: str | None
    depends_on: list[str]
    stored: dict[str, Any]
    """`reach` and `anchors` as they are stored (null: saved before they were worked out)"""
    error: str | None = None
    """Why its criteria do not fit the models now, if they do not (then nothing more is said)"""
    reach: str | None = None
    complete: bool = False
    anchors: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    """Each group: `ids`, `hops`, and `merged` (an id as written, to its survivor's)"""
    chosen_for: list[str] = dataclasses.field(default_factory=list)
    in_full: str = ""
    query: str = ""
    params: dict[str, Any] = dataclasses.field(default_factory=dict)


async def explain(id: str) -> Explained | None:
    """What a description is (local or far, its anchors, complete or not), which writes the worker evaluates it for,
    how it is evaluated in full, and the compiled query of its test. None if there is no description of the id"""
    db = database()

    @db.read_transaction
    async def read(tx: Transaction) -> dict[str, Any] | None:
        record = await (await tx.run(DESCRIPTION_QUERY, id=str(id))).single()
        return dict(record) if record else None

    row = await read()
    if row is None:
        return None
    told = Explained(
        id=row["id"],
        head=row["head"],
        criteria=row["criteria"] or "",
        count=row["count"],
        count_everyone=row["count_everyone"],
        linked=row["linked"],
        broken=row["broken"],
        depends_on=list(row["depends_on"] or []),
        stored={"reach": row["reach"], "anchors": row["anchors"]},
    )
    if not row["criteria"]:
        told.error = "it has no criteria"
        return told
    operations = storage_of().operations
    try:
        pattern = SearchPattern(row["criteria"])
        survivors = await operations.survivors_of(ids_named(pattern))
        resolved = with_ids(pattern, survivors)
        items = check_stored(resolved, None, EXCLUDED)
        model = resolve_search_type(resolved.type)
    except (PanglossSearchError, ValueError) as error:
        told.error = str(error)
        return told
    # (what the worker chooses by: the pattern as written; what it evaluates: the ids resolved)
    written = analysis.analyse(model, check_stored(pattern, None, EXCLUDED))
    found = analysis.analyse(model, items)
    told.reach, told.complete = written.reach, written.complete
    told.anchors = [
        {
            "ids": list(anchor.ids),
            "hops": anchor.hops,
            "merged": {i: survivors[i] for i in anchor.ids if i in survivors},
        }
        for anchor in written.anchors
    ]
    told.chosen_for = _chosen_for(written, row)
    told.in_full = await _in_full(found)

    @db.read_transaction
    async def read_head(tx: Transaction) -> Head | None:
        heads, _ = await read_heads(tx, [row["head"]])
        return heads.get(row["head"])

    head = await read_head()
    match = resolved.match(EXCLUDED)
    query, params = build_search_ids_query(
        model,
        check_match(model, match),
        max_candidates(),
        True,
        check_excluded(match),
        sorted(head.named) if head else None,
    )
    told.query = query
    told.params = json.loads(json.dumps(params, default=str))
    return told


def _chosen_for(written: analysis.Analysis, row: dict[str, Any]) -> list[str]:
    """Which writes the worker evaluates the description for, in words (the table of `pangloss_criteria.worker`)"""
    depends = ", ".join(row["depends_on"] or []) or "(none)"
    said = [
        "every save of its own document: evaluated in full",
        "a write of an entity its criteria name, or that was merged into one of them or one of them into it: "
        "evaluated in full",
    ]
    if written.reach == analysis.FAR:
        said.append(
            f"every write of a head with a node of a class it depends on ({depends}), now or before the write: "
            "evaluated in full (far: a write may change a match of an entity it does not name)"
        )
        return said
    said.append(
        f"while it has more candidates than are linked, every write of a head with a node of a class it depends on "
        f"({depends}): evaluated in full"
    )
    if written.complete:
        groups = " and ".join(
            "one of " + ", ".join(anchor.ids) if len(anchor.ids) > 1 else anchor.ids[0]
            for anchor in written.anchors
        )
        said.append(
            f"a write of a head that names (now or before the write) {groups}: evaluated among what those heads "
            "name and its candidates (complete: a write that does not name them cannot change the result)"
        )
        said.append("a write of one of its candidates: evaluated among its candidates")
    else:
        said.append(
            f"every write of a head with a node of a class it depends on ({depends}), now or before the write: "
            "evaluated among what the batch names and its candidates"
        )
    return said


async def _in_full(found: analysis.Analysis) -> str:
    """How a full evaluation is made: from which anchor (the one `from_anchors` chooses), or root first"""
    if not found.anchors:
        return "root first: every entity of the class is tested (the criteria name no entity)"

    @database().read_transaction
    async def read(tx: Transaction) -> tuple[dict[str, list[str]], dict[str, set[str]]]:
        ids = [id for anchor in found.anchors for id in anchor.ids]
        return await referring_heads(tx, ids), await from_anchors(tx, {"it": found})

    referring, among = await read()

    def cost(anchor: analysis.Anchor) -> tuple[int, int]:
        return anchor.hops, sum(len(referring[id]) for id in anchor.ids)

    chosen = min(found.anchors, key=cost)
    heads = len({head for id in chosen.ids for head in referring[id]})
    where = ", ".join(chosen.ids)
    if "it" not in among:
        return (
            f"root first: the anchor it would be evaluated from ({where}, {chosen.hops} hops, {heads} heads refer "
            f"to it) has more around it than is read (more than {MAX_HEADS} heads or {MAX_AMONG} entities)"
        )
    return (
        f"from the anchor {where} ({chosen.hops} hops): {heads} heads refer to it, and the criteria are tested of "
        f"the {len(among['it'])} ids around it"
    )


# --- what no longer holds ---------------------------------------------------------------------------------------------


NAMED_QUERY = f"""
    UNWIND $ids AS id
    OPTIONAL MATCH (n:PGIndexableNode {{id: id}})
    OPTIONAL MATCH (h:HeadNode {{id: n.head_node_id}})
    RETURN id, n IS NOT NULL AS found, {fragments.deleted("n")} OR {fragments.deleted("h")} AS deleted
"""


@dataclasses.dataclass(frozen=True)
class Problem:
    description: str
    head: str
    problem: str


async def check() -> tuple[list[Problem], list[Problem]]:
    """The descriptions (in documents that are not deleted) whose criteria no longer pass `check_stored`, or that name
    an entity that is deleted or not there; and, apart, the ids they name of entities that were merged into others
    (not a problem: an id is resolved when the criteria are evaluated)"""
    rows = await _every_description()
    patterns: dict[str, SearchPattern] = {}
    problems: list[Problem] = []
    merged: list[Problem] = []
    for row in rows:
        try:
            patterns[row["id"]] = SearchPattern(row["criteria"])
        except ValueError as error:
            problems.append(Problem(row["id"], row["head"], f"criteria: {error}"))
    named = sorted({i for p in patterns.values() for i in ids_named(p)})
    survivors = await storage_of().operations.survivors_of(named) if named else {}

    @database().read_transaction
    async def read(tx: Transaction) -> dict[str, dict[str, Any]]:
        asked = sorted(set(named) | set(survivors.values()))
        return {
            row["id"]: dict(row) async for row in await tx.run(NAMED_QUERY, ids=asked)
        }

    state = await read() if named else {}
    for row in rows:
        pattern = patterns.get(row["id"])
        if pattern is None:
            continue
        try:
            check_stored(with_ids(pattern, survivors), None, EXCLUDED)
        except (PanglossSearchError, ValueError) as error:
            problems.append(Problem(row["id"], row["head"], f"criteria: {error}"))
        for id in ids_named(pattern):
            survivor = survivors.get(id)
            if survivor is not None:
                merged.append(
                    Problem(row["id"], row["head"], f"{id} merged into {survivor}")
                )
            final = state.get(survivor or id, {})
            if not final.get("found"):
                problems.append(
                    Problem(
                        row["id"],
                        row["head"],
                        f"names {survivor or id}, which is not there",
                    )
                )
            elif final.get("deleted"):
                problems.append(
                    Problem(
                        row["id"],
                        row["head"],
                        f"names {survivor or id}, which is deleted",
                    )
                )
    return problems, merged


__all__ = [
    "CriteriaWorkerBusy",
    "Explained",
    "Problem",
    "Rebuilt",
    "check",
    "description_status",
    "explain",
    "rebuild",
]
