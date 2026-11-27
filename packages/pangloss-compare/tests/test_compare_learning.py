"""What comparison learns from people's judgements (`pangloss_compare.learning`; implementation_docs/spaces-and-
comparison-plan.md, step 6.6), with no database: which judgements are examples of which model and what is left out
(each reason by name), the newest of a pair, the same in any order, a fit as the verdict takes it, a fit worse than
the hand-set score (and the margin allowed for chance), folds dealt by the answer, what makes fits comparable, and
floors on the planted world for comparison."""

import datetime
import random

import pytest
from pangloss_compare import learning, maths
from pangloss_compare.learning import Judged
from pangloss_compare.maths import verdict

import test_compare_maths
from test_compare_maths import (
    BY_MAX,
    ORDERED,
    RULES,
    gathering,
    going,
    models,  # noqa: F401 (a fixture)
    ordered,
    pairs_by_rule,
    said,
    statements_of,
    told,
)

AT = datetime.datetime(2026, 11, 1, tzinfo=datetime.UTC)


def judged(a, b, verdict: str, n: int = 0, **more) -> Judged:
    return Judged(f"j{n:04d}", verdict, (a.id, b.id), a, b, AT + datetime.timedelta(seconds=n), **more)  # fmt: skip


def example(j: Judged):
    return learning.example_of(j, RULES)


# (a gathering told twice, the logistic deciding; an order and the going that answers it)
def told_twice():
    return gathering(), gathering()


def answered():
    return ordered(), going()


# ---------------------------------------------------------------------------
# Which judgements are examples of which model
# ---------------------------------------------------------------------------


def test_two_that_describe_are_one_event_or_two_and_a_prescription_and_another_answer_it_or_not():
    a, b = told_twice()
    for said_so, yes in [("agree", True), ("disagree", True), ("two_events", False)]:
        model, found = example(judged(a, b, said_so))
        assert model == maths.ONE_EVENT and found.yes is yes
        assert set(found.features) == set(learning.ONE_EVENT_FEATURES)
        values = maths.features(a, b, maths.compare_fields(a, b, RULES["Activity"]), RULES["Activity"])  # fmt: skip
        assert found.features[maths.BY_HAND] == pytest.approx(maths.log_odds(maths.logistic(values, maths.WEIGHTS)))  # fmt: skip
        assert "bias" not in found.features
    order, went = answered()
    for said_so, yes in [
        ("carried_out", True),
        ("carried_out_otherwise", True),
        ("not_carried_out", True),
        ("breach", True),
        ("two_events", False),
    ]:
        # (the prescription first, whichever way the judgement cites the two)
        for first, second in [(order, went), (went, order)]:
            model, found = example(judged(first, second, said_so))
            assert model == maths.ANSWERS_IT and found.yes is yes
            assert set(found.features) == set(learning.ANSWER_FEATURES)
            assert found.features[maths.BY_HAND] == pytest.approx(maths.log_odds(maths.logistic(maths.answer_features(order, went, maths.compare_fields(order, went, RULES["Going"]), RULES["Going"]), maths.ANSWER_WEIGHTS)))  # fmt: skip


def test_what_is_no_example_is_left_out_and_counted_by_why():
    a, b = told_twice()
    order, went = answered()
    cases = {
        learning.CHANGED: judged(a, b, "agree", changed=True),
        learning.UNREAD: Judged("j", "agree", (a.id, "gone"), a, None, AT),
        learning.ITSELF: judged(a, a, "agree"),
        learning.NOT_COMPARED: judged(a, told("Birth", person="a"), "two_events"),
        learning.SAYS_NOTHING: judged(a, gathering(said(0)), "agree"),
        learning.TWO_PRESCRIPTIONS: judged(order, ordered(), "agree"),
        # (no identifying entity in common; and once per the same entity)
        learning.BY_RULE: judged(
            a, told("Activity", carried_out_by="z", participants=("y",)), "two_events"
        ),  # fmt: skip
        learning.NOT_THE_THING: judged(
            order, told("Going", goer="john", to="market"), "two_events"
        ),  # fmt: skip
        learning.OTHER_VERDICT: judged(order, went, "agree"),
    }
    for why, j in cases.items():
        assert example(j) == why, why
    born = told("Birth", person="a")
    assert example(judged(born, told("Birth", person="a"), "agree")) == learning.BY_RULE
    assert example(judged(a, b, "carried_out")) == learning.OTHER_VERDICT
    # (done by another, or before it was prescribed: the rules settle these before any likelihood is asked)
    assert example(judged(order, going(goer="peter"), "two_events")) == learning.BY_RULE
    assert example(judged(going(when=test_compare_maths.day(1500, 5, 1)), order, "carried_out")) == learning.BY_RULE  # fmt: skip

    found = learning.examples(
        [*cases.values(), judged(*told_twice(), "agree", 1)], RULES
    )
    assert found.judgements == len(cases) + 1
    assert found.left_out == {**dict.fromkeys(learning.LEFT_OUT, 0), **dict.fromkeys(cases, 1)}  # fmt: skip
    assert [len(found.by_model[m]) for m in learning.MODELS] == [1, 0]
    assert set(learning.LEFT_OUT) == {*cases, learning.OLDER}


