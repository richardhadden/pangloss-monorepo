"""`pangloss_learn.maths` (step 11.1 of implementation_docs/similarity-build-plan.md): planted weights are found
again, the same examples make the same model in any order, examples a feature divides cleanly do not send a weight
off, every refusal by its message, and `compare` says a model is better only where it is"""

import math
import random

import pytest
from pangloss_learn import (
    Compared,
    Example,
    Model,
    Unfittable,
    compare,
    compare_calls,
    fit,
)

FEATURES = ("name", "graph", "shared")


def planted(
    seed: int, count: int, weights=(4.0, -2.0, 1.5), constant=-1.0
) -> list[Example]:
    """Examples whose answers are drawn by a known model: each feature a number from 0 to 1, "yes" with the
    likelihood the weights give"""
    rng = random.Random(seed)
    made = []
    for n in range(count):
        values = [rng.random() for _ in FEATURES]
        total = constant + sum(w * v for w, v in zip(weights, values, strict=True))
        made.append(
            Example(
                dict(zip(FEATURES, values, strict=True)),
                rng.random() < 1 / (1 + math.exp(-total)),
                group=f"g{n // 5}",
            )
        )
    return made


# -- fit ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_planted_weights_are_found_again(seed):
    model = fit(planted(seed, 20_000), FEATURES, ridge=1e-6)
    assert model.features == FEATURES
    assert model.weights == pytest.approx((4.0, -2.0, 1.5), abs=0.2)
    assert model.constant == pytest.approx(-1.0, abs=0.15)
    assert model.examples == 20_000
    assert 0 < model.yes < 20_000


def test_the_same_examples_make_the_same_model_in_any_order():
    examples = planted(4, 500)
    first = fit(examples, FEATURES)
    shuffled = list(examples)
    random.Random(9).shuffle(shuffled)
    assert fit(shuffled, FEATURES) == first
    assert fit(reversed(examples), FEATURES) == first


def test_examples_a_feature_divides_cleanly_do_not_send_its_weight_off():
    examples = [Example({"name": n / 100}, n >= 50) for n in range(100)]
    model = fit(examples, ["name"])
    assert 0 < model.weights[0] < 50
    assert model.score({"name": 0.9}) > 0.5 > model.score({"name": 0.1})
    # (a smaller ridge, a steeper weight: still a number)
    steeper = fit(examples, ["name"], ridge=1e-4)
    assert model.weights[0] < steeper.weights[0] < math.inf


def test_the_ridge_does_not_pull_the_constant():
    # (one feature that says nothing: the likelihood is the share of "yes", whatever the ridge)
    examples = [Example({"name": 0.0}, n < 20) for n in range(100)]
    model = fit(examples, ["name"], ridge=1000.0)
    assert model.score({"name": 0.0}) == pytest.approx(0.2, abs=1e-6)


def test_a_score_is_the_logistic_of_the_weighted_sum():
    model = Model(("name", "graph"), (2.0, -1.0), 0.5)
    assert model.score({"name": 1.0, "graph": 0.5, "more": 9}) == pytest.approx(
        1 / (1 + math.exp(-2.0))
    )
    assert Model(("name",), (1000.0,), 0.0).score({"name": 5.0}) == 1.0
    # (a sum far below 0 is cut before `exp`: nearly 0, and never an overflow)
    assert 0.0 <= Model(("name",), (-1000.0,), 0.0).score({"name": 5.0}) < 1e-300


def test_a_score_without_a_feature_the_model_weighs_is_refused():
    model = Model(("name", "graph"), (2.0, -1.0), 0.5)
    with pytest.raises(
        KeyError, match=r"The model weighs graph, which the features.*they have name"
    ):
        model.score({"name": 1.0})


def test_a_model_goes_to_json_and_back():
    model = fit(planted(5, 200), FEATURES, fitted_at="2026-11-23T10:00:00Z")
    assert Model.from_json(model.to_json()) == model
    assert model.fitted_at == "2026-11-23T10:00:00Z"


def test_a_model_with_other_weights_than_features_is_refused():
    with pytest.raises(ValueError, match=r"a weight for each feature, not 1 for 2"):
        Model(("name", "graph"), (1.0,), 0.0)


