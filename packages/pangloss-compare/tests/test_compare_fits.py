"""What `pangloss compare learn` and `status` say and decide, the parts with no database in them
(`pangloss_compare.fits`; implementation_docs/spaces-and-comparison-plan.md, step 6.6 and the questions answered for
"6.8"): the check with the margin, a fit that would lose a model, nothing new, the route's `model` for a reader who is
not logged in, and the lines."""

import datetime
import json
from types import SimpleNamespace

import pytest
from pangloss_compare import fits, learning, maths
from pangloss_learn import CallsCompared, Model

AT = datetime.datetime(2026, 11, 27, 9, tzinfo=datetime.UTC)


@pytest.fixture(autouse=True)
def compare_settings(monkeypatch):
    """(the package's settings as a project gives them: COMPARE_LEARN_FROM at 10)"""
    import pangloss_core.settings as core_settings

    given = SimpleNamespace(INSTALLED_APPS=[], COMPARE_LEARN_FROM=10)
    monkeypatch.setattr(core_settings, "SETTINGS", given, raising=False)
    return given


def test_a_model_is_refused_only_when_worse_than_the_hand_set_score_by_more_than_chance(compare_settings):  # fmt: skip
    close = CallsCompared(decisions=100, model=95, baseline=96, differ=9)
    assert fits.why_not(100, True, None, close) is None
    assert fits.why_not(100, True, None, close, 0.0) == (
        "it called 95 of 100 judgements held out rightly, the hand-set score 96: worse by 1, more than chance "
        "allows (COMPARE_LEARN_MARGIN 0 × √9 called differently = 0.0)"
    )
    compare_settings.COMPARE_LEARN_MARGIN = 0.3
    assert "COMPARE_LEARN_MARGIN 0.3 × √9 called differently = 0.9" in (fits.why_not(100, True, None, close) or "")  # fmt: skip
    # (too few, and not fitted: each said)
    assert fits.why_not(4, False, "All 4 examples are yes", None) == (
        "it is of 4 judgements, fewer than COMPARE_LEARN_FROM (10); it could not be fitted (All 4 examples are yes)"
    )


def stored(id: str, *, one_event: bool, answers: bool, in_use: bool = True, signature: str = "today", **more) -> dict:  # fmt: skip
    model = Model(("by_hand",), (1.0,), 0.0, examples=12, yes=6).to_json()
    compared = {"decisions": 12, "model": 11, "baseline": 10, "differ": 3}
    return {
        "id": id,
        "at": AT,
        "signature": signature,
        "judgements": 30,
        "latest": AT,
        "one_event": model,
        "answers": model,
        "one_event_examples": 12,
        "answers_examples": 12,
        "one_event_why": None,
        "answers_why": None,
        "compared": json.dumps({"one_event": compared, "answers": compared}),
        "margin": 1.0,
        "one_event_used": one_event,
        "answers_used": answers,
        "in_use": in_use,
        "not_in_use": None,
        **more,
    }


def learnt_with(one_event: bool, answers: bool) -> fits.Learnt:
    learnt = fits.Learnt(dry_run=False, judgements=30)
    learnt.fits = learning.Fits(learning.Fitted(12, None), learning.Fitted(12, None))
    learnt.why_not = {maths.ONE_EVENT: None if one_event else "no", maths.ANSWERS_IT: None if answers else "no"}  # fmt: skip
    return learnt


def test_a_fit_that_would_lose_a_model_the_fit_in_use_has_is_told():
    both = stored("in use", one_event=True, answers=True)
    assert fits._would_lose(both, "today", learnt_with(True, False)) == (
        maths.ANSWERS_IT,
    )
    assert fits._would_lose(both, "today", learnt_with(True, True)) == ()
    # (one of another signature is used by nothing: nothing to lose; nor where none is in use)
    assert fits._would_lose(stored("old", one_event=True, answers=True, signature="then"), "today", learnt_with(True, False)) == ()  # fmt: skip
    assert fits._would_lose(None, "today", learnt_with(True, False)) == ()
    # (a model the fit in use has fitted but does not use is not lost)
    assert fits._would_lose(stored("in use", one_event=True, answers=False), "today", learnt_with(True, False)) == ()  # fmt: skip


