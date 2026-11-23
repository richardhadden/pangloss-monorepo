""" "None of these" on the stored route, from the fit in use (step 11.6 of implementation_docs/similarity-build-plan.md;
implementation_docs/reconcile.md, "None of these"), on the backend under test.

On the world of the decisions' tests (review's models; two Jon Smyths in different company, Ada, Ben, Cy and Dee),
every part built, and a factoid that names a Jon Smyth not identified beside Ada and Ben. A fit is put in use by
writing a `PGReconcileModel` through 11.5's own writer (`fits.write`), today's signatures (`decisions.today`) and a
hand-made "none of these" model whose weights make the figure predictable: it weighs `best` and `rows`, so that it
is `Model.score(head_features(the rows answered))` and changes with how many were answered. What is claimed:
`model` null and no `new` without a fit in use; with one, the figure of the rows answered and `probablyNew` on each
side of `RECONCILE_NEW_ABOVE`; a fit not of today, or with no "none of these" model, said and not used; an empty list
no figure; `limit` changes the figure; the payload route unchanged; the candidates the same with and without a fit;
nothing written but 11.4's one record; what the route costs."""

import datetime
import json
import math
import uuid
from typing import Any, no_type_check

import pytest
import pytest_asyncio
from pangloss_core import backend
from pangloss_learn import Model
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, load
from pangloss_testing.live import apply_changes, run
import test_reconcile_candidates_live as candidates_live
import test_reconcile_decisions_live as decisions_live
from test_reconcile_candidates_live import ROUTE, bearer, ref, reviewed_meeting
from test_reconcile_decisions_live import (
    STORED_STATEMENTS,
    STORED_TRANSACTIONS,
    UNKNOWN,
    mentioned,
    shown_records,
    shown_to,
    world,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

# (the fixtures of the candidates' tests: the database emptied, its vector indexes dropped; a client of the app)
database = candidates_live.database
client = candidates_live.client
setting = decisions_live.setting

# (a "none of these" model of `best` and `rows` alone: lower for a better best, higher for more rows)
MODEL = Model(features=("best", "rows"), weights=(-3.0, 1.5), constant=1.0)


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def structure(database):
    """The package's migrations applied, as `pangloss migrate` would (the test database is set up without the
    structure of installed apps)"""
    for name in ["0001_initial", "0002_models"]:
        migration = load("pangloss_reconcile", name)
        await apply_changes(
            backend.current().database(), EMPTY_SNAPSHOT, list(migration.changes)
        )


async def planted(
    none: Model | None = MODEL, in_use: bool = True, **changes: Any
) -> dict[str, Any]:
    """A fit written through 11.5's writer, of today's signatures (or of `changes` to them), with `none` as its
    "none of these" model (None: not fitted) and no ranking model: its properties"""
    from pangloss_reconcile import decisions, fits
    from pangloss_vectors import store

    now = datetime.datetime.now(datetime.UTC)
    properties = {
        "id": str(uuid.uuid4()),
        "at": now,
        **decisions.today(await store.states()),
        "decisions": 120,
        "latest": now,
        "ranking": None,
        "none": none.to_json() if none is not None else None,
        "ranking_why": "not fitted here",
        "none_why": None if none is not None else "not fitted here",
        "compared": json.dumps(
            {
                "ranking": None,
                "none": {"decisions": 120, "model": 90, "baseline": 60},
            }
        ),
        "in_use": in_use,
        **changes,
    }
    await fits.write(properties)
    return properties


def the_unknown(answer: dict[str, Any]) -> dict[str, Any]:
    (unknown,) = answer["unknowns"]
    return unknown


def expected(unknown: dict[str, Any], model: Model = MODEL) -> float:
    """What the figure must be: the model's score of the head of the candidates answered, in the answer's order"""
    from pangloss_reconcile.learning import head_features

    return model.score(
        head_features(
            [
                {"score": c["score"], "scores": c["scores"], "displayed": True}
                for c in unknown["candidates"]
            ]
        )
    )


def no_figure(unknown: dict[str, Any]) -> bool:
    """Neither key there (not null, not 0)"""
    return "new" not in unknown and "probablyNew" not in unknown


async def asked_about(
    database, client
) -> tuple[Any, dict[str, str], dict[str, str], str]:
    """The world built, root logged in, the mention stored: the models, the ids, the headers, the mention"""
    m, ids = await world(database)
    headers = await bearer(client)
    (mention,) = await mentioned(database, m, ids)
    return m, ids, headers, mention


# ---------------------------------------------------------------------------
# With no fit, and with one
# ---------------------------------------------------------------------------


@no_type_check
async def test_with_no_fit_in_use_the_model_is_null_and_no_unknown_has_a_figure(
    database, client
):
    _, ids, headers, mention = await asked_about(database, client)

    answer = await shown_to(client, headers, mention, limit=5)
    assert answer["model"] is None
    assert the_unknown(answer)["candidates"][0]["id"] == ids["jon"]
    assert no_figure(the_unknown(answer))

    # (a fit written and not in use is none in use)
    await planted(in_use=False)
    answer = await shown_to(client, headers, mention, limit=5)
    assert answer["model"] is None
    assert no_figure(the_unknown(answer))


@no_type_check
async def test_a_fit_of_today_in_use_gives_the_figure_of_the_rows_answered_and_probably_new_by_the_setting(
    database, client, setting
):
    _, _, headers, mention = await asked_about(database, client)
    fit = await planted()

    answer = await shown_to(client, headers, mention, limit=5)

    model = answer["model"]
    assert model == {
        "id": fit["id"],
        "at": model["at"],
        "decisions": 120,
        "used": True,
    }
    assert datetime.datetime.fromisoformat(model["at"]) == pytest.approx(
        fit["at"], abs=datetime.timedelta(milliseconds=1)
    )
    unknown = the_unknown(answer)
    assert len(unknown["candidates"]) > 1
    assert unknown["new"] == pytest.approx(expected(unknown), abs=1e-9)
    assert 0 < unknown["new"] < 1
    # (by hand: the best one's score and how many were answered)
    best = unknown["candidates"][0]["score"]
    rows = math.log1p(len(unknown["candidates"]))
    assert unknown["new"] == pytest.approx(
        1 / (1 + math.exp(-(1.0 - 3.0 * best + 1.5 * rows))), abs=1e-9
    )
    assert unknown["probablyNew"] is (unknown["new"] > 0.5)

    # (each side of the setting)
    setting("RECONCILE_NEW_ABOVE", unknown["new"] - 0.01)
    assert (
        the_unknown(await shown_to(client, headers, mention, limit=5))["probablyNew"]
        is True
    )
    setting("RECONCILE_NEW_ABOVE", unknown["new"] + 0.01)
    again = the_unknown(await shown_to(client, headers, mention, limit=5))
    assert again["probablyNew"] is False
    assert again["new"] == pytest.approx(unknown["new"], abs=1e-9)
    # (the figure itself: "above", so equal is not)
    setting("RECONCILE_NEW_ABOVE", again["new"])
    assert (
        the_unknown(await shown_to(client, headers, mention, limit=5))["probablyNew"]
        is False
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"signature": "another signature"},
        {"parts": json.dumps({"graph": "another", "name": "another"})},
        {"weights": json.dumps({"graph": 0.5, "name": 1.0, "shared": 1.5})},
        {"features": 2},
        {"least": 0.5},
    ],
    ids=[
        "another signature",
        "other parts",
        "other weights",
        "another features",
        "another least score",
    ],
)
@no_type_check
async def test_a_fit_in_use_not_of_today_is_said_and_not_used(
    database, client, changes
):
    _, ids, headers, mention = await asked_about(database, client)
    fit = await planted(**changes)

    answer = await shown_to(client, headers, mention, limit=5)

    assert answer["model"]["id"] == fit["id"]
    assert answer["model"]["used"] is False
    assert the_unknown(answer)["candidates"][0]["id"] == ids["jon"]
    assert no_figure(the_unknown(answer))


