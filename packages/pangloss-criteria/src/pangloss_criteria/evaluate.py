"""Evaluating a description: what its criteria find, under the rules of "What is searched"
(implementation_docs/matches-criteria.md).

1. Not through other descriptions (`EXCLUDED`).
2. Not what the same document names (`without`).
3. Two results, by what may be seen: one of what everyone sees, one of what a logged-in reader sees.
4. A cap: at most so many are linked, the first by label. The counts are of all.
5. The ids of merged entities are resolved first.
"""

import dataclasses
from collections.abc import Iterable
from typing import Any, LiteralString, cast

from pangloss_core import Transaction, backend, storage_of
from pangloss_core import settings as core_settings
from pangloss_cypher import fragments
from pangloss_models import ComputedTarget, PanglossSearchError
from pangloss_models.computed import EVERYONE, LOGGED_IN
from pangloss_models.search import resolve_search_type

from pangloss_criteria.analysis import Analysis, Anchor, analyse
from pangloss_criteria.models import EXCLUDED
from pangloss_criteria.pattern import (
    SearchPattern,
    check_stored,
    ids_named,
    resolve_merged,
    with_ids,
)

DEFAULT_MAX_CANDIDATES = 50


def max_candidates() -> int:
    """`CRITERIA_MAX_CANDIDATES`: how many candidates of a description are linked (50)"""
    settings = core_settings.__dict__.get("SETTINGS")
    return int(getattr(settings, "CRITERIA_MAX_CANDIDATES", DEFAULT_MAX_CANDIDATES))


@dataclasses.dataclass(frozen=True)
class Evaluation:
    """What a description's criteria find: the candidates to link (the first by label, each with who may see it),
    with their labels, and how many there are in all, for a logged-in reader and for everyone"""

    candidates: list[dict[str, Any]]
    """`{id, type, label, seen_by}`, in the order of their labels"""
    count: int
    count_everyone: int

    @property
    def targets(self) -> list[ComputedTarget]:
        return [ComputedTarget(c["id"], c["seen_by"]) for c in self.candidates]

    @property
    def too_broad(self) -> bool:
        return self.count > len(self.candidates)


async def evaluate(
    pattern: SearchPattern,
    without: Iterable[str] = (),
    limit: int | None = None,
) -> Evaluation:
    """Evaluate criteria in full. `without`: the ids of the entities the description's own document names, which
    are never its candidates. Raises `PanglossSearchError` if the pattern no longer fits the models"""
    limit = max_candidates() if limit is None else limit
    resolved = await resolve_merged(pattern)
    check_stored(resolved, None, EXCLUDED)
    model = resolve_search_type(resolved.type)
    match = resolved.match(EXCLUDED)
    search_ids = getattr(storage_of().operations, "search_ids", None)
    if search_ids is None:
        raise PanglossSearchError(
            "Criteria are evaluated on the server: this storage cannot evaluate them"
        )
    left_out = sorted(set(without))
    everyone = await search_ids(
        model, match, limit=limit, see_unpublished=False, without=left_out
    )
    logged_in = await search_ids(
        model, match, limit=limit, see_unpublished=True, without=left_out
    )
    return _evaluation(logged_in, everyone)


# --- many at once -------------------------------------------------------------------------------------------------------
#
# The worker evaluates many descriptions in a batch. Each is evaluated **among** some ids: the search is made of
# those entities only, found by their index, and searches of one shape are one query (`operations.search_ids_among`).
#
# - **Seeded**: among the ids its caller gives (the entities a batch of writes names, with the candidates it has).
# - **From an anchor**: in full, among what is joined to an entity the criteria name (`analysis`): the heads that
#   refer to the anchor, and what those heads name. Every match is among them, and the criteria are then tested of
#   each as any search tests them, so this is exact whatever the pattern holds (wrappers, `through`, conditions on
#   an edge).
# - **Root first**: in full, every entity of the class tested (`evaluate`), where the criteria name no entity, or
#   the anchor's neighbourhood is larger than `MAX_AMONG`.

MAX_AMONG = 5000
"""The most entities a full evaluation from an anchor is made among: past it, root first"""

MAX_HEADS = 5000
"""The most heads referring to an anchor that are read for what they name"""

MAX_WITHOUT = 200
"""The most ids a description's own document may name for it to take the result of a group of identical criteria
(`evaluate_many`): the group's result is fetched with that many more candidates"""