def test_only_the_newest_judgement_of_a_pair_counts_in_either_order():
    a, b = told_twice()
    older = judged(a, b, "agree", 1)
    newer = judged(b, a, "two_events", 2)
    found = learning.examples([newer, older], RULES)
    assert found.left_out[learning.OLDER] == 1
    (only,) = found.by_model[maths.ONE_EVENT]
    assert only.yes is False
    assert found.latest == newer.at
    # (one with no record of when is older than any with; of two made at once, the greater id)
    undated = Judged("j9999", "agree", (a.id, b.id), a, b, None)
    assert learning.newest([undated, older])[0] == [older]
    same = Judged("j0002", "agree", (a.id, b.id), a, b, older.at)
    assert learning.newest([same, older])[0] == [same]
    # (the newest decides, though it is left out: an older judgement does not stand in for it)
    changed = judged(a, b, "agree", 3, changed=True)
    found = learning.examples([older, changed], RULES)
    assert found.by_model[maths.ONE_EVENT] == []
    assert found.left_out[learning.CHANGED] == found.left_out[learning.OLDER] == 1


# ---------------------------------------------------------------------------
# The fits
# ---------------------------------------------------------------------------


def unlike_by_hand(count: int, seed: int = 0) -> list[Judged]:
    """Judgements of gatherings told twice, a day or more apart, that people judge two events when they are more
    than a week apart and one event otherwise (the hand-set weights are milder than that); and of orders and goings,
    a going more than a month off judged not to answer"""
    rng = random.Random(seed)
    made = []
    for n in range(count):
        if n % 2:
            days = rng.randint(0, 40)
            a = gathering(when=maths.Span(700_000, 700_000))
            b = gathering(when=maths.Span(700_000 + days, 700_000 + days))
            made.append(judged(a, b, "two_events" if days > 7 else "agree", n))
        else:
            days = rng.randint(0, 90)
            order = told("Going", ORDERED, maths.Span(700_000, 700_000), prescribed=BY_MAX, goer="john", to="shops")  # fmt: skip
            went = told("Going", when=maths.Span(700_000 + days, 700_000 + days), goer="john", to="shops")  # fmt: skip
            made.append(judged(order, went, "two_events" if days > 30 else "carried_out_otherwise", n))  # fmt: skip
    return made


def test_both_models_are_fitted_and_compared_with_the_hand_set_score():
    found = learning.examples(unlike_by_hand(200), RULES)
    fits = learning.fit_both(found, fitted_at="then")
    for model in learning.MODELS:
        fitted = fits.of(model)
        assert fitted.model is not None and fitted.compared is not None, fitted
        assert fitted.examples == 100 == fitted.compared.decisions
        assert fitted.model.features == learning.features_of(model)
        assert fitted.model.fitted_at == "then"
        # (the hand-set score called on the same held-out judgements: likelihood of a half or more is yes)
        by_hand = sum((learning.by_hand_likelihood(e.features) >= 0.5) == e.yes for e in found.by_model[model])  # fmt: skip
        assert fitted.compared.baseline == by_hand
        assert fitted.passes(0) and fitted.compared.model > fitted.compared.baseline
        assert 0 < fitted.compared.differ <= fitted.compared.decisions


def test_a_model_that_cannot_be_fitted_is_none_with_why_and_the_other_stands():
    found = learning.examples([j for j in unlike_by_hand(200) if j.a and j.a.type == "Activity"], RULES)  # fmt: skip
    fits = learning.fit_both(found)
    assert fits.one_event.model is not None
    assert fits.answers.model is None and fits.answers.examples == 0
    assert fits.answers.why == "0 examples are too few to fit 4 features: at least 6 are needed"  # fmt: skip
    assert not fits.answers.passes(1.0)


