"""What comparison learns from people's judgements, with no database in it (implementation_docs/spaces-and-comparison-
plan.md, step 6.6; implementation_docs/compare.md, "Learning from judgements"). The fit and its comparison are
`pangloss_learn`'s; this says what the examples are. `fits.py` reads the judgements and writes the fits.

A judgement is given as plain data (`Judged`): the two statements it cites, as they are read **now** (`maths.Told`,
or None where one is no longer there to read: call 8, the features are worked out at learning time), its verdict,
when it was made and whether a statement it cites has changed since it was cited. Only the newest judgement of a
pair counts (`newest`); of those, each is an example of one of two models, or is left out and counted by why
(`LEFT_OUT`):

- **one event or two** (`maths.ONE_EVENT`): two statements neither of which prescribes, of a compared class in
  common, neither saying nothing of its contents, which the rules do not settle (`maths.by_rule` is None: where the
  logistic decides). `agree` and `disagree` are yes, `two_events` no. Its features (`ONE_EVENT_FEATURES`): the terms
  of `maths.features` but `bias`, and `maths.BY_HAND`, the log odds of the hand-set likelihood
  (`maths.logistic(features, maths.WEIGHTS)`; why it is there: the plan's "6.6, measured before its brief");
- **does this answer that** (`maths.ANSWERS_IT`): one statement that prescribes and one that does not, where the
  other is of the thing prescribed (`maths.answers`). `carried_out`, `carried_out_otherwise`, `not_carried_out` and
  `breach` are yes, `two_events` no. Its features (`ANSWER_FEATURES`): the terms of `maths.answer_features` but
  `bias`, and `BY_HAND` of `maths.logistic(those, maths.ANSWER_WEIGHTS)`.

`fit_both` fits each (`pangloss_learn.fit`; `Unfittable`: none, with why) and compares it, on judgements held out
(`pangloss_learn.compare_calls`, five folds dealt by a seed, the "yes" and the "no" apart so that every part fitted on
has both answers where there are two of each), with **the hand-set score**: how often each calls the judgement rightly
(a likelihood of a half or more is "yes"), and on how many the two call differently (`differ`). A fit passes
(`passes`) unless the hand-set score is right more often by more than a margin times the square root of `differ`
(`COMPARE_LEARN_MARGIN`, `fits.py`; 0 is "no worse")
`as_fitted` gives a model as `maths.verdict(fitted=...)` takes it. `signature` is what makes fits comparable: the
features of both models, `maths.WEIGHTS`, `maths.ANSWER_WEIGHTS` and each compared class's rules; a fit of another
signature is not used.

The examples, the fits and their comparisons are the same whatever the order the judgements are given in."""

import dataclasses
import datetime
import json
from collections.abc import Iterable, Mapping, Sequence

from pangloss_learn import CallsCompared, Example, Model, Unfittable, compare_calls, fit

from pangloss_compare import maths

# (how the comparisons are made: the same each time, so that a fit says the same of the same judgements)
FOLDS = 5
SEED = 0
RIDGE = 1.0

ONE_EVENT_FEATURES: tuple[str, ...] = (
    *(name for name in maths.WEIGHTS if name != "bias"),
    maths.BY_HAND,
)
ANSWER_FEATURES: tuple[str, ...] = (
    *(name for name in maths.ANSWER_WEIGHTS if name != "bias"),
    maths.BY_HAND,
)

MODELS = (maths.ONE_EVENT, maths.ANSWERS_IT)

# What each verdict says of its model (yes or no); a verdict of the other kind of pair is left out
YES_NO: dict[str, dict[str, bool]] = {
    maths.ONE_EVENT: {"agree": True, "disagree": True, "two_events": False},
    maths.ANSWERS_IT: {
        "carried_out": True,
        "carried_out_otherwise": True,
        "not_carried_out": True,
        "breach": True,
        "two_events": False,
    },
}

# Why a judgement is no example, by name
OLDER = "older"
"""A newer judgement of the same pair counts"""
CHANGED = "changed"
"""A statement it cites has changed since it was cited: it may no longer be what was judged"""
UNREAD = "unread"
"""A statement it cites is not there to read as compared (deleted, of a class no longer compared, in a space that
is not)"""
ITSELF = "itself"
"""It cites one statement twice"""
NOT_COMPARED = "not_compared"
"""The two have no compared class in common"""
SAYS_NOTHING = "says_nothing"
"""One of the two leans neither way: it says nothing of its contents"""
TWO_PRESCRIPTIONS = "two_prescriptions"
"""Both prescribe: nothing is learnt of two prescriptions"""
BY_RULE = "by_rule"
"""Of two that describe: the rules settle it (`once_per`, or no identifying entity in common), no weighing"""
NOT_THE_THING = "not_the_thing"
"""Of a prescription and another: the other is not of the thing prescribed (`maths.answers`), no weighing"""
OTHER_VERDICT = "other_verdict"
"""A verdict of the other kind of pair (`agree` of a prescription and what came of it, `carried_out` of two that
describe)"""