@pytest.mark.parametrize(
    "examples, features, more, message",
    [
        (planted(1, 50), [], {}, r"over one feature or more: none was named"),
        (planted(1, 50), ["name", "name"], {}, r"A feature is named twice: name, name"),
        (
            planted(1, 50),
            FEATURES,
            {"ridge": 0},
            r"The ridge is a number above 0, not 0",
        ),
        (
            planted(1, 4),
            FEATURES,
            {},
            r"4 examples are too few to fit 3 features: at least 5 are needed",
        ),
        (
            [Example({"name": n / 10}, True) for n in range(10)],
            ["name"],
            {},
            r"All 10 examples are yes: a model needs some of each",
        ),
        (
            [Example({"name": n / 10}, False) for n in range(10)],
            ["name"],
            {},
            r"All 10 examples are no: a model needs some of each",
        ),
        (
            [*planted(1, 50), Example({"name": 1.0}, True)],
            FEATURES,
            {},
            r"An example has no graph, shared \(it has name\)",
        ),
        (
            [*planted(1, 50), Example(dict.fromkeys(FEATURES, math.nan), True)],
            FEATURES,
            {},
            r"a feature that is not a number",
        ),
    ],
)
def test_what_cannot_be_fitted_is_refused_with_why(examples, features, more, message):
    with pytest.raises(Unfittable, match=message):
        fit(examples, features, **more)


# -- compare -----------------------------------------------------------------------------------------------------------


def decisions(seed: int, count: int, telling: str) -> list[Example]:
    """Decisions of four offered, one taken: the one taken has the highest `telling` feature; the other feature is
    noise"""
    rng = random.Random(seed)
    made = []
    for n in range(count):
        rows = [{"name": rng.random(), "graph": rng.random()} for _ in range(4)]
        taken = max(range(4), key=lambda k: rows[k][telling])
        made += [Example(row, k == taken, f"d{n:04d}") for k, row in enumerate(rows)]
    return made


def test_a_model_wins_where_the_baseline_looks_at_the_wrong_feature():
    found = compare(decisions(1, 200, "graph"), ["name", "graph"], lambda f: f["name"])
    assert found.decisions == 200
    assert found.model > 180
    assert found.baseline < 90
    assert found.no_worse


def test_a_model_does_not_win_where_the_baseline_is_the_truth():
    found = compare(decisions(2, 200, "name"), ["name", "graph"], lambda f: f["name"])
    assert found.baseline == found.decisions == 200
    assert found.model <= found.baseline
    # (and fitted on the feature that says nothing alone, it is worse)
    worse = compare(decisions(2, 200, "name"), ["graph"], lambda f: f["name"])
    assert worse.model < 100
    assert not worse.no_worse


def test_a_comparison_is_the_same_twice_and_another_with_another_seed():
    examples = decisions(3, 100, "graph")
    noisy = [
        Example(e.features, e.yes if n % 7 else not e.yes, e.group)
        for n, e in enumerate(examples)
    ]
    first = compare(noisy, ["name", "graph"], lambda f: f["name"], seed=1)
    assert (
        compare(list(reversed(noisy)), ["name", "graph"], lambda f: f["name"], seed=1)
        == first
    )
    assert isinstance(first, Compared)


def test_a_decision_in_which_nothing_offered_was_taken_is_not_counted():
    examples = decisions(4, 50, "graph")
    none = [Example({"name": 0.5, "graph": 0.5}, False, f"n{n}") for n in range(10)]
    found = compare([*examples, *none], ["name", "graph"], lambda f: f["graph"])
    assert found.decisions == 50
    assert found.baseline == 50


def test_of_several_scored_alike_the_first_given_is_the_first():
    rows = [
        *decisions(5, 40, "graph"),
        Example({"name": 0.3, "graph": 0.3}, False, "tie"),
        Example({"name": 0.3, "graph": 0.3}, True, "tie"),
    ]
    found = compare(rows, ["name", "graph"], lambda f: f["graph"])
    # (in "tie" the one given first is first by both, and it was not the one taken)
    assert found.decisions == 41
    assert found.baseline == 40


@pytest.mark.parametrize(
    "more, message",
    [
        ({"folds": 1}, r"over two folds or more, not 1"),
        ({"folds": 50}, r"10 decisions are too few to compare over 50 folds"),
    ],
)
def test_what_cannot_be_compared_is_refused_with_why(more, message):
    with pytest.raises(Unfittable, match=message):
        compare(decisions(6, 10, "graph"), ["name", "graph"], lambda f: 0.0, **more)