def x_and_y(xs: int, ys: int, x_says: str, y_says: str) -> list[Judged]:
    """Gatherings by one host told twice: `xs` with no guests named (the hand-set likelihood 0.55: one event), `ys`
    with guests that are partly the same (0.43: two)"""
    made = []
    for n in range(xs):
        made.append(judged(*(told("Activity", carried_out_by="ada", participants=()) for _ in "ab"), x_says, n))  # fmt: skip
    for n in range(ys):
        a = told("Activity", carried_out_by="ada", participants=("ben", "cy"))
        b = told("Activity", carried_out_by="ada", participants=("ben", "dee"))
        made.append(judged(a, b, y_says, xs + n))
    return made


def test_a_fit_worse_than_the_hand_set_score_on_judgements_held_out_says_so():
    """The hand-set score calls every one of these judgements rightly; a fit of eighteen of one kind and two of the
    other, by the ridge, calls the two as the eighteen when they are held out: worse by two, of two called
    differently, more than chance allows at a margin of 1 (√2) and less than at 2"""
    fits = learning.fit_both(learning.examples(x_and_y(18, 2, "agree", "two_events"), RULES))  # fmt: skip
    assert fits.one_event.compared == learning.CallsCompared(decisions=20, model=18, baseline=20, differ=2)  # fmt: skip
    assert not fits.one_event.passes(0) and not fits.one_event.passes(1.0)
    assert fits.one_event.passes(2.0)


def test_the_folds_share_each_answer_so_a_rare_two_events_is_in_every_part_fitted_on():
    """Two "two events" among forty judgements: dealt as they come, a part fitted on could have none and the model
    could not be compared; dealt by the answer, each is in a fold of its own, and every part has the other"""
    from pangloss_learn import compare_calls

    found = learning.examples(x_and_y(38, 2, "agree", "two_events"), RULES)
    fitted = learning.fit_both(found).one_event
    assert fitted.compared is not None, fitted.compared_why
    examples = found.by_model[maths.ONE_EVENT]
    refused = 0
    for seed in range(10):
        try:
            compare_calls(examples, learning.ONE_EVENT_FEATURES, seed=seed, baseline=learning.by_hand_likelihood)  # fmt: skip
        except learning.Unfittable:
            refused += 1
    assert refused > 0
    # (one answer only: no model, and why)
    alone = learning.fit_both(learning.examples(x_and_y(20, 0, "agree", "agree"), RULES)).one_event  # fmt: skip
    assert alone.model is None and alone.why == "All 20 examples are yes: a model needs some of each"  # fmt: skip
    # (one of the other answer: fitted, but a part fitted on has none of it, so not compared)
    one = learning.fit_both(learning.examples(x_and_y(19, 1, "agree", "two_events"), RULES)).one_event  # fmt: skip
    assert one.model is not None and one.compared is None
    assert "a model needs some of each" in (one.compared_why or "")


def test_the_same_judgements_in_any_order_give_the_same_models_and_comparison():
    made = unlike_by_hand(120, seed=3)
    shuffled = made[:]
    random.Random(1).shuffle(shuffled)
    one, other = (learning.fit_both(learning.examples(m, RULES)) for m in (made, shuffled))  # fmt: skip
    for model in learning.MODELS:
        assert one.of(model).model is not None
        assert one.of(model).model.to_json() == other.of(model).model.to_json()
        assert one.of(model).compared == other.of(model).compared


def test_a_fit_is_what_the_verdict_takes_and_gives_the_model_s_likelihood():
    fits = learning.fit_both(learning.examples(unlike_by_hand(200), RULES))
    one, answers = fits.one_event.model, fits.answers.model
    assert one is not None and answers is not None
    fitted = {maths.ONE_EVENT: learning.as_fitted(one), maths.ANSWERS_IT: learning.as_fitted(answers)}  # fmt: skip
    assert set(fitted[maths.ONE_EVENT]) == {*learning.ONE_EVENT_FEATURES, "bias"}
    for a, b in [
        (
            gathering(when=maths.Span(700_000, 700_000)),
            gathering(when=maths.Span(700_003, 700_003)),
        ),  # fmt: skip
        (
            ordered(),
            going(when=maths.Span(BY_MAX.at.latest + 50, BY_MAX.at.latest + 50)),
        ),  # fmt: skip
    ]:
        model, found = example(judged(a, b, "two_events"))
        expected = (one if model == maths.ONE_EVENT else answers).score(found.features)
        assert verdict(a, b, RULES, fitted=fitted).likelihood == pytest.approx(expected)
    # (a gathering ten days apart is two events by the fit, one told otherwise by hand)
    a, b = gathering(when=maths.Span(700_000, 700_000)), gathering(when=maths.Span(700_010, 700_010))  # fmt: skip
    assert verdict(a, b, RULES).relation == "disagree"
    assert verdict(a, b, RULES, fitted=fitted).relation == "two"