LEFT_OUT = (
    OLDER,
    CHANGED,
    UNREAD,
    ITSELF,
    NOT_COMPARED,
    SAYS_NOTHING,
    TWO_PRESCRIPTIONS,
    BY_RULE,
    NOT_THE_THING,
    OTHER_VERDICT,
)


@dataclasses.dataclass(frozen=True)
class Judged:
    """A judgement as plain data: its id, verdict, the ids it cites (`statement`, `other`), the two statements as
    they are read now (None: not there to read), when it was made and whether a statement it cites has changed
    since it was cited"""

    id: str
    verdict: str
    cited: tuple[str, str]
    a: maths.Told | None
    b: maths.Told | None
    at: datetime.datetime | None = None
    changed: bool = False

    @property
    def pair(self) -> tuple[str, str]:
        """The pair it is of, in either order"""
        first, second = self.cited
        return (first, second) if first <= second else (second, first)


@dataclasses.dataclass
class Examples:
    """The examples of each model (`by_model`, by `maths.ONE_EVENT` and `maths.ANSWERS_IT`), how many judgements
    were read, those left out by why (`left_out`, a count for each of `LEFT_OUT`), and when the newest judgement read
    was made (taken or left out: with how many were read, what tells a later run that nothing is new)"""

    judgements: int = 0
    by_model: dict[str, list[Example]] = dataclasses.field(
        default_factory=lambda: {name: [] for name in MODELS}
    )
    left_out: dict[str, int] = dataclasses.field(
        default_factory=lambda: dict.fromkeys(LEFT_OUT, 0)
    )
    latest: datetime.datetime | None = None

    @property
    def taken(self) -> int:
        """How many judgements are examples (of either model)"""
        return sum(len(found) for found in self.by_model.values())


def _key(judged: Judged) -> tuple[bool, datetime.datetime, str]:
    least = datetime.datetime.min.replace(tzinfo=datetime.UTC)
    return judged.at is not None, judged.at or least, judged.id


def newest(judgements: Iterable[Judged]) -> tuple[list[Judged], int]:
    """The newest judgement of each pair (newest by when it was made; one with no record of when is older than any
    with; then by id, the greater: as `judgements.newest_first`), in the order of their pairs, and how many older
    ones there were"""
    by_pair: dict[tuple[str, str], Judged] = {}
    seen = 0
    for judged in judgements:
        seen += 1
        held = by_pair.get(judged.pair)
        if held is None or _key(judged) > _key(held):
            by_pair[judged.pair] = judged
    return [by_pair[pair] for pair in sorted(by_pair)], seen - len(by_pair)


def by_hand_likelihood(features: Mapping[str, float]) -> float:
    """The hand-set likelihood of an example, from its `BY_HAND` term: what a fit is compared with"""
    return maths.logistic(
        {maths.BY_HAND: features[maths.BY_HAND]}, {maths.BY_HAND: 1.0}
    )


def _without_bias(values: Mapping[str, float]) -> dict[str, float]:
    return {name: float(value) for name, value in values.items() if name != "bias"}


def example_of(
    judged: Judged, rules: Mapping[str, maths.Rules]
) -> tuple[str, Example] | str:
    """The model a judgement is an example of, and the example; or why it is none (one of `LEFT_OUT`, but `OLDER`)"""
    if judged.changed:
        return CHANGED
    a, b = judged.a, judged.b
    if a is None or b is None:
        return UNREAD
    if a.id == b.id:
        return ITSELF
    common = maths.common_class(a, b)
    if common is None or common not in rules:
        return NOT_COMPARED
    if maths.NEITHER in (maths.stance(a.signature), maths.stance(b.signature)):
        return SAYS_NOTHING
    # (of a prescription and another, the prescription first, as `maths.verdict` has it)
    if maths.prescribes(b.signature) and not maths.prescribes(a.signature):
        a, b = b, a
    of = rules[common]
    compared = maths.compare_fields(a, b, of)
    group = "|".join(judged.pair)
    if maths.prescribes(a.signature):
        if maths.prescribes(b.signature):
            return TWO_PRESCRIPTIONS
        if not maths.answers(compared, of, a):
            return NOT_THE_THING
        model = maths.ANSWERS_IT
        values = maths.answer_features(a, b, compared, of)
        if values["by_another"] or values["out_of_order"]:
            # (done by another, or on the wrong side of when it was prescribed: `maths._answered` settles these
            # by rule before any likelihood is asked, so a judgement of one teaches the likelihood nothing, and
            # the hand-set score would be held to a call it never makes)
            return BY_RULE
        weights = maths.ANSWER_WEIGHTS
    else:
        if maths.by_rule(compared, of) is not None:
            return BY_RULE
        model = maths.ONE_EVENT
        values = maths.features(a, b, compared, of)
        weights = maths.WEIGHTS
    yes = YES_NO[model].get(judged.verdict)
    if yes is None:
        return OTHER_VERDICT
    features = {
        **_without_bias(values),
        maths.BY_HAND: maths.log_odds(maths.logistic(values, weights)),
    }
    return model, Example(features, yes, group)


