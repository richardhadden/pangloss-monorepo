"""Retraining (`fits.py`; step 11.5 of implementation_docs/similarity-build-plan.md), on the backend under test.

The examples are written directly, through `decisions.write_example` (the writer the listener uses), of made-up rows
(`made`: a seeded generator in which the row taken has the best name, and the lists where none of those offered was
taken have a low best score, so that both models can be fitted and are no worse than what they would replace), with
today's signatures (`decisions.today`, of vector states written by the test: `TODAY`). No model is declared and no
vector is built: what is fitted is only what the examples hold. What is claimed: no examples; too few; enough (in
use, and only one); nothing new; more, and a second fit in use; a worse one kept out of use; examples of other
signatures, weights and features left out and counted, and those lacking a part; `use` of an earlier fit, of one of
other signatures, of none; a dry run; a "none of these" model that cannot be fitted; the admin job."""

import datetime
import json
import random
from typing import Any, no_type_check

import pangloss_core.settings as core_settings
import pytest
import pytest_asyncio
from pangloss_admin.kinds import job_kinds
from pangloss_admin.runner import run_job
from pangloss_admin.store import JobStore
from pangloss_core import backend
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, load
from pangloss_reconcile import decisions, fits, settings
from pangloss_reconcile import score as scoring
from pangloss_testing.live import apply_changes, run

pytestmark = pytest.mark.asyncio(loop_scope="session")

# (the states of the vectors in use the examples are of: their signatures are what `decisions.today` reads)
TODAY = """
CREATE (:PGVectorState {part: 'name', generation: 1, count: 0, stale: 0, signature: 'name-1', graph_sees: ''}),
    (:PGVectorState {part: 'graph', generation: 1, count: 0, stale: 0, signature: 'graph-1', graph_sees: ''}),
    (:PGVectorProfile {profile: 'who', generation: 1, signature: 'who-1', dimension: 2, count: 0, weights: '{}'})
"""

LEARN_FROM = 40
START = datetime.datetime(2026, 11, 1, tzinfo=datetime.UTC)


@pytest.fixture
def learnable(db_driver, clear_database, monkeypatch):
    """An empty database with today's vector states, and a fit put in use from `LEARN_FROM` decisions"""
    from pangloss_vectors import import_installed_apps

    import_installed_apps()
    monkeypatch.setattr(core_settings.SETTINGS, "RECONCILE_LEARN_FROM", LEARN_FROM)
    run(db_driver, TODAY)
    return db_driver


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def structure(learnable):
    """The package's migrations applied, as `pangloss migrate` would (the test database is set up without the
    structure of installed apps)"""
    for name in ["0001_initial", "0002_models"]:
        migration = load("pangloss_reconcile", name)
        await apply_changes(
            backend.current().database(), EMPTY_SNAPSHOT, list(migration.changes)
        )


