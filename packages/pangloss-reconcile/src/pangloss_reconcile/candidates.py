"""The candidates of the unknowns of a write plan (implementation_docs/reconcile.md; step 10.2c of
implementation_docs/similarity-build-plan.md, rows d and e).

For each unknown (`pangloss_vectors.unknowns_of`), with what every part says it would be
(`pangloss_vectors.unknown_vectors`):

1. **found**: for each part that gave it a vector and that the profile weighs, the nearest `RECONCILE_FETCH` items
   by that part alone (`nearest(vector={part: vector}, exact=True)`, narrowed to the classes the unknown stands for,
   as the reader may see them), and the union of their ids. A hit's score from these searches is not used: with one
   part in the query it lifts hits that lack the other parts;
2. **scored**: the vectors in use of those items, part by part (`store.read_part`), each scored against the
   unknown's (`score.py`), by score and then id, the first `limit`.

An unknown no part says anything of has no candidates. Nothing is written."""

import dataclasses
from collections.abc import Collection, Mapping
from typing import Any, Literal

from pangloss_vectors.parts import Unknown, Vector

from pangloss_reconcile import score as scoring
from pangloss_reconcile.settings import fetch, profile, weights

type Status = Literal["ok", "pending", "rebuild_due"]


@dataclasses.dataclass(frozen=True)
class Candidate:
    """An item an unknown may be: its id and class, its score (the weighted mean of `scores`) and the cosine of each
    part the unknown has a vector of (0 where the item has none)"""

    id: str
    type: str
    score: float
    scores: dict[str, float]


@dataclasses.dataclass(frozen=True)
class Found:
    """An unknown and its candidates, best first. `status`: `"ok"`, or what a search of the profile said instead
    (`"pending"`: it has not been built; `"rebuild_due"`: its vectors in use are of another dimension than its parts
    make today), and then no candidates"""

    unknown: Unknown
    candidates: list[Candidate]
    status: Status = "ok"


async def candidates_of(
    plan: Any,
    *,
    see_unpublished: bool,
    limit: int = 10,
    only: Collection[str] | None = None,
) -> list[Found]:
    """The candidates of each unknown of a write plan (`pangloss_cypher.write_plan.WritePlan`), in the order of the
    plan; `only`: of the unknowns of these ids (every part is still asked of them all, so that each is laid out as
    the others are, as the plan of the whole document has them). By the profile `RECONCILE_PROFILE` (`settings.py`),
    as the reader may see them. Nothing is written"""
    from pangloss_vectors import store
    from pangloss_vectors.fields import classes_of
    from pangloss_vectors.parts import profile as weights_of
    from pangloss_vectors.parts import unknown_vectors
    from pangloss_vectors.search import nearest
    from pangloss_vectors.unknowns import unknowns_of

    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError(f"Candidates are asked 1 or more at a time, not {limit!r}")
    unknowns = unknowns_of(plan)
    wanted = [u for u in unknowns if only is None or u.id in set(only)]
    if not wanted:
        return []
    name = profile()
    searched = weights_of(name)
    weighed = weights()
    k = fetch()
    said = await unknown_vectors(plan, unknowns)

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

    return [
        Found(
            unknown,
            _scored(
                said.get(unknown.id, {}), found_ids[unknown.id], of_part, weighed, limit
            ),
            statuses.get(unknown.id, "ok"),
        )
        for unknown in wanted
    ]


def _scored(
    vectors: Mapping[str, Vector],
    hits: Mapping[str, str],
    of_part: Mapping[str, Mapping[str, list[float]]],
    weighed: Mapping[str, float],
    limit: int,
) -> list[Candidate]:
    """The items found for one unknown, each scored against its vectors, best first, the first `limit`"""
    scored: dict[str, tuple[float, dict[str, float]]] = {}
    for id in hits:
        candidate = {
            part_name: found[id] for part_name, found in of_part.items() if id in found
        }
        scores = scoring.part_scores(vectors, candidate, weighed)
        scored[id] = (scoring.score(scores, weighed), scores)
    best = scoring.ranked({id: value for id, (value, _) in scored.items()}, limit)
    return [Candidate(id, hits[id], scored[id][0], scored[id][1]) for id in best]
