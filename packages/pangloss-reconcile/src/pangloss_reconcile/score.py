"""How a candidate is scored against an unknown, part by part, with no database in it (step 10.2c of
implementation_docs/similarity-build-plan.md, row e; 10.3 changes it).

For each part the unknown has a vector of and that has a weight above 0, the cosine of the candidate's vector of that
part with the unknown's (0 where the candidate has none, or either is of length 0); the score is the weighted mean of
those cosines, `Σ w·cos / Σ w`, over the parts the unknown has: a part the candidate lacks counts 0, and still
counts in the sum below the line (unlike the search's combined vectors, which leave it out of that one's sum, and so
lift an item that lacks a part)."""

import math
from collections.abc import Mapping, Sequence

type Vector = Sequence[float]


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
    """The cosine of each part the unknown has a vector of and that weighs above 0, by part (0 where the candidate
    has none of it)"""
    return {
        name: cosine(vector, candidate[name]) if name in candidate else 0.0
        for name, vector in sorted(unknown.items())
        if weights.get(name, 0) > 0
    }


def score(scores: Mapping[str, float], weights: Mapping[str, float]) -> float:
    """The weighted mean of the cosines of the parts, `Σ w·cos / Σ w`; 0 for no part"""
    total = math.fsum(weights[name] for name in scores)
    if not total:
        return 0.0
    return math.fsum(weights[name] * value for name, value in scores.items()) / total


def ranked(scored: Mapping[str, float], limit: int) -> list[str]:
    """The ids by score, highest first, then by id; the first `limit`"""
    return sorted(scored, key=lambda key: (-scored[key], key))[:limit]