@dataclasses.dataclass
class Job:
    """One description to evaluate"""

    key: str
    pattern: SearchPattern
    without: set[str]
    """The ids of the entities its own document names (rule 2)"""
    among: set[str] | None = None
    """The ids to evaluate it among (seeded). None: in full"""


@dataclasses.dataclass
class Counts:
    """How the jobs of a call were evaluated"""

    seeded: int = 0
    anchored: int = 0
    """Evaluations in full from an anchor (a group of identical criteria is one)"""
    root_first: int = 0
    """Evaluations in full, every entity of the class tested (a group of identical criteria is one)"""
    shared: int = 0
    """Jobs that took the result of a group: criteria identical to those of other jobs of the call, evaluated once
    for all of them, each less what its own document names"""


def database() -> Any:
    return backend.current().database()


# What a head names: everything its own node refers to, and the nodes below it do (two queries: each finds its
# nodes by an index). Entities, and the nodes of its own tree that a relation is to: a document that stands in for
# an entity is one, and criteria may name it. Not what is computed (`asserted`): a candidate is not "named"
def _named_queries(label: str) -> tuple[str, ...]:
    return tuple(
        f"""
    UNWIND $heads AS head_id
    MATCH (node:PGIndexableNode {{{key}: head_id}})-[edge]->(named:{label})
    WHERE {fragments.forward("edge")} AND {fragments.asserted("edge")}
    RETURN head_id AS head, collect(DISTINCT named.id) AS named
    """
        for key in ("id", "head_node_id")
    )


NAMED_QUERIES = _named_queries("PGIndexableNode")
# (what a match can be: the walk from an anchor goes from entity to entity)
NAMED_ENTITIES_QUERIES = _named_queries("Entity")

# The heads that refer to an entity (or to a head document): of each node with an edge to it (a part of a
# document, a wrapper, a head)
REFERRING_HEADS_QUERY = f"""
    UNWIND $ids AS id
    MATCH (entity:PGIndexableNode {{id: id}})<-[edge]-(node:PGIndexableNode)
    WHERE {fragments.forward("edge")} AND {fragments.asserted("edge")}
    RETURN id, collect(DISTINCT coalesce(node.head_node_id, node.id)) AS heads
"""


async def named_by(
    tx: Transaction, heads: Iterable[str], entities_only: bool = False
) -> dict[str, set[str]]:
    """The ids of what each head's tree refers to (`entities_only`: of the entities among them)"""
    ids = list(dict.fromkeys(heads))
    found: dict[str, set[str]] = {id: set() for id in ids}
    if ids:
        for query in NAMED_ENTITIES_QUERIES if entities_only else NAMED_QUERIES:
            async for row in await tx.run(cast(LiteralString, query), heads=ids):
                found[row["head"]].update(row["named"])
    return found


async def referring_heads(tx: Transaction, ids: Iterable[str]) -> dict[str, list[str]]:
    asked = list(dict.fromkeys(ids))
    found: dict[str, list[str]] = {id: [] for id in asked}
    if asked:
        async for row in await tx.run(REFERRING_HEADS_QUERY, ids=asked):
            found[row["id"]] = list(row["heads"])
    return found


async def around(tx: Transaction, ids: Iterable[str]) -> set[str] | None:
    """What is one head away from the entities: the heads that refer to them, and everything those heads name.
    None if that is too much to be worth it"""
    referring = await referring_heads(tx, ids)
    heads = {head for found in referring.values() for head in found}
    if len(heads) > MAX_HEADS:
        return None
    near = set(heads)
    for named in (await named_by(tx, heads, entities_only=True)).values():
        near |= named
    return near if len(near) <= MAX_AMONG else None


