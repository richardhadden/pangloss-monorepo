"""The whole of the learning, with no database in it (step 11.1 of implementation_docs/similarity-build-plan.md).

An **example** is one thing that was offered when a person decided: its features (numbers, by name), whether it was
the one taken (`yes`), and the decision it belongs to (`group`: the others offered with it are of the same group).

`fit` makes a **model**: a logistic regression, the likelihood of "yes" as `1 / (1 + exp(-(w·x + c)))`, fitted by
Newton's steps with a ridge (a pull of every weight but the constant towards 0, so that examples a feature divides
cleanly do not send its weight off without end). The examples are put in one order first, so the same examples,
given in any order, make the same model to the last bit.

`compare` says whether a model is worth using: the decisions are dealt into folds by a seed; for each fold a model
is fitted on the others, and in each decision of the fold the example it scores highest is looked at, and the one a
baseline (a score set by hand) scores highest. How often each was the one taken is the answer. A decision in which
nothing offered was taken can be right for neither, and is not counted.

`compare_calls` is the same question of a model that says yes or no of a whole decision ("none of those offered is
the one"): each example is a decision by itself, the model's call is "yes" at a likelihood of a half or more, and
what it is compared with is always answering whichever of the two was the commoner among the examples it was fitted
on, or, given a `baseline` (a likelihood set by hand, of an example's features), that likelihood's call at a half.
Two options, each off unless asked for: `stratified` deals the "yes" and the "no" into the folds apart, evenly, so that
every part a model is fitted on has both answers wherever there are two of each or more; `count_differences` also
counts the held-out examples the model and the baseline call differently (`CallsCompared.differ`), for a check that
allows for chance (`CallsCompared.within`).

Features are not rescaled: they are expected to be of the size of a cosine or a small count's logarithm."""

import dataclasses
import json
import math
import random
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

import numpy as np

STEPS = 100
"""The most of Newton's steps (a fit that has a ridge settles in under ten)"""


class Unfittable(ValueError):
    """The examples given cannot make a model: the message says why"""


@dataclasses.dataclass(frozen=True)
class Example:
    features: Mapping[str, float]
    yes: bool
    group: str = ""


@dataclasses.dataclass(frozen=True)
class Model:
    """What `fit` found: plain data. `examples` and `yes` are how many it was fitted on and how many of them were
    taken; `fitted_at` is what the caller said (the maths knows no clock)"""

    features: tuple[str, ...]
    weights: tuple[float, ...]
    constant: float
    examples: int = 0
    yes: int = 0
    ridge: float = 1.0
    fitted_at: str | None = None

    def __post_init__(self) -> None:
        if len(self.features) != len(self.weights):
            raise ValueError(
                f"A model has a weight for each feature, not {len(self.weights)} for {len(self.features)}"
            )

    def score(self, features: Mapping[str, float]) -> float:
        """The likelihood, from 0 to 1, that what has these features is the one"""
        return float(_likelihood(np.array([self._sum(features)]))[0])

    def _sum(self, features: Mapping[str, float]) -> float:
        missing = [name for name in self.features if name not in features]
        if missing:
            raise KeyError(
                f"The model weighs {', '.join(missing)}, which the features given do not have "
                f"(they have {', '.join(sorted(features)) or 'none'})"
            )
        return self.constant + sum(
            weight * float(features[name])
            for name, weight in zip(self.features, self.weights, strict=True)
        )

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> Model:
        data: dict[str, Any] = json.loads(text)
        return cls(
            features=tuple(data["features"]),
            weights=tuple(float(weight) for weight in data["weights"]),
            constant=float(data["constant"]),
            examples=int(data.get("examples", 0)),
            yes=int(data.get("yes", 0)),
            ridge=float(data.get("ridge", 1.0)),
            fitted_at=data.get("fitted_at"),
        )


@dataclasses.dataclass(frozen=True)
class Compared:
    """Of `decisions` decisions (those in which something offered was taken), in how many the one taken was first
    by a model fitted on the other folds (`model`) and by the baseline (`baseline`)"""

    decisions: int
    model: int
    baseline: int

    @property
    def no_worse(self) -> bool:
        return self.model >= self.baseline


@dataclasses.dataclass(frozen=True)
class CallsCompared(Compared):
    """(`compare_calls(count_differences=True)`) the same, and of the examples held out, how many the model and the
    baseline call differently (`differ`): only there can one be right where the other is not"""

    differ: int = 0

    def within(self, margin: float) -> bool:
        """No worse than the baseline by more than chance: the baseline right more often than the model by no more
        than `margin` times the square root of `differ` (the spread of the difference were each of those calls a coin
        toss). A margin of 0 is `no_worse`"""
        if margin < 0:
            raise ValueError(f"A margin is a number of 0 or more, not {margin!r}")
        return self.baseline - self.model <= margin * math.sqrt(self.differ)


