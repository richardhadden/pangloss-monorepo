"""What reconciliation learns from the decisions kept (`decisions.py`), with no database in it (step 11.5 of
implementation_docs/similarity-build-plan.md; implementation_docs/reconcile.md, "Learning from decisions"). The fit
and the comparisons are `pangloss_learn`'s; this says what the examples are.

Two models are fitted from the same decisions:

- the **ranking** model: one `pangloss_learn.Example` for each row kept in a decision (the ten best by the hand-set
  score, displayed or not; `group` the stand-in), `yes` for the row taken. Its features (`ranking_features`): each
  scored part's cosine, by the part's name, and `shared` (its score as kept) while its weight is above 0, in the
  order `sorted(parts) + ["shared"]`. Compared with the hand-set score (`score.score`);
- the **"none of these"** model: one example for each decision, over the head of the **displayed** rows as the
  hand-set score ranks them (`head_features`): `best` (the best one's score), `gap` (to the next one's; with one
  row, `best` itself), the best one's own features as `best_PART` and `best_shared`, and `rows` (how many were
  displayed, as `log(1 + n)`). `yes` when none of those displayed was taken (`taken` null, or a row not displayed).
  A decision with no row displayed has no such example (there is no figure of an empty list). Compared with always
  answering the commoner of the two (`pangloss_learn.compare_calls`).

A decision is made in one of two ways (`decisions.py`): of a person's choice in the dialog (`via` None), or of a
person's confirmation of one of the worker's suggestions (`via` `"suggestion"`, `VIA_SUGGESTION`: the rows the worker
saw, the person shown its choice and not the dialog's list). `decision_of` reads either from an example as kept;
`fits.learn` counts the second apart and may leave it out (`RECONCILE_LEARN_FROM_SUGGESTIONS`). Of those, the
confirmations of suggestions a project's judge changed (`judged`, step 10.5c': the rows are still the worker's own,
`displayed` as the worker decided, so a judge's entity that is none of them is "none of those offered") are counted
apart again, and taken in like the others.

A decision is plain data (`Decision`), and so is a row: a mapping with `score`, `scores` (each part's cosine and
`shared`, by name), `displayed` and, in a decision, `id`. `head_features` is what step 11.6 asks of a live answer too:
`none_likelihood`, the figure of "none of these" the stored route gives from the fit in use.
"""

import dataclasses
import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pangloss_learn import Example, Model

from pangloss_reconcile.score import SHARED

type Row = Mapping[str, Any]

# (the prefix of the best row's own features among the "none of these" model's)
BEST = "best_"


# (what an example made of a confirmed suggestion says it came by)
VIA_SUGGESTION = "suggestion"


@dataclasses.dataclass(frozen=True)
class Decision:
    """A decision kept (`PGReconcileExample`): what it is kept by (the stand-in; for one made of a confirmed
    suggestion, the suggestion's id), the rows as they were kept (by the hand-set score), the id of the row taken, or
    None when none of them was, and how it was made (`via`: None, a choice in the dialog; `VIA_SUGGESTION`), and
    whether a project's judge changed what was suggested (`judged`)"""

    stand_in: str
    rows: tuple[Row, ...]
    taken: str | None
    via: str | None = None
    judged: bool = False


def decision_of(example: Mapping[str, Any]) -> Decision:
    """A decision of an example as `decisions.examples()` gives it (`rows` read from JSON already; `via` absent or
    None for one of the dialog; `judged` absent or None for one no judge changed)"""
    return Decision(
        str(example["stand_in"]),
        tuple(example["rows"]),
        example.get("taken"),
        example.get("via"),
        bool(example.get("judged")),
    )


def from_suggestion(decision: Decision) -> bool:
    """Whether a decision was made of a person's confirmation of one of the worker's suggestions"""
    return decision.via == VIA_SUGGESTION


def ranking_features(weights: Mapping[str, float]) -> list[str]:
    """The ranking model's features for these weights (`settings.weights()`): each part weighed above 0, by name, then
    `shared` if its weight is above 0"""
    parts = sorted(
        name for name, weight in weights.items() if name != SHARED and weight > 0
    )
    return parts + ([SHARED] if weights.get(SHARED, 0) > 0 else [])