async def from_anchors(
    tx: Transaction, wanted: dict[str, Analysis]
) -> dict[str, set[str]]:
    """For each key, the ids a full evaluation can be made among, from the best of its anchors: the one with the
    fewest hops, and of those the one fewest heads refer to. No entry where there is no anchor, or too much
    around it"""
    first = {
        id
        for analysis in wanted.values()
        for anchor in analysis.anchors
        for id in anchor.ids
    }
    referring = await referring_heads(tx, first)

    def cost(anchor: Anchor) -> tuple[int, int]:
        return anchor.hops, sum(len(referring[id]) for id in anchor.ids)

    chosen = {
        key: min(analysis.anchors, key=cost)
        for key, analysis in wanted.items()
        if analysis.anchors
    }
    # (what is around each anchor is read once, however many descriptions name it; and the first hop of all of
    # them together: what refers to them is read already, and what those heads name is two queries)
    heads_of: dict[tuple[str, ...], set[str] | None] = {}
    for anchor in set(chosen.values()):
        heads = {head for id in anchor.ids for head in referring[id]}
        heads_of[anchor.ids] = heads if len(heads) <= MAX_HEADS else None
    named = await named_by(
        tx,
        {head for heads in heads_of.values() if heads for head in heads},
        entities_only=True,
    )
    near: dict[tuple[tuple[str, ...], int], set[str] | None] = {}
    found: dict[str, set[str]] = {}
    for key, anchor in chosen.items():
        place = (anchor.ids, anchor.hops)
        if place not in near:
            heads = heads_of[anchor.ids]
            reached: set[str] | None = None
            if heads is not None:
                reached = heads.union(*(named[head] for head in heads))
                if len(reached) > MAX_AMONG:
                    reached = None
            for _ in range(anchor.hops - 1):
                reached = await around(tx, reached) if reached else reached
            near[place] = reached
        among = near[place]
        if among is not None:
            found[key] = among
    return found


def _evaluation(logged_in: Any, everyone: Any) -> Evaluation:
    # (what everyone sees is among what a logged-in reader sees, and both are in the order of their labels: one of
    # the first of the larger result that everyone sees is among the first of the smaller)
    seen_by_everyone = set(everyone.ids)
    return Evaluation(
        candidates=[
            {
                **item,
                "seen_by": EVERYONE if item["id"] in seen_by_everyone else LOGGED_IN,
            }
            for item in logged_in.items
        ],
        count=logged_in.count,
        count_everyone=everyone.count,
    )


def _less(found: Any, without: set[str], count: int, limit: int | None) -> Any:
    """A result of a group as one member's: its items less `without` (the first `limit`), with its own count"""
    items = [item for item in found.items if item["id"] not in without]
    return dataclasses.replace(
        found, count=count, items=items if limit is None else items[:limit]
    )


def _complete(found: Any) -> bool:
    """Whether a result has every match among its items (not cut at the limit)"""
    return found.count <= len(found.items)


