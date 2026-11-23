"""How a candidate is scored against an unknown, part by part, with no database in it (step 10.2c of
implementation_docs/similarity-build-plan.md, row e; 10.3 and 11.2 change it).

For each part the unknown has a vector of and that has a weight above 0, the cosine of the candidate's vector of that
part with the unknown's (0 where the candidate has none, or either is of length 0); the score is the weighted mean of
those cosines, `Σ w·cos / Σ w`, over the parts the unknown has: a part the candidate lacks counts 0, and still
counts in the sum below the line (unlike the search's combined vectors, which leave it out of that one's sum, and so
lift an item that lacks a part).

A part whose vector of the unknown is all zeros has said nothing: it is not scored, and is not in the sum below the
line. A candidate's vector of another length than the unknown's (stored by a generation of another dimension, one the
profile's `rebuild_due` does not cover) is as if the candidate had none: 0, never an error.

Beside the parts, `shared` (step 11.2): of n entities of the document the candidate is named with in other stored
documents (`reasons.py`), `lead × n / (n + 2)`, one more term of the mean at its own weight
(`RECONCILE_WEIGHTS["shared"]`, 1.5 unless given). `lead` is the candidate's cosine of the part the weights weigh most
among the parts scored for the unknown (of several weighed alike, the first by name; with the profile `who`, the
name); no part scored, 0. Why the product: what is shared tells namesakes apart, and must not make someone of another
name a candidate. Counted alike for everyone (the first form, `n / (n + 2)` alone at 0.75), the people the document
itself names, of no name like the unknown's, came up at about 0.26 by what they share with each other. Measured
through the service on the planted world at size (32,137 people, Memgraph, 200 mentions; 2026-11-23): name 1 and
graph 0.25 alone, 66.5% right first; with the first form at 0.75, 82.0%; with the product at 1, 85.5%; at 1.5, 86.5%
(among five 99.5%; of names several people have, first 53.9%, 76.5%, 79.1%, 82.6%).

It is not a part: it has no vector, and is a count asked of the database for the candidates found, not something an
item has by itself. While its weight is above 0 every candidate has it, 0 for one that shares nothing and for every
candidate of a document that names no entity, so that it is always in the sum below the line and a score means the
same from one document to the next. At weight 0 it is not there at all, and the score is phase 10's."""

import math
from collections.abc import Mapping, Sequence

type Vector = Sequence[float]

# (the name of the term of the entities shared, beside the parts' names in `scores` and `RECONCILE_WEIGHTS`)
SHARED = "shared"


def shared_score(n: int) -> float:
    """What sharing `n` of the document's entities is worth, from 0 (none) towards 1: `n / (n + 2)`"""
    if n < 0:
        raise ValueError(f"A count of entities shared is 0 or more, not {n}")
    return n / (n + 2)


def lead(scores: Mapping[str, float], weights: Mapping[str, float]) -> str | None:
    """The part of `scores` the weights weigh most (of several alike, the first by name; `shared` never), or None if
    no part is scored"""
    parts = sorted(name for name in scores if name != SHARED)
    if not parts:
        return None
    return min(parts, key=lambda name: (-weights.get(name, 0), name))


def with_shared(
    scores: Mapping[str, float], n: int, weights: Mapping[str, float]
) -> dict[str, float]:
    """The scores of the parts with `shared` beside them when its weight is above 0: the lead part's cosine
    (`lead`) × `shared_score(n)`, 0 with no part scored or a lead's cosine under 0 (what is shared never counts
    against a candidate); by name"""
    found = dict(scores)
    if weights.get(SHARED, 0) > 0:
        first = lead(scores, weights)
        found[SHARED] = (
            0.0 if first is None else max(0.0, scores[first]) * shared_score(n)
        )
    return dict(sorted(found.items()))


def cosine(a: Vector, b: Vector) -> float:
    """The cosine of two vectors of one length; 0 if either is of length 0"""
    if len(a) != len(b):
        raise ValueError(
            f"A cosine is of two vectors of one length, not {len(a)} and {len(b)}"
        )
    dot = math.fsum(x * y for x, y in zip(a, b, strict=True))
    length = math.sqrt(math.fsum(x * x for x in a)) * math.sqrt(
        math.fsum(y * y for y in b)
    )
    return dot / length if length else 0.0


def part_scores(
    unknown: Mapping[str, Vector],
    candidate: Mapping[str, Vector],
    weights: Mapping[str, float],
) -> dict[str, float]:
    """The cosine of each part the unknown has a vector of (not all zeros) and that weighs above 0, by part (0 where
    the candidate has none of it, or one of another length)"""

    def of(name: str, vector: Vector) -> float:
        found = candidate.get(name)
        if found is None or len(found) != len(vector):
            return 0.0
        return cosine(vector, found)

    return {
        name: of(name, vector)
        for name, vector in sorted(unknown.items())
        if weights.get(name, 0) > 0 and any(vector)
    }


def score(scores: Mapping[str, float], weights: Mapping[str, float]) -> float:
    """The weighted mean of the cosines of the parts (and of `shared`, when it is there), `Σ w·cos / Σ w`; 0 for no
    part"""
    total = math.fsum(weights[name] for name in scores)
    if not total:
        return 0.0
    return math.fsum(weights[name] * value for name, value in scores.items()) / total


def ranked(scored: Mapping[str, float], limit: int) -> list[str]:
    """The ids by score, highest first, then by id; the first `limit`"""
    return sorted(scored, key=lambda key: (-scored[key], key))[:limit]
