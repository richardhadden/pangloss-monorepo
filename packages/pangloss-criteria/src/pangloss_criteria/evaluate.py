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
from typing import Any

from pangloss_core import settings as core_settings
from pangloss_core import storage_of
from pangloss_models import ComputedTarget, PanglossSearchError
from pangloss_models.computed import EVERYONE, LOGGED_IN
from pangloss_models.search import resolve_search_type

from pangloss_criteria.models import EXCLUDED
from pangloss_criteria.pattern import SearchPattern, check_stored, resolve_merged

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