def examples(
    judgements: Iterable[Judged], rules: Mapping[str, maths.Rules]
) -> Examples:
    """The examples of both models of these judgements (the module's docstring): the newest of each pair, each an
    example or left out and counted by why. `rules`: each compared class's (`rules.rules()`)"""
    judgements = list(judgements)
    found = Examples(judgements=len(judgements))
    taken, found.left_out[OLDER] = newest(judgements)
    for judged in taken:
        made = example_of(judged, rules)
        if isinstance(made, str):
            found.left_out[made] += 1
            continue
        model, example = made
        found.by_model[model].append(example)
    made_at = [judged.at for judged in judgements if judged.at is not None]
    found.latest = max(made_at) if made_at else None
    for model in MODELS:
        found.by_model[model].sort(key=lambda e: e.group)
    return found


@dataclasses.dataclass(frozen=True)
class Fitted:
    """One of the two models: the model, or why it could not be fitted; what its comparison with the hand-set score
    found, or why it could not be made; and how many examples it is of"""

    examples: int
    model: Model | None
    why: str | None = None
    compared: CallsCompared | None = None
    compared_why: str | None = None

    def passes(self, margin: float) -> bool:
        """Fitted, compared, and on the judgements held out not worse than the hand-set score by more than `margin`
        times the square root of how many the two call differently (`CallsCompared.within`; 0: right as often or
        more)"""
        return self.compared is not None and self.compared.within(margin)


@dataclasses.dataclass(frozen=True)
class Fits:
    one_event: Fitted
    answers: Fitted

    def of(self, model: str) -> Fitted:
        return self.one_event if model == maths.ONE_EVENT else self.answers


def features_of(model: str) -> tuple[str, ...]:
    return ONE_EVENT_FEATURES if model == maths.ONE_EVENT else ANSWER_FEATURES


def _fitted(
    found: Sequence[Example], features: Sequence[str], fitted_at: str | None
) -> Fitted:
    try:
        model = fit(found, features, ridge=RIDGE, fitted_at=fitted_at)
    except Unfittable as error:
        return Fitted(len(found), None, str(error))
    try:
        compared = compare_calls(
            found,
            features,
            folds=FOLDS,
            seed=SEED,
            ridge=RIDGE,
            baseline=by_hand_likelihood,
            stratified=True,
            count_differences=True,
        )
    except Unfittable as error:
        return Fitted(len(found), model, None, None, str(error))
    assert isinstance(compared, CallsCompared)
    return Fitted(len(found), model, None, compared)


def fit_both(found: Examples, fitted_at: str | None = None) -> Fits:
    """Each model fitted on its examples and compared with the hand-set score on judgements held out (the module's
    docstring). `fitted_at`: what the models say they were fitted at"""
    return Fits(
        _fitted(found.by_model[maths.ONE_EVENT], ONE_EVENT_FEATURES, fitted_at),
        _fitted(found.by_model[maths.ANSWERS_IT], ANSWER_FEATURES, fitted_at),
    )


def digest(found: Examples) -> str:
    """What the examples of both models are, as a short text (a hash of each model's examples in their order, their
    features, answers and groups): the same examples give the same digest, any change of one another"""
    import hashlib

    data = {
        model: [
            [example.group, example.yes, sorted(example.features.items())]
            for example in found.by_model[model]
        ]
        for model in MODELS
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:32]


def as_fitted(model: Model) -> dict[str, float]:
    """A model's weights by the name of its feature, `bias` its constant: what `maths.verdict(fitted=...)` takes of
    one model"""
    return {
        **dict(zip(model.features, model.weights, strict=True)),
        "bias": model.constant,
    }


def signature(rules: Mapping[str, maths.Rules]) -> str:
    """What makes fits comparable, as JSON text: the features of both models, the hand-set weights a fit corrects
    (`maths.WEIGHTS`, `maths.ANSWER_WEIGHTS`), and each compared class's rules"""
    return json.dumps(
        {
            "features": {
                maths.ONE_EVENT: list(ONE_EVENT_FEATURES),
                maths.ANSWERS_IT: list(ANSWER_FEATURES),
            },
            "weights": dict(maths.WEIGHTS),
            "answer_weights": dict(maths.ANSWER_WEIGHTS),
            "rules": {
                name: {
                    "identifying": list(of.identifying),
                    "once_per": of.once_per,
                    "recurs": of.recurs,
                }
                for name, of in rules.items()
            },
        },
        sort_keys=True,
    )