def none_features(ranking: Sequence[str]) -> list[str]:
    """The "none of these" model's features, of the ranking model's: `best`, `gap`, `best_` and each of them, `rows`"""
    return ["best", "gap", *(BEST + name for name in ranking), "rows"]


def lacking(rows: Iterable[Row], features: Sequence[str]) -> list[str]:
    """The features some row has no number of (a part the unknown had no vector of: fault 11), by name; none, []"""
    return sorted(
        {name for row in rows for name in features if name not in row["scores"]}
    )


def ranking_examples(
    decisions: Iterable[Decision], features: Sequence[str]
) -> list[Example]:
    """One example for each row of each decision: its features, `yes` for the row taken, the stand-in its group"""
    return [
        Example(
            {name: float(row["scores"][name]) for name in features},
            row["id"] == decision.taken,
            decision.stand_in,
        )
        for decision in decisions
        for row in decision.rows
    ]


def head(rows: Iterable[Row]) -> list[Row]:
    """The rows displayed, by the hand-set score, highest first (of several alike, as they were given)"""
    shown = [row for row in rows if row["displayed"]]
    return sorted(shown, key=lambda row: -float(row["score"]))


def head_features(rows: Iterable[Row]) -> dict[str, float] | None:
    """The "none of these" model's features of a list (`none_features`): of the rows displayed, by the hand-set score,
    the best one's score, its gap to the next one's (with one row, its score), its own features (`best_` and each
    name of its `scores`) and how many were displayed (`log(1 + n)`). None for a list with none displayed"""
    shown = head(rows)
    if not shown:
        return None
    best = float(shown[0]["score"])
    gap = best - float(shown[1]["score"]) if len(shown) > 1 else best
    return {
        "best": best,
        "gap": gap,
        **{
            BEST + name: float(value)
            for name, value in sorted(shown[0]["scores"].items())
        },
        "rows": math.log1p(len(shown)),
    }


def none_taken(decision: Decision) -> bool:
    """Whether none of the rows displayed was taken (`taken` null, or a row that was kept and not displayed)"""
    return not any(
        row["displayed"] and row["id"] == decision.taken for row in decision.rows
    )


def none_examples(
    decisions: Iterable[Decision], features: Sequence[str]
) -> list[Example]:
    """One example for each decision with a row displayed (`head_features`, of these `none_features`), `yes` when none
    displayed was taken (`none_taken`); a decision with none displayed has none"""
    found = []
    for decision in decisions:
        features_of = head_features(decision.rows)
        if features_of is None:
            continue
        found.append(
            Example(
                {name: features_of[name] for name in features if name in features_of},
                none_taken(decision),
                decision.stand_in,
            )
        )
    return found


def answered_rows(answered: Iterable[tuple[float, Mapping[str, float]]]) -> list[Row]:
    """The rows of candidates as an answer gives them (each `(score, scores)`, in the answer's order), each displayed:
    what `none_likelihood` is asked of"""
    return [
        {"score": score, "scores": scores, "displayed": True}
        for score, scores in answered
    ]


def probably_new(
    model: Model, answered: Iterable[tuple[float, Mapping[str, float]]], above: float
) -> tuple[float, bool] | None:
    """What the "none of these" model `model` says of candidates as an answer gives them (`answered_rows`): the
    likelihood that the one meant is none of them (`none_likelihood`), and whether it is above `above`
    (`RECONCILE_NEW_ABOVE`): the stored route's `new` and `probablyNew`, and what a suggestion is not made for
    (`suggest.decide_for`). None when there is no figure"""
    new = none_likelihood(model, answered_rows(answered))
    return None if new is None else (new, new > above)


def none_likelihood(model: Model, rows: Sequence[Row]) -> float | None:
    """The likelihood, from 0 to 1, that the one meant is none of `rows` (`Model.score` of their `head_features`), by
    the "none of these" model `model`: the rows as the answer gives them, each displayed. None (no figure) when there
    is no row, when a row lacks a part the model weighs (`best_PART`: the unknown had no vector of it; fault 11), or
    when the features made lack one the model weighs"""
    parts = [
        name.removeprefix(BEST) for name in model.features if name.startswith(BEST)
    ]
    if lacking(rows, parts):
        return None
    features = head_features(rows)
    if features is None or any(name not in features for name in model.features):
        return None
    return model.score(features)