def test_the_signature_changes_with_the_features_the_hand_set_weights_and_the_rules(monkeypatch):  # fmt: skip
    today = learning.signature(RULES)
    assert learning.signature(dict(reversed(list(RULES.items())))) == today
    changed = {**RULES, "Activity": maths.Rules(("carried_out_by",))}
    assert learning.signature(changed) != today
    assert learning.signature({k: v for k, v in RULES.items() if k != "Rule"}) != today
    monkeypatch.setitem(maths.WEIGHTS, "recurs", -1.1)
    assert learning.signature(RULES) != today
    monkeypatch.undo()
    monkeypatch.setitem(maths.ANSWER_WEIGHTS, "bias", 2.0)
    assert learning.signature(RULES) != today
    monkeypatch.undo()
    monkeypatch.setattr(learning, "ANSWER_FEATURES", ("missed_by", maths.BY_HAND))
    assert learning.signature(RULES) != today


# ---------------------------------------------------------------------------
# The planted world
# ---------------------------------------------------------------------------


def judged_world(world) -> list[tuple[Judged, object]]:
    """Each pair by rule of the world that the logistic decides, judged as the truth has it, and its example"""
    statements, event_of = statements_of(world)
    truth = {frozenset((v.a, v.b)): v for v in world.verdicts}
    found = []
    for a, b in pairs_by_rule(statements):
        said_so = truth.get(frozenset((a.id, b.id)))
        one = said_so.relation != "two" if said_so else event_of[a.id] == event_of[b.id]
        j = Judged(f"{a.id}|{b.id}", "agree" if one else "two_events", (a.id, b.id), a, b)  # fmt: skip
        made = example(j)
        if not isinstance(made, str) and made[0] == maths.ONE_EVENT:
            found.append((j, made[1]))
    return found


def mistakes(model, held) -> int:
    weights = learning.as_fitted(model)
    return sum((maths.logistic({**e.features, "bias": 1.0}, weights) >= 0.5) != e.yes for _, e in held)  # fmt: skip


@pytest.mark.usefixtures("models")
def test_a_fit_of_judgements_of_what_is_shown_corrects_the_hand_set_score_on_the_planted_world():
    """Measured 2026-11-27 at 2,000 people: of 31,459 pairs of seed 2 the logistic decides, 67 mistakes by hand;
    fitted on 100 judgements of seed 1 drawn from the 1,655 the hand-set likelihood puts at 0.2 or more (those shown),
    23 to 40 over five draws (31 in this one), on 400, 23 to 26 (23); a fit of the same judgements without the
    hand-set score among its features, 513 to 8,222 (7,482 and 7,317 in these): it knows nothing of the pairs not
    shown, and calls them one event. (At 5,000 people, the plan's "6.6, measured before its brief": 150 by hand,
    about 40 fitted.) Over twenty draws (2026-11-27): 23 to 64 at 100 (one above 40), 23 to 36 at 400; the draw here
    is the same whatever the hash seed (`pairs_by_rule` in one order: before, the order of a set's entities moved it,
    and with `PYTHONHASHSEED=4` it drew one of 74)"""
    from pangloss_learn import fit
    from pangloss_testing import planted

    judgements = judged_world(planted.world(seed=1, people=2000, compared=True))
    held = judged_world(planted.world(seed=2, people=2000, compared=True))
    shown = [(j, e) for j, e in judgements if learning.by_hand_likelihood(e.features) >= 0.2]  # fmt: skip
    assert len(held) > 25_000 and len(shown) > 1_000
    by_hand = sum((learning.by_hand_likelihood(e.features) >= 0.5) != e.yes for _, e in held)  # fmt: skip
    assert 40 < by_hand < 100
    without = [name for name in learning.ONE_EVENT_FEATURES if name != maths.BY_HAND]
    for size, floor in [(100, 40), (400, 30)]:
        drawn = random.Random(f"{size} 0").sample(shown, size)
        found = learning.examples([j for j, _ in drawn], RULES)
        fitted = learning.fit_both(found).one_event
        assert fitted.model is not None and fitted.examples == size
        with_term = mistakes(fitted.model, held)
        assert with_term <= floor < by_hand, size
        alone = fit(found.by_model[maths.ONE_EVENT], without)
        assert mistakes(alone, held) > 50 * with_term, size