def _likelihood(sums: np.ndarray) -> np.ndarray:
    # (cut where `exp` would overflow: a likelihood of 0 or 1 to every digit kept)
    return 1.0 / (1.0 + np.exp(-np.clip(sums, -700.0, 700.0)))


def _rows(
    examples: Sequence[Example], features: Sequence[str]
) -> tuple[np.ndarray, np.ndarray]:
    for example in examples:
        missing = [name for name in features if name not in example.features]
        if missing:
            raise Unfittable(
                f"An example has no {', '.join(missing)} (it has "
                f"{', '.join(sorted(example.features)) or 'no features'}): every example needs every feature fitted"
            )
    rows = sorted(
        (*(float(e.features[name]) for name in features), 1.0 if e.yes else 0.0)
        for e in examples
    )
    table = np.array(rows, dtype=float).reshape(len(rows), len(features) + 1)
    if not np.isfinite(table).all():
        raise Unfittable("An example has a feature that is not a number (nan or inf)")
    return table[:, :-1], table[:, -1]


def fit(
    examples: Iterable[Example],
    features: Sequence[str],
    *,
    ridge: float = 1.0,
    fitted_at: str | None = None,
) -> Model:
    """The model of these examples over these features. Refused (`Unfittable`): no features, a ridge that is not
    above 0, fewer examples than features and one, examples that are all "yes" or all "no", an example without one
    of the features"""
    examples = list(examples)
    features = tuple(features)
    if not features:
        raise Unfittable("A model is fitted over one feature or more: none was named")
    if len(set(features)) != len(features):
        raise Unfittable(f"A feature is named twice: {', '.join(features)}")
    if not ridge > 0:
        raise Unfittable(f"The ridge is a number above 0, not {ridge!r}")
    if len(examples) < len(features) + 2:
        raise Unfittable(
            f"{len(examples)} examples are too few to fit {len(features)} features: "
            f"at least {len(features) + 2} are needed"
        )
    x, y = _rows(examples, features)
    taken = int(y.sum())
    if taken in (0, len(y)):
        raise Unfittable(
            f"All {len(y)} examples are {'yes' if taken else 'no'}: a model needs some of each"
        )
    x = np.hstack([x, np.ones((len(x), 1))])
    pull = np.eye(x.shape[1]) * ridge
    pull[-1, -1] = 0.0
    w = np.zeros(x.shape[1])
    settled = False
    for _ in range(STEPS):
        p = _likelihood(x @ w)
        slope = x.T @ (p - y) + pull @ w
        curve = (x * (p * (1.0 - p))[:, None]).T @ x + pull
        # (the constant has no pull: a grain on the diagonal keeps the step defined when every likelihood is 0 or 1)
        step = np.linalg.solve(curve + 1e-9 * np.eye(len(w)), slope)
        w = w - step
        if not np.isfinite(w).all():
            break
        if float(np.abs(step).max()) < 1e-10:
            settled = True
            break
    if not settled:
        raise Unfittable(
            f"The fit did not settle in {STEPS} steps: the examples are too few or too alike to fit {len(features)} "
            "features"
        )
    return Model(
        features=features,
        weights=tuple(float(v) for v in w[:-1]),
        constant=float(w[-1]),
        examples=len(y),
        yes=taken,
        ridge=float(ridge),
        fitted_at=fitted_at,
    )


def _first(scores: Sequence[float]) -> int:
    """Where the highest score is; of several alike, the first as they were given"""
    return max(range(len(scores)), key=lambda n: (scores[n], -n))


def compare(
    examples: Iterable[Example],
    features: Sequence[str],
    baseline: Callable[[Mapping[str, float]], float],
    *,
    folds: int = 5,
    seed: int = 0,
    ridge: float = 1.0,
) -> Compared:
    """How often the one taken is first by a model fitted on the other folds, and by `baseline`, over the decisions
    (the groups) in which something offered was taken. Refused (`Unfittable`): fewer decisions than folds, fewer
    than two folds, or a fold whose others cannot be fitted"""
    if folds < 2:
        raise Unfittable(f"A comparison is over two folds or more, not {folds}")
    groups: dict[str, list[Example]] = {}
    for example in examples:
        groups.setdefault(example.group, []).append(example)
    names = sorted(groups)
    if len(names) < folds:
        raise Unfittable(
            f"{len(names)} decisions are too few to compare over {folds} folds"
        )
    random.Random(seed).shuffle(names)
    decisions = by_model = by_baseline = 0
    for fold in range(folds):
        held = names[fold::folds]
        kept = set(names) - set(held)
        model = fit(
            (e for name in sorted(kept) for e in groups[name]), features, ridge=ridge
        )
        for name in held:
            rows = groups[name]
            if not any(e.yes for e in rows):
                continue
            decisions += 1
            sums = [model._sum(e.features) for e in rows]
            given = [baseline(e.features) for e in rows]
            by_model += rows[_first(sums)].yes
            by_baseline += rows[_first(given)].yes
    return Compared(decisions=decisions, model=by_model, baseline=by_baseline)