@no_type_check
def made(
    count: int,
    *,
    seed: int = 0,
    prefix: str = "s",
    noise: bool = False,
    by_hand: bool = False,
) -> list[dict[str, Any]]:
    """`count` made-up decisions, each `{stand_in, rows, taken}`: ten rows by the hand-set score, the first five not
    under 0.2 displayed. Six in ten are of someone offered (one row with the best name, and something shared: taken);
    the others of someone new (every name low; taken none, or one in four a row not displayed). `noise`: every list
    is of the first kind, and whether the one taken is the best or none is drawn at random (the "none of these"
    answers are drawn against the features: nothing can be learnt of them). `by_hand`: the lists of someone offered
    have every name high and the graph spread wide, and the one taken is the first by the hand-set score (right in
    every list of someone offered; a fitted ranking is not)"""
    rng = random.Random(seed)
    weights = settings.weights()
    found = []
    for n in range(count):
        stand_in = f"{prefix}{n:04d}"
        offered = noise or rng.random() < 0.6
        rows = []
        for k in range(10):
            if offered and by_hand:
                name, graph, shared = (
                    rng.uniform(0.6, 0.95),
                    rng.uniform(0.0, 1.0),
                    rng.randint(0, 4),
                )
            elif offered and k == 0:
                name, graph, shared = (
                    rng.uniform(0.85, 1.0),
                    rng.uniform(0.1, 0.3),
                    rng.randint(1, 4),
                )
            elif offered:
                name, graph, shared = (
                    rng.uniform(0.1, 0.6),
                    rng.uniform(0.0, 0.3),
                    rng.randint(0, 1),
                )
            else:
                name, graph, shared = (
                    rng.uniform(0.1, 0.45),
                    rng.uniform(0.0, 0.3),
                    rng.randint(0, 1),
                )
            scores = scoring.with_shared(
                {"graph": graph, "name": name}, shared, weights
            )
            rows.append(
                {
                    "id": f"{stand_in}-{k}",
                    "type": "Person",
                    "scores": scores,
                    "shared": shared,
                    "score": scoring.score(scores, weights),
                }
            )
        rows.sort(key=lambda row: (-row["score"], row["id"]))
        shown = [row for row in rows if row["score"] >= settings.least_score()][:5]
        for row in rows:
            row["displayed"] = row in shown
        if by_hand and offered:
            taken = rows[0]["id"]
        elif noise:
            taken = rows[0]["id"] if rng.random() < 0.5 else None
        elif offered:
            taken = max(rows, key=lambda row: row["scores"]["name"])["id"]
        else:
            taken = rows[-1]["id"] if rng.random() < 0.25 else None
        found.append({"stand_in": stand_in, "rows": rows, "taken": taken})
    return found


@no_type_check
async def kept(made_decisions, *, since: datetime.datetime = START, **other) -> None:
    """The decisions written as examples, through the listener's writer, with today's signatures (or `other`
    values of them), one second apart from `since`"""
    from pangloss_vectors import store

    record = {**decisions.today(await store.states()), **other}
    database = backend.current().database()

    @database.write_transaction
    async def write(tx):
        for n, decision in enumerate(made_decisions):
            await decisions.write_example(
                tx,
                decision["stand_in"],
                since + datetime.timedelta(seconds=n),
                {**record, "rows": json.dumps(decision["rows"])},
                decision["taken"],
            )

    await write()


def undisplayed(made_decisions) -> int:
    """How many of the decisions have no row displayed (no "none of these" example)"""
    return sum(not any(row["displayed"] for row in d["rows"]) for d in made_decisions)


def written(db_driver) -> list[dict]:
    return run(
        db_driver,
        f"MATCH (m:{fits.MODEL}) RETURN m.id AS id, m.in_use AS in_use, m.decisions AS decisions, "
        "m.ranking AS ranking, m.none AS none, m.ranking_why AS ranking_why, m.none_why AS none_why, "
        "m.compared AS compared, m.profile AS profile, m.signature AS signature, m.parts AS parts, "
        "m.weights AS weights, m.features AS features, m.least AS least ORDER BY m.at",
    )


def in_use(db_driver) -> list[str]:
    return [found["id"] for found in written(db_driver) if found["in_use"]]


# ---------------------------------------------------------------------------
# A fit, and when there is none
# ---------------------------------------------------------------------------


async def test_with_no_examples_nothing_is_fitted_or_written_and_it_says_so(learnable):
    learnt = await fits.learn()
    assert (learnt.read, learnt.decisions, learnt.id) == (0, 0, None)
    assert learnt.lines()[-1] == (
        "Nothing fitted and nothing written: there is no decision to learn from"
    )
    assert written(learnable) == []


async def test_fewer_decisions_than_learn_from_are_written_not_in_use_and_it_says_why(
    learnable,
):
    few = made(LEARN_FROM - 10)
    await kept(few)
    learnt = await fits.learn()
    assert learnt.decisions == LEARN_FROM - 10
    assert not learnt.in_use
    assert learnt.why_not == (
        f'its "none of these" model is of {LEARN_FROM - 10 - undisplayed(few)} decisions, fewer than '
        f"RECONCILE_LEARN_FROM ({LEARN_FROM})"
    )
    (fit,) = written(learnable)
    assert fit["id"] == learnt.id and fit["in_use"] is False
    assert fit["ranking"] is not None and fit["none"] is not None
    assert (
        f"Written: the fit {learnt.id}, not in use: {learnt.why_not}" in learnt.lines()
    )
    assert fits.NO_FIT in learnt.lines()