def test_nothing_is_new_only_with_the_same_judgements_counts_and_examples_as_the_newest_fit():
    """The signature, how many judgements read and the newest made; and how many examples of each model and left
    out for each reason, and the examples themselves: a cited statement edited (its judgement `changed`), or two
    entities merged (a pair's judgement an example now, or another example), is something new though no judgement
    is"""
    from pangloss_learn import Example

    def examples(
        *features: float, changed: int = 0, by_rule: int = 0
    ) -> learning.Examples:
        found = learning.Examples(judgements=30, latest=AT)
        found.by_model[maths.ONE_EVENT] = [Example({"by_hand": f}, True, f"g{n}") for n, f in enumerate(features)]  # fmt: skip
        found.left_out[learning.CHANGED] = changed
        found.left_out[learning.BY_RULE] = by_rule
        return found

    before = examples(0.1, 0.2, by_rule=1)
    newest = stored(
        "newest",
        one_event=True,
        answers=False,
        in_use=False,
        one_event_examples=2,
        answers_examples=0,
        left_out=json.dumps(dict(before.left_out)),
        examples_digest=learning.digest(before),
    )
    assert fits._unchanged(newest, "today", before)
    assert not fits._unchanged(newest, "tomorrow", before)
    assert not fits._unchanged({**newest, "judgements": 31}, "today", before)
    assert not fits._unchanged({**newest, "latest": AT - datetime.timedelta(seconds=1)}, "today", before)  # fmt: skip
    assert not fits._unchanged(None, "today", before)
    # (a cited statement edited: one example now left out as changed)
    assert not fits._unchanged(newest, "today", examples(0.1, changed=1, by_rule=1))
    # (two entities merged: a pair the rules settled is an example now)
    assert not fits._unchanged(newest, "today", examples(0.1, 0.2, 0.3))
    # (a statement edited or entities merged so that an example's features change, the counts not)
    assert not fits._unchanged(newest, "today", examples(0.1, 0.25, by_rule=1))
    # (the digest: of the examples, not of their order as given)
    assert learning.digest(examples(0.1, 0.2)) == learning.digest(examples(0.1, 0.2))


def test_the_lines_say_nothing_new_and_why_a_fit_is_not_put_in_use():
    newest = stored("f1", one_event=True, answers=False, in_use=False)
    learnt = fits.Learnt(dry_run=False, judgements=30, examples={maths.ONE_EVENT: 12, maths.ANSWERS_IT: 0})  # fmt: skip
    learnt.unchanged = newest
    (said,) = [line for line in learnt.lines() if "Nothing new" in line]
    assert said.startswith("Nothing new since the fit f1 of 2026-11-27 09:00:00 UTC")
    assert said.endswith("nothing written; it is not in use (`pangloss compare learn --use f1` puts it in use, through the check)")  # fmt: skip

    lost = learnt_with(True, False)
    lost.id, lost.not_in_use, lost.kept_in_use = (
        "f2",
        "the fit in use, f0, has ...",
        "f0",
    )
    lines = lost.lines()
    assert "Written: the fit f2, not in use: the fit in use, f0, has ... (`pangloss compare learn --use f2` puts it in use)" in lines  # fmt: skip
    assert lines[-1] == "The fit in use stays in use: f0"


def test_the_route_s_model_gives_its_counts_only_to_a_reader_who_is_logged_in():
    fit = stored("f1", one_event=True, answers=False)
    fitted, said = fits.for_route(fit, "today")
    assert fitted is not None and set(fitted) == {maths.ONE_EVENT}
    assert said == {"id": "f1", "at": AT.isoformat(), "judgements": 12, "oneEvent": True, "answers": False}  # fmt: skip
    hidden, shown = fits.for_route(fit, "today", logged_in=False)
    assert hidden == fitted
    assert shown == {"id": "f1", "at": AT.isoformat(), "judgements": None, "oneEvent": None, "answers": None}  # fmt: skip
    assert fits.for_route(fit, "tomorrow", logged_in=False) == (None, None)


def test_status_says_why_each_model_is_or_is_not_used_and_why_the_newest_fit_is_not_in_use():
    fit = stored("f1", one_event=True, answers=False, answers_why=None)
    newest = stored("f2", one_event=True, answers=False, in_use=False, not_in_use="the fit in use, f1, has ...")  # fmt: skip
    lines = fits.status_lines(
        {
            "fit": fit,
            "of_today": True,
            "checked": fits._checked(fit),
            "newest": newest,
            "judgements": 30,
            "learn_from": 10,
            "margin": 1.0,
        }
    )
    assert lines[2].startswith("COMPARE_LEARN_MARGIN: 1 ")
    assert (
        'in use: the fit f1 of 2026-11-27 09:00:00 UTC, for "one event or two"' in lines
    )
    assert (
        '  "One event or two": used; of 12 judgements; of 12 held out, called rightly in 11 by the fit, 10 by the '
        "hand-set score, 3 called differently; it passes today's check"
    ) in lines
    assert any(
        line.startswith('  "Does this answer that": not used;') for line in lines
    )
    assert (
        lines[-1]
        == "the newest fit, f2 of 2026-11-27 09:00:00 UTC, is not in use: the fit in use, f1, has ..."
    )