def calls(seed: int, count: int, telling: bool, yes: float = 0.5) -> list[Example]:
    """Decisions that are each one example: `best` is low when the answer is yes (if `telling`), `noise` says
    nothing"""
    rng = random.Random(seed)
    made = []
    for n in range(count):
        answer = rng.random() < yes
        best = rng.gauss(0.3 if answer else 0.7, 0.1) if telling else rng.random()
        made.append(Example({"best": best, "noise": rng.random()}, answer, f"d{n}"))
    return made


def test_calls_are_right_more_often_than_the_commoner_where_a_feature_tells():
    found = compare_calls(calls(1, 400, True), ["best", "noise"])
    assert found.decisions == 400
    assert found.model > 0.9 * found.decisions
    assert found.baseline < 0.6 * found.decisions
    assert found.no_worse


def test_calls_are_no_better_than_the_commoner_where_nothing_tells():
    found = compare_calls(calls(2, 400, False, yes=0.8), ["best", "noise"])
    assert 0.7 * found.decisions < found.baseline < 0.9 * found.decisions
    assert found.model <= found.baseline + 0.02 * found.decisions


def test_calls_are_compared_the_same_in_any_order_and_otherwise_by_another_seed():
    examples = calls(3, 200, True)
    shuffled = examples[:]
    random.Random(9).shuffle(shuffled)
    assert compare_calls(examples, ["best", "noise"]) == compare_calls(
        shuffled, ["best", "noise"]
    )
    counts = {
        (found.model, found.baseline)
        for found in (
            compare_calls(calls(3, 200, False), ["best", "noise"], seed=seed)
            for seed in range(6)
        )
    }
    assert len(counts) > 1


def test_every_call_is_counted_whichever_the_answer():
    examples = calls(4, 50, True)
    found = compare_calls(examples, ["best"], folds=5)
    assert found.decisions == 50


@pytest.mark.parametrize(
    ("more", "message"),
    [
        ({"folds": 1}, "two folds or more"),
        ({"folds": 500}, "too few to compare over 500 folds"),
    ],
)
def test_calls_that_cannot_be_compared_are_refused_with_why(more, message):
    with pytest.raises(Unfittable, match=message):
        compare_calls(calls(5, 60, True), ["best", "noise"], **more)


def test_calls_without_a_feature_are_refused():
    with pytest.raises(Unfittable, match="has no gap"):
        compare_calls(calls(6, 60, True), ["best", "gap"])


def test_calls_are_compared_with_a_score_set_by_hand_when_one_is_given():
    """The baseline's call is "yes" at a likelihood of a half or more, on the same held-out examples: a score that
    reads `best` rightly is right where the commoner is not, and a score that is always wrong is never right"""
    examples = calls(7, 300, True)
    commoner = compare_calls(examples, ["best", "noise"])
    by_hand = compare_calls(
        examples,
        ["best", "noise"],
        baseline=lambda features: 1.0 if features["best"] < 0.5 else 0.0,
    )
    assert by_hand.model == commoner.model and by_hand.decisions == 300
    assert by_hand.baseline > 0.9 * by_hand.decisions > commoner.baseline
    wrong = compare_calls(
        examples,
        ["best", "noise"],
        baseline=lambda features: 0.0 if features["best"] < 0.5 else 1.0,
    )
    assert wrong.baseline < 0.1 * wrong.decisions and wrong.no_worse
    # (exactly a half is "yes")
    half = compare_calls(examples, ["best", "noise"], baseline=lambda features: 0.5)
    assert half.baseline == sum(e.yes for e in examples)