async def test_enough_decisions_make_a_fit_in_use_and_only_one(learnable):
    from pangloss_learn import Model
    from pangloss_vectors import store

    await kept(made(60))
    learnt = await fits.learn()
    assert learnt.why_not is None, learnt.lines()
    assert learnt.in_use
    (fit,) = written(learnable)
    assert fit["in_use"] is True and fit["decisions"] == 60
    now = decisions.today(await store.states())
    assert {name: fit[name] for name in decisions.SIGNATURES} == now
    ranking = Model.from_json(fit["ranking"])
    none = Model.from_json(fit["none"])
    assert ranking.features == ("graph", "name", "shared")
    assert ranking.examples == 600
    assert none.features == (
        "best",
        "gap",
        "best_graph",
        "best_name",
        "best_shared",
        "rows",
    )
    compared = json.loads(fit["compared"])
    assert compared["none"]["model"] >= compared["none"]["baseline"]
    assert learnt.undisplayed == undisplayed(made(60)) > 0
    assert compared["none"]["decisions"] == 60 - undisplayed(made(60))
    assert set(compared["ranking"]) == {"decisions", "model", "baseline"}
    assert in_use(learnable) == [learnt.id]
    lines = learnt.lines()
    assert lines[:3] == [
        "0 records of what was offered removed",
        "60 examples read",
        "60 decisions to learn from",
    ]
    assert lines[-1] == f"Written: the fit {learnt.id}, in use"
    assert any(
        line.startswith(
            "The ranking model: fitted on 600 rows; the one taken was first in"
        )
        and line.endswith(
            " by the score set by hand (recorded: nothing uses the ranking model)"
        )
        for line in lines
    )
    assert any(
        line.startswith('The "none of these" model: fitted on')
        and "by always answering the commoner" in line
        for line in lines
    )


async def test_a_second_run_with_nothing_new_writes_nothing_and_says_so(learnable):
    await kept(made(60))
    first = await fits.learn()
    again = await fits.learn()
    assert again.id is None and again.unchanged is not None
    assert again.unchanged["id"] == first.id
    assert again.lines()[-1].startswith("Nothing new since the fit of 2")
    assert again.lines()[-1].endswith(f"({first.id}): nothing written")
    assert [fit["id"] for fit in written(learnable)] == [first.id]


async def test_nothing_new_since_a_fit_not_in_use_says_how_to_put_it_in_use(learnable):
    await kept(made(LEARN_FROM - 10))
    first = await fits.learn()
    assert not first.in_use
    again = await fits.learn()
    assert again.lines()[-1].endswith(
        f"({first.id}): nothing written; it is not in use (`pangloss reconcile learn --use {first.id}` puts it "
        "in use, through the check)"
    )


async def test_more_decisions_make_a_second_fit_in_use_and_the_first_is_kept_not_in_use(
    learnable,
):
    await kept(made(60))
    first = await fits.learn()
    await kept(made(20, seed=1, prefix="t"), since=START + datetime.timedelta(days=1))
    second = await fits.learn()
    assert second.decisions == 80 and second.in_use
    assert [fit["id"] for fit in written(learnable)] == [first.id, second.id]
    assert in_use(learnable) == [second.id]


async def test_a_none_model_worse_than_the_commoner_answer_is_written_not_in_use_and_the_one_before_stays(
    learnable,
):
    await kept(made(60))
    first = await fits.learn()
    assert first.in_use
    run(learnable, "MATCH (e:PGReconcileExample) DELETE e")
    await kept(
        made(60, seed=3, prefix="n", noise=True),
        since=START + datetime.timedelta(days=1),
    )
    worse = await fits.learn()
    assert worse.none is not None and worse.none.compared is not None
    assert worse.none.compared.model < worse.none.compared.baseline, worse.lines()
    assert not worse.in_use
    assert (
        worse.why_not is not None
        and "fewer than always answering the commoner" in worse.why_not
    )
    assert in_use(learnable) == [first.id]
    assert worse.lines()[-1] == f"The fit in use stays in use: {first.id}"
    assert len(written(learnable)) == 2