def _in_order(examples: Sequence[Example], features: Sequence[str]) -> list[Example]:
    return sorted(
        examples,
        key=lambda e: (e.group, *(float(e.features[name]) for name in features), e.yes),
    )


def _dealt(
    ordered: Sequence[Example], folds: int, seed: int, stratified: bool
) -> list[int]:
    """The places of the examples in the order they are dealt round the folds (fold `k` holds `places[k::folds]`)"""
    if stratified:
        shuffle = random.Random(seed).shuffle
        yes = [n for n, e in enumerate(ordered) if e.yes]
        no = [n for n, e in enumerate(ordered) if not e.yes]
        shuffle(yes)
        shuffle(no)
        return yes + no
    places = list(range(len(ordered)))
    random.Random(seed).shuffle(places)
    return places


def folds_of(
    examples: Iterable[Example],
    features: Sequence[str],
    *,
    folds: int = 5,
    seed: int = 0,
    stratified: bool = False,
) -> list[list[Example]]:
    """The examples each fold of `compare_calls` holds out, as it deals them (to see how they are dealt)"""
    ordered = _in_order(list(examples), tuple(features))
    places = _dealt(ordered, folds, seed, stratified)
    return [[ordered[n] for n in sorted(places[fold::folds])] for fold in range(folds)]


def compare_calls(
    examples: Iterable[Example],
    features: Sequence[str],
    *,
    folds: int = 5,
    seed: int = 0,
    ridge: float = 1.0,
    baseline: Callable[[Mapping[str, float]], float] | None = None,
    stratified: bool = False,
    count_differences: bool = False,
) -> Compared:
    """For examples that are each a decision by itself (yes or no of the whole of it): how often a model fitted on
    the other folds calls it rightly ("yes" at a likelihood of a half or more), and how often always answering the
    commoner of the two among those other folds does ("yes" when they are as many), or, with `baseline`, how often
    its likelihood does ("yes" at a half or more), on the same held-out examples. The examples are put in one
    order first (by `group`, then by what they are), so the same examples in any order give the same answer.
    `stratified`: the "yes" and the "no" are dealt into the folds apart (each shuffled by the seed, the "yes" first,
    round the folds in turn), so each fold has as many of each as another, give or take one, and every part fitted on
    has both answers where there are two of each or more. `count_differences`: a `CallsCompared`, with how many of
    the held-out examples the two call differently. Refused (`Unfittable`): fewer examples than folds, fewer than
    two folds, or a fold whose others cannot be fitted"""
    if folds < 2:
        raise Unfittable(f"A comparison is over two folds or more, not {folds}")
    features = tuple(features)
    for example in (examples := list(examples)):
        missing = [name for name in features if name not in example.features]
        if missing:
            raise Unfittable(
                f"An example has no {', '.join(missing)}: every example needs every feature fitted"
            )
    ordered = _in_order(examples, features)
    if len(ordered) < folds:
        raise Unfittable(
            f"{len(ordered)} decisions are too few to compare over {folds} folds"
        )
    places = _dealt(ordered, folds, seed, stratified)
    by_model = by_baseline = differ = 0
    for fold in range(folds):
        held = set(places[fold::folds])
        others = [ordered[n] for n in range(len(ordered)) if n not in held]
        model = fit(others, features, ridge=ridge)
        commoner = 2 * sum(e.yes for e in others) >= len(others)
        for n in sorted(held):
            example = ordered[n]
            fitted = model._sum(example.features) >= 0.0
            called = commoner if baseline is None else baseline(example.features) >= 0.5
            by_model += fitted == example.yes
            by_baseline += called == example.yes
            differ += fitted != called
    if count_differences:
        return CallsCompared(
            decisions=len(ordered), model=by_model, baseline=by_baseline, differ=differ
        )
    return Compared(decisions=len(ordered), model=by_model, baseline=by_baseline)