def test_calls_dealt_by_their_answer_give_every_fold_as_many_of_each_and_change_nothing_unless_asked():
    """Dealt by the answer, each fold holds as many "yes" and as many "no" as another, give or take one; dealt as
    they come, they do not, and with two "no" among forty a part fitted on can lack both (refused). The default
    gives what it gave before the option was added (the figures of the commit before, pinned)"""
    from pangloss_learn.maths import folds_of

    for count, yes in [(40, 0.95), (37, 0.3), (200, 0.5)]:
        examples = calls(12, count, True, yes=yes)
        for seed in range(5):
            dealt = folds_of(examples, ["best", "noise"], seed=seed, stratified=True)
            assert sorted(e.group for fold in dealt for e in fold) == sorted(e.group for e in examples)  # fmt: skip
            for answer in (True, False):
                each = [sum(e.yes is answer for e in fold) for fold in dealt]
                assert max(each) - min(each) <= 1, (count, seed, answer, each)
    two_no = [
        Example({"best": 0.1 * (n % 7), "noise": 0.01 * n}, n >= 2, f"d{n:02d}")
        for n in range(40)
    ]
    uneven = refused = 0
    for seed in range(20):
        dealt = folds_of(two_no, ["best", "noise"], seed=seed)
        uneven += max(sum(not e.yes for e in f) for f in dealt) > 1
        try:
            compare_calls(two_no, ["best", "noise"], seed=seed)
        except Unfittable:
            refused += 1
        found = compare_calls(two_no, ["best", "noise"], seed=seed, stratified=True)
        assert found.decisions == 40
        assert [sum(not e.yes for e in f) for f in folds_of(two_no, ["best", "noise"], seed=seed, stratified=True)].count(1) == 2  # fmt: skip
    assert uneven > 0 and refused == uneven

    # (off by default: what was given before is given still, to the figure)
    by_hand = lambda features: 1.0 if features["best"] < 0.5 else 0.0  # noqa: E731
    for (seed, count, telling, yes, fold_seed), commoner, hand in [
        ((3, 200, True, 0.5, 0), (200, 194, 113), (200, 194, 196)),
        ((2, 400, False, 0.8, 0), (400, 321, 321), (400, 321, 188)),
        ((11, 60, True, 0.3, 4), (60, 52, 36), (60, 52, 58)),
    ]:
        examples = calls(seed, count, telling, yes=yes)
        plain = compare_calls(examples, ["best", "noise"], seed=fold_seed)
        assert type(plain) is Compared
        assert (plain.decisions, plain.model, plain.baseline) == commoner
        given = compare_calls(examples, ["best", "noise"], seed=fold_seed, baseline=by_hand)  # fmt: skip
        assert (given.decisions, given.model, given.baseline) == hand
        assert plain == compare_calls(examples, ["best", "noise"], seed=fold_seed, stratified=False, count_differences=False)  # fmt: skip


def test_calls_dealt_by_their_answer_are_the_same_in_any_order():
    examples = calls(8, 120, True, yes=0.2)
    shuffled = examples[:]
    random.Random(4).shuffle(shuffled)
    assert compare_calls(examples, ["best", "noise"], stratified=True) == compare_calls(
        shuffled, ["best", "noise"], stratified=True
    )


def test_the_calls_that_differ_are_counted_and_the_margin_allows_for_chance():
    from pangloss_learn import CallsCompared

    examples = calls(7, 300, True)
    by_hand = lambda features: 1.0 if features["best"] < 0.5 else 0.0  # noqa: E731
    found = compare_calls(examples, ["best", "noise"], baseline=by_hand, count_differences=True)  # fmt: skip
    assert isinstance(found, CallsCompared)
    plain = compare_calls(examples, ["best", "noise"], baseline=by_hand)
    assert (found.decisions, found.model, found.baseline) == (plain.decisions, plain.model, plain.baseline)  # fmt: skip
    # (only where the two call differently can one be right and the other not)
    assert abs(found.model - found.baseline) <= found.differ <= found.decisions
    # (a baseline that is always wrong: every call differs where the model is right)
    wrong = compare_calls(examples, ["best", "noise"], baseline=lambda f: 1.0 - by_hand(f), count_differences=True)  # fmt: skip
    assert wrong.differ >= wrong.model - wrong.baseline > 0

    # (the check: worse by more than margin × √differ is refused; a margin of 0 is "no worse")
    close = CallsCompared(decisions=100, model=95, baseline=96, differ=9)
    assert not close.no_worse and not close.within(0)
    assert close.within(1.0) and close.within(1 / 3)
    assert not close.within(0.3)
    far = CallsCompared(decisions=100, model=80, baseline=96, differ=16)
    assert not far.within(1.0) and far.within(4.0)
    level = CallsCompared(decisions=100, model=96, baseline=96, differ=0)
    assert level.within(0) and level.within(1.0)
    with pytest.raises(ValueError, match="A margin is a number of 0 or more"):
        level.within(-1)