async def test_examples_of_other_signatures_weights_or_features_and_those_lacking_a_part_are_left_out_and_counted(
    learnable,
):
    await kept(made(50))
    await kept(made(3, prefix="sig"), signature="who-0")
    await kept(
        made(2, prefix="part"), parts=json.dumps({"graph": "graph-0", "name": "name-1"})
    )
    await kept(
        made(2, prefix="wt"),
        weights=json.dumps({"graph": 0.5, "name": 1.0, "shared": 1.5}),
    )
    await kept(made(1, prefix="ft"), features=decisions.FEATURES + 1)
    await kept(made(1, prefix="pr"), profile="default")
    lacking = made(4, prefix="lack")
    for decision in lacking:
        for row in decision["rows"]:
            del row["scores"]["graph"]
    await kept(lacking)
    learnt = await fits.learn()
    assert (learnt.read, learnt.other, learnt.lacking, learnt.decisions) == (
        63,
        9,
        4,
        50,
    )
    lines = learnt.lines()
    assert "9 examples left out: of other vectors or weights" in lines
    assert (
        "4 examples left out: a mention had no vector of a part the features need"
        in lines
    )
    assert "50 decisions to learn from" in lines
    assert written(learnable)[0]["decisions"] == 50


# ---------------------------------------------------------------------------
# --use
# ---------------------------------------------------------------------------


async def test_use_puts_an_earlier_fit_in_use_through_the_check(learnable):
    await kept(made(60))
    first = await fits.learn()
    await kept(made(20, seed=1, prefix="t"), since=START + datetime.timedelta(days=1))
    second = await fits.learn()
    assert in_use(learnable) == [second.id]
    found = await fits.use(first.id)
    assert found is not None and found["id"] == first.id
    assert in_use(learnable) == [first.id]


async def test_use_of_a_fit_that_fails_the_check_is_refused_and_nothing_changes(
    learnable,
):
    await kept(made(60))
    good = await fits.learn()
    await kept(made(5, seed=2, prefix="few"), since=START + datetime.timedelta(days=1))
    run(
        learnable,
        "MATCH (e:PGReconcileExample) WHERE e.stand_in STARTS WITH 's' DELETE e",
    )
    few = await fits.learn()
    assert not few.in_use
    with pytest.raises(
        fits.Refused,
        match=rf'The fit {few.id} cannot be put in use: its "none of these" model is of 0 decisions, fewer than '
        rf"RECONCILE_LEARN_FROM \({LEARN_FROM}\)",
    ):
        await fits.use(few.id)
    assert in_use(learnable) == [good.id]
    with pytest.raises(fits.Refused, match="There is no fit nope"):
        await fits.use("nope")


async def test_use_of_a_fit_of_other_signatures_than_today_s_is_refused(learnable):
    await kept(made(60))
    first = await fits.learn()
    await fits.use(None)
    # (the name part built again since: its vectors are not those the fit's examples were scored with)
    run(learnable, "MATCH (s:PGVectorState {part: 'name'}) SET s.signature = 'name-2'")
    with pytest.raises(
        fits.Refused,
        match=rf"The fit {first.id} is of other vectors or weights than today's",
    ):
        await fits.use(first.id)
    assert in_use(learnable) == []


async def test_use_none_leaves_no_fit_in_use(learnable):
    await kept(made(60))
    await fits.learn()
    assert len(in_use(learnable)) == 1
    assert await fits.use(None) is None
    assert in_use(learnable) == []
    assert len(written(learnable)) == 1


# ---------------------------------------------------------------------------
# A dry run; what cannot be fitted
# ---------------------------------------------------------------------------