@no_type_check
async def test_a_fit_in_use_with_no_none_of_these_model_is_said_and_not_used(
    database, client
):
    _, _, headers, mention = await asked_about(database, client)
    fit = await planted(none=None)

    answer = await shown_to(client, headers, mention, limit=5)

    assert answer["model"] == {**answer["model"], "id": fit["id"], "used": False}
    assert no_figure(the_unknown(answer))


@no_type_check
async def test_of_two_fits_marked_in_use_the_newest_is_the_one(database, client):
    _, _, headers, mention = await asked_about(database, client)
    older = await planted(
        at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    )
    newer = await planted()
    # (two runs at the same instant could each leave one marked: put the first back as the writer unmarked it)
    run(
        database,
        "MATCH (m:PGReconcileModel {id: $id}) SET m.in_use = true",
        id=older["id"],
    )

    answer = await shown_to(client, headers, mention, limit=5)

    assert answer["model"]["id"] == newer["id"]


@no_type_check
async def test_an_empty_list_has_no_figure(database, client, setting):
    _, _, headers, mention = await asked_about(database, client)
    # (no candidate scores so much: the list is empty; the fit is of that least score, so of today)
    setting("RECONCILE_LEAST_SCORE", 0.99)
    await planted()

    answer = await shown_to(client, headers, mention, limit=5)

    assert answer["model"]["used"] is True
    unknown = the_unknown(answer)
    assert unknown["candidates"] == []
    assert no_figure(unknown)


