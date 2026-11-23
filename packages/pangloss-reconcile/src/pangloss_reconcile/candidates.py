"""The candidates of the unknowns of a write plan (implementation_docs/reconcile.md; step 10.2c of
implementation_docs/similarity-build-plan.md, rows d and e).

For each unknown (`pangloss_vectors.unknowns_of`), with what every part says it would be
(`pangloss_vectors.unknown_vectors`):

1. **found**: for each part that gave it a vector and that the profile weighs, the nearest `RECONCILE_FETCH` items
   by that part alone (`nearest(vector={part: vector}, exact=True)`, narrowed to the classes the unknown stands for,
   as the reader may see them), and the union of their ids. A hit's score from these searches is not used: with one
   part in the query it lifts hits that lack the other parts;
2. **counted**: what each item found shares with the document (`reasons.shared`, step 11.2): one query for every
   item found of every unknown asked about, before any cut, unless neither the score nor the answer wants it (the
   weight of `shared` 0 and `RECONCILE_REASONS` 0);
3. **scored**: the vectors in use of those items, part by part (`store.read_part`), each scored against the
   unknown's with what it shares (`score.py`), by score and then id; those under `RECONCILE_LEAST_SCORE` left out,
   then the first `limit` (`Found.candidates`). Of the same ranking, before either cut, the first `KEPT` are
   `Found.best`: what the stored route keeps of what it offered (`decisions.py`, step 11.4).

An unknown no part says anything of has no candidates. Nothing is written."""

import dataclasses
from collections.abc import Collection, Mapping
from typing import Any, Literal

from pangloss_vectors.parts import Unknown, Vector

from pangloss_reconcile import score as scoring
from pangloss_reconcile.settings import (
    fetch,
    least_score,
    most_unknowns,
    profile,
    reasons,
    weights,
)

type Status = Literal["ok", "pending", "rebuild_due"]

# How many of the items found for an unknown are kept in `Found.best`, by the hand-set score, whatever the least score
# and `limit` (what a decision is learnt from: `decisions.py`)
KEPT = 10


class TooManyUnknowns(ValueError):
    """A plan with more unknowns than `RECONCILE_MOST_UNKNOWNS` (or more asked for by `only`): refused before any
    part is asked"""

    def __init__(self, count: int, most: int) -> None:
        super().__init__(
            f"The document has {count} unknowns, and at most {most} are asked about at once (RECONCILE_MOST_UNKNOWNS)"
        )
        self.count = count
        self.most = most


@dataclasses.dataclass(frozen=True)
class Candidate:
    """An item an unknown may be: its id and class, its score (the weighted mean of `scores`), the cosine of each
    part the unknown has a vector of (0 where the item has none) and `shared` while its weight is above 0
    (`score.py`); and `shared`, every entity of the document it is named with in other stored documents, with in how
    many, most documents first and then by id (whatever the weight, when it was asked: `candidates_of`)"""

    id: str
    type: str
    score: float
    scores: dict[str, float]
    shared: tuple[tuple[str, int], ...] = ()


@dataclasses.dataclass(frozen=True)
class Found:
    """An unknown and its candidates, best first. `status`: `"ok"`, or what a search of the profile said instead
    (`"pending"`: it has not been built; `"rebuild_due"`: its vectors in use are of another dimension than its parts
    make today), and then no candidates.

    `best`: the first `KEPT` of every item found, by the same score and order, before the cut by
    `RECONCILE_LEAST_SCORE` and `limit` (of the one ranking: `candidates` is its first `limit` above the least
    score, so the two cannot differ where they meet)"""

    unknown: Unknown
    candidates: list[Candidate]
    status: Status = "ok"
    best: tuple[Candidate, ...] = ()