async def evaluate_many(
    jobs: list[Job], limit: int | None = None, counts: Counts | None = None
) -> dict[str, Evaluation | Exception]:
    """Evaluate several descriptions. What each finds, by its key; or the error, for criteria that no longer fit
    the models (`PanglossSearchError`, `ValueError`).

    **Identical criteria are evaluated once.** Jobs in full whose criteria are the same (the same text, once merged
    ids are resolved) are a group, evaluated once without rule 2 and with as many more candidates as the most any
    member's document names (`MAX_WITHOUT` at most: a member past it is evaluated alone). Each member's result is
    the group's less what its own document names; its counts are exact: worked out from the group's candidates
    where those are all of them, and otherwise with one search of the ids the members' documents name, among
    them"""
    limit = max_candidates() if limit is None else limit
    counts = counts if counts is not None else Counts()
    operations = storage_of().operations
    results: dict[str, Evaluation | Exception] = {}

    # rule 5: the ids of merged entities, resolved for all of them at once
    named = list(dict.fromkeys(id for job in jobs for id in ids_named(job.pattern)))
    survivors = await operations.survivors_of(named) if named else {}

    ready: dict[str, tuple[Job, Any, Any, Analysis, str]] = {}
    for job in jobs:
        try:
            resolved = with_ids(job.pattern, survivors)
            items = check_stored(resolved, None, EXCLUDED)
            model = resolve_search_type(resolved.type)
            ready[job.key] = (
                job,
                model,
                resolved.match(EXCLUDED),
                analyse(model, items),
                resolved.text(),
            )
        except (PanglossSearchError, ValueError) as error:
            results[job.key] = error

    # identical criteria, in full: a group, evaluated once (keys of their own, which no job's can be)
    by_text: dict[str, list[str]] = {}
    for key, (job, _, _, _, text) in ready.items():
        if job.among is None and len(job.without) <= MAX_WITHOUT:
            by_text.setdefault(text, []).append(key)
    groups: dict[Any, list[str]] = {
        ("group", index): members
        for index, members in enumerate(m for m in by_text.values() if len(m) > 1)
    }
    more = {
        group: max(len(ready[member][0].without) for member in members)
        for group, members in groups.items()
    }
    grouped = {member for members in groups.values() for member in members}

    # what is evaluated: each job not in a group, and each group (among what, less what, the class, the pattern)
    units: dict[Any, tuple[set[str] | None, set[str], Any, Any, Analysis]] = {
        key: (job.among, job.without, model, match, analysis)
        for key, (job, model, match, analysis, _) in ready.items()
        if key not in grouped
    }
    for group, members in groups.items():
        _, model, match, analysis, _ = ready[members[0]]
        units[group] = (None, set(), model, match, analysis)
        counts.shared += len(members)

    in_full = {
        key: analysis
        for key, (among, _, _, _, analysis) in units.items()
        if among is None and analysis.anchors
    }
    anchored: dict[Any, set[str]] = {}
    if in_full:

        @database().read_transaction
        async def walk(tx: Transaction) -> dict[Any, set[str]]:
            return await from_anchors(tx, in_full)

        anchored = await walk()

    among: list[tuple[Any, Any, Any, list[str], list[str]]] = []
    root_first: list[Any] = []
    for key, (ids, without, model, match, _) in units.items():
        if ids is not None:
            counts.seeded += 1
        elif key in anchored:
            counts.anchored += 1
            ids = anchored[key]
        else:
            counts.root_first += 1
            root_first.append(key)
            continue
        among.append((key, model, match, sorted(ids), sorted(without)))
    found: dict[Any, tuple[Any, Any]] = {}
    if among:
        # (one call for all: of a group, as many more as its members leave out; the others are cut to the limit)
        fetched = limit + max(
            (more[key] for key, *_ in among if key in more), default=0
        )
        logged_in = await operations.search_ids_among(
            among, limit=fetched, see_unpublished=True
        )
        everyone = await operations.search_ids_among(
            among, limit=fetched, see_unpublished=False
        )
        for key in logged_in:
            found[key] = (logged_in[key], everyone[key])
    for key in root_first:
        _, without, model, match, _ = units[key]
        left_out = sorted(without)
        fetched = limit + more.get(key, 0)
        found[key] = (
            await operations.search_ids(
                model, match, limit=fetched, see_unpublished=True, without=left_out
            ),
            await operations.search_ids(
                model, match, limit=fetched, see_unpublished=False, without=left_out
            ),
        )
    for key, (logged, seen) in found.items():
        if key not in groups:
            results[key] = _evaluation(_less(logged, set(), logged.count, limit), seen)
    if groups:
        results.update(await _shared(groups, found, ready, limit))
    return results


async def _shared(
    groups: dict[Any, list[str]],
    found: dict[Any, tuple[Any, Any]],
    ready: dict[str, tuple[Job, Any, Any, Analysis, str]],
    limit: int,
) -> dict[str, Evaluation]:
    """What each member of a group finds: the group's result less what its own document names. Where the group's
    result is not all of its matches (as a reader), how many of what a member's document names match is asked of
    the database: one search for each, among those ids, in one call"""
    operations = storage_of().operations
    asked: dict[bool, list[tuple[Any, Any, Any, list[str], list[str]]]] = {
        True: [],
        False: [],
    }
    for group, members in groups.items():
        for seeing, result in zip((True, False), found[group], strict=True):
            if _complete(result):
                continue
            for member in members:
                job, model, match, _, _ = ready[member]
                if job.without:
                    asked[seeing].append(
                        (member, model, match, sorted(job.without), [])
                    )
    matching: dict[bool, dict[Any, Any]] = {True: {}, False: {}}
    for seeing, searches in asked.items():
        if searches:
            matching[seeing] = await operations.search_ids_among(
                searches, limit=1, see_unpublished=seeing
            )

    made: dict[str, Evaluation] = {}
    for group, members in groups.items():
        logged, seen = found[group]
        for member in members:
            without = ready[member][0].without
            counted = [
                result.count - _removed(result, without, matching[seeing].get(member))
                for seeing, result in ((True, logged), (False, seen))
            ]
            made[member] = _evaluation(
                _less(logged, without, counted[0], limit),
                _less(seen, without, counted[1], None),
            )
    return made


def _removed(result: Any, without: set[str], matched: Any) -> int:
    """How many of the matches of a group's result a member leaves out: counted among the result's items where they
    are all of them, and otherwise what the search among the member's ids found (`matched`)"""
    if _complete(result):
        return sum(1 for item in result.items if item["id"] in without)
    return matched.count if matched is not None else 0