async def test_a_dry_run_writes_nothing_and_removes_nothing(learnable):
    run(
        learnable,
        "CREATE (:PGReconcileShown {stand_in: 'old', user: 'ann', at: $at})",
        at=datetime.datetime(2000, 1, 1, tzinfo=datetime.UTC),
    )
    await kept(made(60))
    learnt = await fits.learn(dry_run=True)
    assert learnt.swept == 1 and learnt.id is None and not learnt.in_use
    assert (
        learnt.lines()[0] == "1 record of what was offered would be removed (a dry run)"
    )
    assert (
        learnt.lines()[-1] == "Nothing written (a dry run): the fit would be put in use"
    )
    assert written(learnable) == []
    assert run(learnable, "MATCH (s:PGReconcileShown) RETURN count(s) AS n") == [
        {"n": 1}
    ]
    assert run(learnable, "MATCH (e:PGReconcileExample) RETURN count(e) AS n") == [
        {"n": 60}
    ]


async def test_when_every_decision_took_one_displayed_the_none_model_is_null_with_why_and_not_in_use(
    learnable,
):
    every = [
        d
        for d in made(120)
        if d["taken"]
        and any(r["displayed"] and r["id"] == d["taken"] for r in d["rows"])
    ]
    await kept(every[:50])
    learnt = await fits.learn()
    (fit,) = written(learnable)
    assert (
        fit["none"] is None
        and fit["none_why"] == "All 50 examples are no: a model needs some of each"
    )
    assert fit["ranking"] is not None
    assert not fit["in_use"]
    assert learnt.why_not == (
        'its "none of these" model could not be fitted (All 50 examples are no: a model needs some of each)'
    )


async def test_when_no_decision_took_one_offered_neither_model_is_fitted_and_none_is_in_use(
    learnable,
):
    nobody = [d for d in made(300) if d["taken"] is None]
    await kept(nobody[:45])
    learnt = await fits.learn()
    (fit,) = written(learnable)
    # (a list of someone new may have no row displayed, all under the least score: no "none of these" example)
    assert learnt.undisplayed > 0
    assert fit["none"] is None
    assert fit["none_why"].startswith(f"All {45 - learnt.undisplayed} examples are yes")
    assert fit["ranking"] is None and fit["ranking_why"].startswith(
        "All 450 examples are no"
    )
    assert json.loads(fit["compared"]) == {"none": None, "ranking": None}
    assert not fit["in_use"] and not learnt.in_use
    assert any(
        line.startswith("The ranking model: not fitted (All 450 examples are no")
        for line in learnt.lines()
    )


# ---------------------------------------------------------------------------
# The admin job
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_admin_job_learns_with_its_counts_and_its_report(learnable, tmp_path):
    kinds = job_kinds(["pangloss_reconcile"])
    assert list(kinds) == ["reconcile_learn", "reconcile_suggest"]
    assert kinds["reconcile_learn"].checked_options({}) == {"dry_run": "no"}
    with pytest.raises(ValueError, match="dry_run must be one of no, yes"):
        kinds["reconcile_learn"].checked_options({"dry_run": "maybe"})
    await kept(made(60))

    jobs = JobStore(tmp_path / "jobs")
    job = jobs.create("reconcile_learn", {"dry_run": "yes"}, "me")
    await run_job(jobs, job["id"], kinds)
    done = jobs.read(job["id"])
    assert done is not None and done["state"] == "finished", done["error"]
    assert done["counts"] == {
        "swept": 0,
        "read": 60,
        "other": 0,
        "lacking": 0,
        "suggestions_left_out": 0,
        "decisions": 60,
        "suggested": 0,
        "undisplayed": undisplayed(made(60)),
    }
    assert [f["name"] for f in done["files"]] == ["learnt.txt"]
    report = (jobs.files(job["id"]) / "learnt.txt").read_text().splitlines()
    assert report[-1] == "Nothing written (a dry run): the fit would be put in use"
    assert written(learnable) == []

    job = jobs.create("reconcile_learn", {"dry_run": "no"}, "me")
    await run_job(jobs, job["id"], kinds)
    assert jobs.read(job["id"])["state"] == "finished"
    assert len(in_use(learnable)) == 1


# ---------------------------------------------------------------------------
# The mends of the second reading
# ---------------------------------------------------------------------------


