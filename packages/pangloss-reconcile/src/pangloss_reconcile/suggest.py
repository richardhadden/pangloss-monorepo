"""What to suggest for an unknown, from its candidates (step 10.5c; implementation_docs/reconcile.md). No database:
`percentages` and `decide` are pure, given every number; `decide_for` gives `decide` its arguments from the settings
(`RECONCILE_SUGGEST_ABOVE`, `RECONCILE_SUGGEST_MOST`, `RECONCILE_SUGGEST_WITHIN`, `RECONCILE_NEW_ABOVE`) and from the
"none of these" model of the fit in use, which its caller has read.

The candidates are those of one unknown **as the dialog would be answered**: in the order of their score, those
under the least score left out, cut to the dialog's limit (`candidates.DISPLAYED`). From them: nothing, or the best
few as alternatives, each with how likely it is the one meant, in whole per cent that sum to 100 (what a
`WeightedAlternative` holds).
"""

import dataclasses
from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pangloss_learn import Model

    from pangloss_reconcile.candidates import Found

__all__ = ["Alternative", "Decision", "decide", "decide_for", "percentages"]

# Why nothing is suggested, or that something is
Reason = Literal["suggested", "none", "low", "new"]


@dataclasses.dataclass(frozen=True)
class Alternative:
    """One of those suggested: the entity, and how likely it is the one meant, in per cent"""

    id: str
    type: str
    percent: int


@dataclasses.dataclass(frozen=True)
class Decision:
    """What was decided for one unknown: the alternatives, the likeliest first (none: the mention is left), and why:
    `suggested`; `none` (no candidate); `low` (the best scores under the threshold); `new` (a fit in use says the
    one meant is probably none of those offered)"""

    alternatives: tuple[Alternative, ...]
    reason: Reason

    @property
    def suggested(self) -> bool:
        return bool(self.alternatives)


def percentages(scores: Sequence[float]) -> list[int]:
    """The scores as whole per cent that sum to 100, each at least 1, in the same order: in proportion to the
    scores, the whole per cent that rounding down leaves going to the largest remainders (the earlier first, of
    equal ones). Scores of nothing (or less) share equally. At most 100 scores"""
    count = len(scores)
    if not count:
        return []
    if count > 100:
        raise ValueError("More than 100 alternatives cannot each have 1 per cent")
    held = [max(float(score), 0.0) for score in scores]
    total = sum(held)
    if total <= 0:
        held = [1.0] * count
        total = float(count)
    # (each has its 1 per cent first; the rest is shared in proportion)
    spare = 100 - count
    exact = [spare * score / total for score in held]
    whole = [int(share) for share in exact]
    left = spare - sum(whole)
    by_remainder = sorted(range(count), key=lambda n: (-(exact[n] - whole[n]), n))
    for n in by_remainder[:left]:
        whole[n] += 1
    return [1 + share for share in whole]


def decide(
    candidates: Sequence[tuple[str, str, float]],
    *,
    above: float,
    most: int,
    within: float,
    probably_new: bool = False,
) -> Decision:
    """What to suggest for an unknown whose candidates are these (`(id, type, score)`, the best first, as answered
    to the dialog). Nothing if there is none, if the best scores under `above`, or if `probably_new` (a fit in use
    says so). Otherwise the best `most` whose score is at least `within` of the best's (from 0 to 1: 0.8 keeps
    those that score four fifths of the best or more), with their `percentages`"""
    if not candidates:
        return Decision((), "none")
    best = candidates[0][2]
    if best < above:
        return Decision((), "low")
    if probably_new:
        return Decision((), "new")
    kept = [one for one in candidates[: max(most, 1)] if one[2] >= within * best]
    shares = percentages([score for _, _, score in kept])
    return Decision(
        tuple(
            Alternative(id, type, percent)
            for (id, type, _), percent in zip(kept, shares, strict=True)
        ),
        "suggested",
    )


def decide_for(found: Found, fit: Model | None) -> Decision:
    """What to suggest for an unknown whose candidates are `found` (`candidates_of`, as the dialog asks them: the
    first `candidates.DISPLAYED` of them are taken), by the settings (`RECONCILE_SUGGEST_ABOVE`,
    `RECONCILE_SUGGEST_MOST`, `RECONCILE_SUGGEST_WITHIN`). `fit`: the "none of these" model of the fit in use when it
    can be used (`fits.usable`), or None: then nothing is suggested when it says the one meant is probably none of
    them, as the stored route says `probablyNew` (`learning.probably_new`, above `RECONCILE_NEW_ABOVE`)"""
    from pangloss_reconcile import learning, settings
    from pangloss_reconcile.candidates import DISPLAYED

    answered = list(found.candidates[:DISPLAYED])
    said = (
        learning.probably_new(
            fit, [(c.score, c.scores) for c in answered], settings.new_above()
        )
        if fit is not None and answered
        else None
    )
    return decide(
        [(c.id, c.type, c.score) for c in answered],
        above=settings.suggest_above(),
        most=settings.suggest_most(),
        within=settings.suggest_within(),
        probably_new=said is not None and said[1],
    )