@no_type_check
async def test_the_limit_changes_the_rows_and_so_the_figure(database, client):
    _, ids, headers, mention = await asked_about(database, client)
    await planted()

    one = the_unknown(await shown_to(client, headers, mention, limit=1))
    five = the_unknown(await shown_to(client, headers, mention, limit=5))

    assert [c["id"] for c in one["candidates"]] == [ids["jon"]]
    assert len(five["candidates"]) > 1
    assert one["new"] == pytest.approx(expected(one), abs=1e-9)
    assert five["new"] == pytest.approx(expected(five), abs=1e-9)
    assert one["new"] != pytest.approx(five["new"], abs=1e-6)


# ---------------------------------------------------------------------------
# What does not change
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_payload_route_is_unchanged_with_a_fit_in_use(database, client):
    _, ids, headers, _ = await asked_about(database, client)
    await planted()
    body = {
        "type": "Factoid",
        "label": "Ann met Ben and Jon",
        "statements": [reviewed_meeting(ref(ids["Ada"]), [ref(ids["Ben"]), UNKNOWN])],
    }

    response = await client.post(f"{ROUTE}?limit=5", json=body, headers=headers)

    assert response.status_code == 200, response.text
    answer = response.json()
    assert set(answer) == {"status", "profile", "unknowns"}
    unknown = the_unknown(answer)
    assert unknown["candidates"][0]["id"] == ids["jon"]
    assert no_figure(unknown)


@no_type_check
async def test_the_candidates_are_the_same_with_and_without_a_fit_in_use(
    database, client
):
    """(the ranking stays hand-set, and what a reader may see is the views': the fit changes neither)"""
    _, _, headers, mention = await asked_about(database, client)
    without = the_unknown(await shown_to(client, headers, mention, limit=5))
    await planted()
    with_fit = the_unknown(await shown_to(client, headers, mention, limit=5))

    assert "new" in with_fit
    assert with_fit["candidates"] == without["candidates"]
    assert {k: v for k, v in with_fit.items() if k not in ("new", "probablyNew")} == (
        without
    )


@no_type_check
async def test_nothing_is_written_but_what_was_offered_and_it_holds_no_figure(
    database, client
):
    _, _, headers, mention = await asked_about(database, client)
    await planted()
    # (the counts once the workers have done with the writes so far)
    nodes, edges, marks = await candidates_live.settled(database)

    answer = await shown_to(client, headers, mention, limit=5)
    assert "new" in the_unknown(answer)
    assert candidates_live.counts(database) == (nodes + 1, edges, marks)
    await shown_to(client, headers, mention, limit=5)
    assert candidates_live.counts(database) == (nodes + 1, edges, marks)

    (record,) = shown_records(database)
    assert record["stand_in"] == mention
    (properties,) = decisions_live.every_property(database, "PGReconcileShown")
    assert "new" not in properties and "probablyNew" not in properties
    for row in json.loads(record["rows"]):
        assert set(row) == {"id", "type", "scores", "shared", "score", "displayed"}


# ---------------------------------------------------------------------------
# What the stored route costs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fit", [True, False], ids=["a fit in use", "no fit"])
@no_type_check
async def test_reading_the_fit_in_use_is_one_read_transaction_of_one_statement(
    database, client, fit
):
    """(the budget of `test_reconcile_decisions_live.py`, which holds the read: 15 transactions and 49 statements
    before step 11.6 with nothing kept, 16 and 50 since; the same with a fit in use as with none)"""
    from pangloss_testing.conformance.test_query_costs import recorded

    _, _, headers, mention = await asked_about(database, client)
    if fit:
        await planted()
    # (once before, so that what is read once for a process is read)
    await shown_to(client, headers, mention, limit=5)

    with recorded() as found:
        answer = await shown_to(client, headers, mention, limit=5)

    assert ("new" in the_unknown(answer)) is fit
    # (and what was offered kept: one write transaction of two statements)
    assert (found.transactions, len(found.statements)) == (
        STORED_TRANSACTIONS + 1,
        STORED_STATEMENTS + 2,
    )