async def test_the_threshold_counts_the_decisions_of_the_none_model_not_every_decision(
    learnable, monkeypatch
):
    """80 decisions, of which 20 had nothing displayed: the "none of these" model is of 60 minus those of the 60
    with nothing displayed, and a threshold between the two counts keeps the fit out of use, for `learn` and `use`"""
    some = made(60)
    hidden = made(20, seed=5, prefix="h")
    for decision in hidden:
        for row in decision["rows"]:
            row["displayed"] = False
    await kept(some + hidden)
    of_none = 60 - undisplayed(some)
    monkeypatch.setattr(core_settings.SETTINGS, "RECONCILE_LEARN_FROM", of_none + 1)
    learnt = await fits.learn()
    assert learnt.decisions == 80 and learnt.undisplayed == 80 - of_none
    assert learnt.why_not == (
        f'its "none of these" model is of {of_none} decisions, fewer than RECONCILE_LEARN_FROM ({of_none + 1})'
    )
    assert not learnt.in_use
    with pytest.raises(fits.Refused, match=f"is of {of_none} decisions, fewer than"):
        await fits.use(learnt.id)
    monkeypatch.setattr(core_settings.SETTINGS, "RECONCILE_LEARN_FROM", of_none)
    found = await fits.use(learnt.id)
    assert found is not None and found["id"] == learnt.id
    assert in_use(learnable) == [learnt.id]


async def test_examples_of_another_least_score_are_left_out_and_a_fit_of_one_is_refused(
    learnable, monkeypatch
):
    await kept(made(60))
    await kept(made(3, prefix="least"), least=0.5)
    learnt = await fits.learn()
    assert (learnt.read, learnt.other, learnt.decisions) == (63, 3, 60)
    assert learnt.in_use
    await fits.use(None)
    monkeypatch.setattr(core_settings.SETTINGS, "RECONCILE_LEAST_SCORE", 0.3)
    with pytest.raises(
        fits.Refused, match="is of other vectors or weights than today's"
    ):
        await fits.use(learnt.id)
    assert in_use(learnable) == []


async def test_use_of_a_fit_whose_comparison_could_not_be_made_is_refused_with_why(
    learnable, monkeypatch
):
    """Nine decisions that took one displayed and one that took none: the "none of these" model is fitted (some of
    each), but the fold that holds the one "yes" leaves the others all "no", and it cannot be compared"""
    every = made(200)
    took = [
        d
        for d in every
        if d["taken"]
        and any(r["displayed"] and r["id"] == d["taken"] for r in d["rows"])
    ][:9]
    nobody = [
        d
        for d in every
        if d["taken"] is None and any(r["displayed"] for r in d["rows"])
    ][:1]
    await kept(took + nobody)
    monkeypatch.setattr(core_settings.SETTINGS, "RECONCILE_LEARN_FROM", 1)
    learnt = await fits.learn()
    (fit,) = written(learnable)
    assert fit["none"] is not None and json.loads(fit["compared"])["none"] is None
    assert fit["none_why"] == "All 8 examples are no: a model needs some of each"
    assert not learnt.in_use
    with pytest.raises(fits.Refused) as refused:
        await fits.use(fit["id"])
    assert str(refused.value) == (
        f'The fit {fit["id"]} cannot be put in use: its "none of these" model could not be compared '
        "(All 8 examples are no: a model needs some of each)"
    )


async def test_a_ranking_model_worse_than_the_hand_set_score_does_not_keep_the_fit_out_of_use(
    learnable,
):
    await kept(made(60, by_hand=True, prefix="b"))
    learnt = await fits.learn()
    ranking = learnt.ranking
    assert ranking is not None and ranking.compared is not None
    assert ranking.compared.model < ranking.compared.baseline
    assert learnt.in_use and in_use(learnable) == [learnt.id]
    line = next(
        line for line in learnt.lines() if line.startswith("The ranking model:")
    )
    assert line.endswith(
        f"first in {ranking.compared.model} of {ranking.compared.decisions} by the model, "
        f"{ranking.compared.baseline} by the score set by hand (recorded: nothing uses the ranking model)"
    )