async def candidates_of(
    plan: Any,
    *,
    see_unpublished: bool,
    limit: int = 10,
    only: Collection[str] | None = None,
) -> list[Found]:
    """The candidates of each unknown of a write plan (`pangloss_cypher.write_plan.WritePlan`), in the order of the
    plan, by the profile `RECONCILE_PROFILE` (`settings.py`), as the reader may see them. Nothing is written.

    `only`: of the unknowns of these ids. Every part is still asked of all the plan's unknowns, so that each is laid
    out as the others are, as in the whole document; but a plan with more unknowns than `RECONCILE_MOST_UNKNOWNS` has
    the parts asked of those of `only` alone (the stored route: a document with many stand-ins costs no more than
    the cap). `TooManyUnknowns` if more are asked about than the cap (all of the plan's, or those of `only`), before
    any part is asked. What the items found share with the document is asked once, of them all (`reasons.shared`)"""
    from pangloss_vectors import store
    from pangloss_vectors.fields import classes_of
    from pangloss_vectors.parts import profile as weights_of
    from pangloss_vectors.parts import unknown_vectors
    from pangloss_vectors.search import nearest
    from pangloss_vectors.unknowns import unknowns_of

    from pangloss_reconcile.reasons import shared

    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError(f"Candidates are asked 1 or more at a time, not {limit!r}")
    unknowns = unknowns_of(plan)
    chosen = None if only is None else set(only)
    wanted = [u for u in unknowns if chosen is None or u.id in chosen]
    most = most_unknowns()
    if len(wanted) > most:
        raise TooManyUnknowns(len(wanted), most)
    if not wanted:
        return []
    # (each laid out among the others, unless there are more of them than the cap)
    asked = unknowns if len(unknowns) <= most else wanted
    name = profile()
    searched = weights_of(name)
    weighed = weights()
    least = least_score()
    k = fetch()
    said = await unknown_vectors(plan, asked)

    # (1. found: the union of what each part finds alone)
    found_ids: dict[str, dict[str, str]] = {}
    statuses: dict[str, Status] = {}
    for unknown in wanted:
        vectors = said.get(unknown.id, {})
        types = classes_of(unknown.type)
        hits: dict[str, str] = {}
        for part_name, vector in sorted(vectors.items()):
            if searched.get(part_name, 0) <= 0 or not types or not any(vector):
                continue
            near = await nearest(
                vector={part_name: vector},
                profile=name,
                types=types,
                asked=[unknown.type],
                k=k,
                exact=True,
                see_unpublished=see_unpublished,
            )
            if near.status != "ok":
                statuses[unknown.id] = near.status
                break
            for hit in near.hits:
                hits.setdefault(hit.id, hit.type)
        found_ids[unknown.id] = {} if unknown.id in statuses else hits

    # (2. scored: the vectors of what was found, read once for each part)
    of_part: dict[str, dict[str, list[float]]] = {}
    everyone = sorted({id for hits in found_ids.values() for id in hits})
    for part_name in sorted(
        {
            part_name
            for unknown in wanted
            for part_name in said.get(unknown.id, {})
            if weighed.get(part_name, 0) > 0
        }
    ):
        of_part[part_name] = (
            await store.read_part(part_name, everyone) if everyone else {}
        )

    # (2. counted: what every item found shares with the document, in one query, before any cut; not asked only
    # when neither the score nor the answer would use it)
    wanted_shared = weighed.get(scoring.SHARED, 0) > 0 or reasons() > 0
    sharing = (
        await shared(plan, everyone, see_unpublished)
        if everyone and wanted_shared
        else {}
    )

    found: list[Found] = []
    for unknown in wanted:
        best, candidates = ranked(
            said.get(unknown.id, {}),
            found_ids[unknown.id],
            of_part,
            sharing,
            weighed,
            least,
            limit,
        )
        found.append(
            Found(unknown, candidates, statuses.get(unknown.id, "ok"), tuple(best))
        )
    return found


def ranked(
    vectors: Mapping[str, Vector],
    hits: Mapping[str, str],
    of_part: Mapping[str, Mapping[str, list[float]]],
    sharing: Mapping[str, list[tuple[str, int]]],
    weighed: Mapping[str, float],
    least: float,
    limit: int,
) -> tuple[list[Candidate], list[Candidate]]:
    """The items found for one unknown, each scored against its vectors and by what it shares, best first (by score,
    then id): the first `KEPT` of them all (`Found.best`), and the first `limit` of those not under `least`
    (`Found.candidates`). No database in it"""
    every: list[Candidate] = []
    for id in hits:
        candidate = {
            part_name: found[id] for part_name, found in of_part.items() if id in found
        }
        scores = scoring.with_shared(
            scoring.part_scores(vectors, candidate, weighed),
            len(sharing.get(id, [])),
            weighed,
        )
        every.append(
            Candidate(
                id,
                hits[id],
                scoring.score(scores, weighed),
                scores,
                tuple(sharing.get(id, [])),
            )
        )
    by_id = {c.id: c for c in every}
    order = [
        by_id[id] for id in scoring.ranked({c.id: c.score for c in every}, len(every))
    ]
    # (those not under the least score are a head of the one order: the candidates are its first `limit` of them)
    kept = [c for c in order if c.score >= least]
    return order[:KEPT], kept[:limit]
