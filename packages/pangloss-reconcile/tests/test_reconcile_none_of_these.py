"""What decides whether the fit in use says "none of these", and what the stored route's answer gains from it (step
11.6; `fits.usable`, `api.none_of_these`), with no database"""

import datetime
import json

import pytest
from pangloss_learn import Model
from pangloss_reconcile import fits
from pangloss_reconcile.api import none_of_these
from pangloss_reconcile.decisions import SIGNATURES
from pangloss_reconcile.learning import head_features

TODAY = {
    "profile": "who",
    "signature": "abc",
    "parts": json.dumps({"graph": "g1", "name": "n1"}),
    "weights": json.dumps({"graph": 0.25, "name": 1.0, "shared": 1.5}),
    "features": 1,
    "least": 0.15,
}

MODEL = Model(features=("best", "rows"), weights=(-3.0, 1.5), constant=0.0)
AT = datetime.datetime(2026, 11, 23, 12, 30, tzinfo=datetime.UTC)


def fit(**changes) -> dict:
    return {
        "id": "f1",
        "at": AT,
        **TODAY,
        "decisions": 140,
        "none": MODEL.to_json(),
        "in_use": True,
        **changes,
    }


def candidate(id: str, score: float) -> dict:
    return {
        "id": id,
        "type": "Person",
        "label": id,
        "score": score,
        "scores": {"name": score, "graph": score / 2, "shared": 0.0},
        "shared": [],
    }


def answer(*lists: list[dict]) -> dict:
    return {
        "status": "ok",
        "profile": "who",
        "unknowns": [
            {"id": f"u{n}", "type": "Person", "label": "Jon", "candidates": candidates}
            for n, candidates in enumerate(lists)
        ],
    }


# -- fits.usable -----------------------------------------------------------------------------------------------------


def test_a_fit_of_today_with_a_none_of_these_model_is_usable():
    assert fits.usable(fit(), TODAY)


@pytest.mark.parametrize("name", SIGNATURES)
def test_a_fit_of_another_value_of_any_signature_is_not_usable(name):
    other = 2 if name == "features" else 0.5 if name == "least" else "other"
    assert not fits.usable(fit(**{name: other}), TODAY)


def test_a_fit_with_no_none_of_these_model_is_not_usable():
    assert not fits.usable(fit(none=None), TODAY)


def test_no_fit_and_a_profile_never_built_are_not_usable():
    assert not fits.usable(None, TODAY)
    assert not fits.usable(fit(signature=""), {**TODAY, "signature": ""})


# -- api.none_of_these -----------------------------------------------------------------------------------------------


def test_with_no_fit_the_model_is_null_and_nothing_else_changes():
    given = answer([candidate("a", 0.8)])
    assert none_of_these(given, None, TODAY, 0.5) == {**given, "model": None}


def test_a_fit_used_gives_each_unknown_with_candidates_its_figure_and_probably_new():
    given = answer(
        [candidate("a", 0.8), candidate("b", 0.5)], [], [candidate("c", 0.2)]
    )
    found = none_of_these(given, fit(), TODAY, 0.5)

    assert found["model"] == {
        "id": "f1",
        "at": "2026-11-23T12:30:00+00:00",
        "decisions": 140,
        "used": True,
    }
    first, empty, third = found["unknowns"]
    for unknown, original in [
        (first, given["unknowns"][0]),
        (third, given["unknowns"][2]),
    ]:
        rows = [{**c, "displayed": True} for c in original["candidates"]]
        assert unknown["new"] == pytest.approx(
            MODEL.score(head_features(rows)), abs=1e-12
        )
        assert unknown["probablyNew"] is (unknown["new"] > 0.5)
        assert {
            k: v for k, v in unknown.items() if k not in ("new", "probablyNew")
        } == original
    # (a good best: unlikely to be someone new; a poor one: likely)
    assert first["probablyNew"] is False
    assert third["probablyNew"] is True
    # (no figure of an empty list: the keys absent)
    assert empty == given["unknowns"][1]
    assert "new" not in empty and "probablyNew" not in empty


def test_probably_new_is_above_the_setting_not_at_it():
    given = answer([candidate("a", 0.8)])
    new = none_of_these(given, fit(), TODAY, 0.5)["unknowns"][0]["new"]
    assert (
        none_of_these(given, fit(), TODAY, new - 1e-6)["unknowns"][0]["probablyNew"]
        is True
    )
    assert (
        none_of_these(given, fit(), TODAY, new)["unknowns"][0]["probablyNew"] is False
    )


@pytest.mark.parametrize(
    "changes",
    [{"signature": "other"}, {"none": None}],
    ids=["not of today", "no none model"],
)
def test_a_fit_not_used_is_said_and_gives_no_figure(changes):
    given = answer([candidate("a", 0.8)])
    found = none_of_these(given, fit(**changes), TODAY, 0.5)
    assert found["model"]["used"] is False
    assert found["unknowns"] == given["unknowns"]


def test_the_figure_is_of_the_rows_in_the_answer_s_order_and_nothing_of_the_answer_is_changed():
    given = answer([candidate("a", 0.8), candidate("b", 0.79), candidate("c", 0.1)])
    copy = json.loads(json.dumps(given))
    one = none_of_these(
        answer(given["unknowns"][0]["candidates"][:1]), fit(), TODAY, 0.5
    )
    three = none_of_these(given, fit(), TODAY, 0.5)
    # (fewer rows, another figure: the model weighs how many)
    assert one["unknowns"][0]["new"] != pytest.approx(three["unknowns"][0]["new"])
    assert given == copy
