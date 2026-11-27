"""Learning from judgements (`pangloss_compare.fits`; implementation_docs/spaces-and-comparison-plan.md, step 6.6), on
the backend under test, with `similar_models.declare(compared=True)` and its `StatementJudgement`.

The judgements are of gatherings by one host told twice (`x_and_y`): an X pair names no guests (the hand-set
likelihood of one event 0.55), a Y pair names guests that are partly the same (0.43). Judged against the hand-set
score (X two events, Y one), a fit corrects it and is put in use; judged as the score has it with few Y, the fit is
worse on judgements held out and is refused. What is claimed: none; too few; a fit in use, which the route then
answers with and says so; a worse one refused; a fit of another signature not used; `use` of none and of an id; a
dry run; a judgement on a statement changed since it was cited left out and counted; the admin job; nothing new,
nothing written; the route's counts only to a reader logged in; an "answers" model in use, and a fit that would lose
it not put in use; two runs at once. The commands are `test_compare_learn_command_live.py`'s.

The orders (`orders_answered`): an order to the doer to give to the receiver on a day, and the doer's giving some
days after; judged carried out within a month and two events past it, where the hand-set score has it the answer
for half a year: a fit corrects it."""

import asyncio
import json
import math
import uuid
from typing import Any, no_type_check

import pangloss_core.settings as core_settings
import pytest
import pytest_asyncio
from pangloss_admin.kinds import job_kinds
from pangloss_admin.runner import run_job
from pangloss_admin.store import JobStore
from pangloss_compare import fits, learning, maths
from pangloss_core import backend
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, load
from pangloss_testing.live import apply_changes, run

from test_compare_pairs_live import (
    activity,
    entities,
    factoid,
    giving,
    order,
    ref,
    settled,
)
from test_compare_reading_live import day
from test_compare_route_live import bearer, client

pytestmark = pytest.mark.asyncio(loop_scope="session")

LEARN_FROM = 20


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def structure(clear_database):
    """The package's structure applied, as `pangloss migrate` would (the test database is set up without the
    structure of installed apps)"""
    migration = load("pangloss_compare", "0002_models")
    await apply_changes(
        backend.current().database(), EMPTY_SNAPSHOT, list(migration.changes)
    )


@pytest.fixture
def learn_from(monkeypatch):
    monkeypatch.setattr(core_settings.SETTINGS, "COMPARE_LEARN_FROM", LEARN_FROM)


def labelled(db_driver) -> dict[str, str]:
    """The ids of the statements by their labels"""
    return {
        r["label"]: r["id"]
        for r in run(
            db_driver,
            "MATCH (n:Activity) RETURN n.label AS label, n.id AS id",
        )
    }


@no_type_check
async def x_and_y(m, db_driver, xs: int, ys: int, x_says: str, y_says: str, fresh: bool = True):  # fmt: skip
    """`xs` X pairs and `ys` Y pairs, each judged; and (`fresh`) one X pair and one Y pair no one judged. The ids of
    the statements by label, the people's, and the judgements' in the order made"""
    ids = await entities(m)
    shapes = [("x", n, x_says) for n in range(xs)] + [("y", n, y_says) for n in range(ys)]  # fmt: skip
    if fresh:
        shapes += [("x", "fresh", None), ("y", "fresh", None)]
    for shape, n, _ in shapes:
        for side in "ab":
            label = f"{shape}{n}{side}"
            guests = () if shape == "x" else (ids["ben"], ids["cy" if side == "a" else "dee"])  # fmt: skip
            await factoid(m, f"fac {label}", activity(label, ids["ada"], *guests))
    statements = labelled(db_driver)
    made = []
    for shape, n, says in shapes:
        if says is None:
            continue
        made.append(await judge(m, statements[f"{shape}{n}a"], statements[f"{shape}{n}b"], says))  # fmt: skip
    return {**statements, **ids}, made


@no_type_check
async def judge(m, first: str, second: str, says: str) -> str:
    made = await m.StatementJudgement.Create(
        label=says,
        verdict=says,
        statement=ref(first, "Activity"),
        other=ref(second, "Activity"),
    ).save()
    return str(made.id)


def written(db_driver) -> list[dict[str, Any]]:
    return run(
        db_driver,
        f"MATCH (m:PGCompareModel) RETURN {fits.RETURNED} ORDER BY m.at",
    )


async def compared(id: str, kind: str = "Activity", logged_in: bool = True) -> dict:
    """The route's answer, to a reader logged in unless not"""
    async with client() as api:
        headers = (
            await bearer(api, f"reader{uuid.uuid4().hex[:8]}") if logged_in else {}
        )
        response = await api.get(f"/api/compare/{kind}/{id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


@no_type_check
async def orders_answered(m, db_driver, ids: dict, count: int) -> list[str]:
    """`count` orders (each to the doer, to give to the receiver in a given year on 1 May, ordered in April) and the
    doer's giving `6 n` days after the day ordered, judged `carried_out` within thirty days and `two_events` past
    them. The judgements' ids"""
    made = []
    for n in range(count):
        year = 1500 + n
        thing = {**giving(f"to give {n}", ids["doer"], ids["receiver"]), "when": day(year, 5, 1)}  # fmt: skip
        await factoid(m, f"order {n}", {**order(ids, f"the order {n}", thing), "when": day(year, 4, 1)})  # fmt: skip
        late = 6 * n
        gave = {**giving(f"gave {n}", ids["doer"], ids["receiver"]), "when": day(year, 5 + late // 30, 1 + late % 30)}  # fmt: skip
        await factoid(m, f"done {n}", gave)
    statements = {
        r["label"]: r["id"]
        for r in run(
            db_driver, "MATCH (n:Transfer) RETURN n.label AS label, n.id AS id"
        )  # fmt: skip
    }
    for n in range(count):
        says = "carried_out" if 6 * n <= 30 else "two_events"
        made.append(str((await m.StatementJudgement.Create(label=says, verdict=says, statement=ref(statements[f"to give {n}"], "Transfer"), other=ref(statements[f"gave {n}"], "Transfer")).save()).id))  # fmt: skip
    return made


def entry(answer: dict, label: str) -> dict:
    (found,) = [e for e in answer["pairs"] if e["other"]["label"] == label]
    return found


# ---------------------------------------------------------------------------
# None, too few, a fit, a worse one
# ---------------------------------------------------------------------------


@no_type_check
async def test_with_no_judgement_nothing_is_fitted_or_written_and_it_says_so(db_driver):
    from pangloss_testing.similar_models import declare

    declare(compared=True)
    learnt = await fits.learn()
    assert learnt.judgements == 0 and learnt.fits is None and learnt.id is None
    assert learnt.lines() == [
        "0 judgements read",
        "Nothing fitted and nothing written: there is no judgement to learn from",
    ]
    assert written(db_driver) == []
    assert await fits.in_use() is None


@no_type_check
async def test_too_few_judgements_make_a_fit_that_is_written_not_in_use_and_the_route_says_none(
    db_driver,
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids, _ = await x_and_y(m, db_driver, 10, 10, "two_events", "agree")
    learnt = await fits.learn()
    assert learnt.examples == {maths.ONE_EVENT: 20, maths.ANSWERS_IT: 0}
    assert not learnt.in_use
    assert learnt.why_not[maths.ONE_EVENT] == (
        "it is of 20 judgements, fewer than COMPARE_LEARN_FROM (100)"
    )
    (fit,) = written(db_driver)
    assert fit["id"] == learnt.id and fit["in_use"] is False
    assert fit["one_event_used"] is False and fit["answers_used"] is False
    assert fit["one_event_examples"] == 20 and fit["answers_examples"] == 0
    assert fit["one_event"] is not None and fit["answers"] is None
    assert fit["answers_why"].startswith("0 examples are too few to fit 4 features")
    assert json.loads(fit["compared"])["one_event"] == {"decisions": 20, "model": 20, "baseline": 0, "differ": 20}  # fmt: skip
    assert fit["margin"] == 1.0 and fit["not_in_use"] is None
    assert fit["signature"] == fits.today()
    assert learnt.lines()[-2:] == [f"Written: the fit {fit['id']}, not in use", fits.NO_FIT]  # fmt: skip

    answer = await compared(ids["xfresha"])
    assert answer["model"] is None
    assert entry(answer, "xfreshb")["relation"] == "agree"


@no_type_check
async def test_a_fit_in_use_is_what_the_route_answers_with_and_it_says_so(
    db_driver, learn_from
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids, _ = await x_and_y(m, db_driver, 10, 10, "two_events", "agree")
    before = await compared(ids["xfresha"])
    assert before["model"] is None
    assert entry(before, "xfreshb")["workedOut"]["relation"] == "agree"

    learnt = await fits.learn()
    assert learnt.in_use and learnt.used(maths.ONE_EVENT)
    assert not learnt.used(maths.ANSWERS_IT)
    (fit,) = written(db_driver)
    assert fit["in_use"] is True and fit["one_event_used"] is True
    assert fit["answers_used"] is False
    assert learnt.lines()[-1] == f'Written: the fit {fit["id"]}, in use for "one event or two"'  # fmt: skip

    after = await compared(ids["xfresha"])
    found = await fits.in_use()
    assert after["model"] == {
        "id": fit["id"],
        "at": fits._when(found["at"]).isoformat(),
        "judgements": 20,
        "oneEvent": True,
        "answers": False,
    }
    # (to a reader not logged in: which fit, and when; its counts null. The verdicts the same)
    anonymous = await compared(ids["xfresha"], logged_in=False)
    assert anonymous["model"] == {**after["model"], "judgements": None, "oneEvent": None, "answers": None}  # fmt: skip
    assert anonymous["pairs"] == after["pairs"]
    # (what no one judged is worked out with the fit: two events now)
    fresh = entry(after, "xfreshb")
    assert fresh["relation"] == fresh["workedOut"]["relation"] == "two"
    assert fresh["likelihood"] < 0.5 < entry(before, "xfreshb")["likelihood"]
    # (and guests partly the same, two events by hand, one told otherwise by the fit)
    assert entry(await compared(ids["yfresha"]), "yfreshb")["relation"] == "disagree"


@no_type_check
async def test_a_fit_worse_than_the_hand_set_score_is_written_and_refused(
    db_driver, learn_from
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    await x_and_y(m, db_driver, 18, 2, "agree", "two_events", fresh=False)
    learnt = await fits.learn()
    assert not learnt.in_use
    assert learnt.why_not[maths.ONE_EVENT] == (
        "it called 18 of 20 judgements held out rightly, the hand-set score 20: worse by 2, more than chance allows "
        "(COMPARE_LEARN_MARGIN 1 × √2 called differently = 1.4)"
    )
    (fit,) = written(db_driver)
    assert fit["in_use"] is False and fit["one_event_used"] is False
    assert await fits.in_use() is None
    with pytest.raises(fits.Refused, match="cannot be put in use"):
        await fits.use(fit["id"])
    assert written(db_driver)[0]["in_use"] is False


@no_type_check
async def test_a_second_fit_in_use_takes_the_place_of_the_first_and_a_refused_one_leaves_it(
    db_driver, learn_from
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids, _ = await x_and_y(m, db_driver, 10, 10, "two_events", "agree")
    first = await fits.learn()
    # (one judgement more: something new)
    await judge(m, ids["xfresha"], ids["xfreshb"], "two_events")
    second = await fits.learn()
    assert first.in_use and second.in_use
    assert [(f["id"], f["in_use"]) for f in written(db_driver)] == [(first.id, False), (second.id, True)]  # fmt: skip
    # (every judgement now as the hand-set score has it, the Y ones few: worse, refused, the second stays)
    for n in range(10):
        await judge(m, ids[f"x{n}a"], ids[f"x{n}b"], "agree")
    for n in range(8):
        await judge(m, ids[f"y{n}a"], ids[f"y{n}b"], "agree")
    third = await fits.learn()
    assert third.left_out[learning.OLDER] == 18 and third.unchanged is None
    assert not third.in_use and third.kept_in_use == second.id
    assert third.lines()[-1] == f"The fit in use stays in use: {second.id}"
    assert (await fits.in_use())["id"] == second.id


# ---------------------------------------------------------------------------
# Another signature; use; a dry run
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_fit_of_another_signature_is_not_used(
    db_driver, learn_from, monkeypatch
):
    from pangloss_compare import rules as rules_module
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids, _ = await x_and_y(m, db_driver, 10, 10, "two_events", "agree")
    learnt = await fits.learn()
    assert learnt.in_use
    assert (await compared(ids["xfresha"]))["model"] is not None

    # (a hand-set weight changed: the fit corrected weights that are no longer these)
    monkeypatch.setitem(maths.WEIGHTS, "recurs", -1.1)
    answer = await compared(ids["xfresha"])
    assert answer["model"] is None
    assert entry(answer, "xfreshb")["relation"] == "agree"
    with pytest.raises(fits.Refused, match="other features, hand-set weights or rules"):
        await fits.use(learnt.id)
    status = await fits.status()
    assert status["fit"]["id"] == learnt.id and status["of_today"] is False
    assert any(line.startswith("it is of other features") for line in fits.status_lines(status))  # fmt: skip
    monkeypatch.undo()
    assert (await compared(ids["xfresha"]))["model"] is not None

    # (a class's rules changed)
    known = rules_module.rules()

    def changed():
        return {**known, "Activity": maths.Rules(("carried_out_by", "participants"), recurs=True)}  # fmt: skip

    monkeypatch.setattr(rules_module, "rules", changed)
    assert (await compared(ids["xfresha"]))["model"] is None


@no_type_check
async def test_use_puts_an_earlier_fit_in_use_or_none(
    db_driver, learn_from, monkeypatch
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids, _ = await x_and_y(m, db_driver, 10, 10, "two_events", "agree")
    first = await fits.learn()
    await judge(m, ids["xfresha"], ids["xfreshb"], "two_events")
    second = await fits.learn()

    assert await fits.use(None) is None
    assert [f["in_use"] for f in written(db_driver)] == [False, False]
    assert (await compared(ids["xfresha"]))["model"] is None

    used = await fits.use(first.id)
    assert used["id"] == first.id and used["one_event_used"] is True
    assert [(f["id"], f["in_use"]) for f in written(db_driver)] == [(first.id, True), (second.id, False)]  # fmt: skip
    assert (await compared(ids["xfresha"]))["model"]["id"] == first.id
    with pytest.raises(fits.Refused, match="There is no fit nope"):
        await fits.use("nope")

    # (through today's check: with more wanted than it is of, refused, and nothing changes)
    monkeypatch.setattr(core_settings.SETTINGS, "COMPARE_LEARN_FROM", 22)
    with pytest.raises(fits.Refused, match="fewer than COMPARE_LEARN_FROM"):
        await fits.use(second.id)
    assert (await fits.in_use())["id"] == first.id


@no_type_check
async def test_a_dry_run_writes_nothing(db_driver, learn_from):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    await x_and_y(m, db_driver, 10, 10, "two_events", "agree", fresh=False)
    before = await settled(db_driver)
    learnt = await fits.learn(dry_run=True)
    assert learnt.id is None and not learnt.in_use and learnt.fits is not None
    assert learnt.lines()[-1] == (
        'Nothing written (a dry run): the fit would be put in use, for "one event or two"'
    )
    assert written(db_driver) == []
    assert await settled(db_driver) == before


# ---------------------------------------------------------------------------
# What is left out; the admin job
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_judgement_of_a_statement_changed_since_it_was_cited_is_left_out_and_counted(
    db_driver,
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids, made = await x_and_y(m, db_driver, 3, 0, "agree", "agree", fresh=False)
    (row,) = run(
        db_driver,
        "MATCH (f:Factoid {label: 'fac x0b'}) RETURN f.id AS id",
    )
    read = await m.Factoid.get(row["id"])
    data = read.model_dump(mode="json", exclude={"meta"})
    data["statements"][0]["carried_out_by"] = ref(ids["ben"])
    await m.Factoid.Update(**data).save(acknowledge_citations=True)
    # (and an older judgement of a pair judged again. One citing the same statement twice cannot be made: refused
    # when it is written, `test_compare_route_live.py`; `learning.ITSELF` is the pure tests')
    await judge(m, ids["x2b"], ids["x2a"], "two_events")

    learnt = await fits.learn()
    assert learnt.judgements == 4
    assert {why: n for why, n in learnt.left_out.items() if n} == {
        learning.CHANGED: 1,
        learning.OLDER: 1,
    }
    assert learnt.examples[maths.ONE_EVENT] == 2
    lines = learnt.lines()
    assert "1 judgement left out: a statement it cites has changed since it was cited" in lines  # fmt: skip


@no_type_check
async def test_a_deleted_judgement_is_not_read_and_one_not_published_is(db_driver):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True, reviewed=True)
    ids = await entities(m)
    for label in ("a", "b"):
        await factoid(m, f"fac {label}", activity(label, ids["ada"]), published=True)
    statements = labelled(db_driver)
    first, second = ref(statements["a"], "Activity"), ref(statements["b"], "Activity")
    gone = await m.StatementJudgement.Create(label="gone", verdict="agree", statement=first, other=second).save(published=True)  # fmt: skip
    await m.StatementJudgement.delete(gone.id)
    await m.StatementJudgement.Create(label="kept", verdict="two_events", statement=first, other=second).save(published=False)  # fmt: skip

    learnt = await fits.learn(dry_run=True)
    assert learnt.judgements == 1 and learnt.examples[maths.ONE_EVENT] == 1


@no_type_check
async def test_the_admin_job_learns_with_its_counts_and_its_report(
    db_driver, learn_from, tmp_path
):
    from pangloss_testing.similar_models import declare

    kinds = job_kinds(["pangloss_compare"])
    assert list(kinds) == ["compare_learn"]
    assert kinds["compare_learn"].checked_options({}) == {"dry_run": "no"}
    with pytest.raises(ValueError, match="dry_run must be one of no, yes"):
        kinds["compare_learn"].checked_options({"dry_run": "maybe"})
    m = declare(compared=True)
    await x_and_y(m, db_driver, 10, 10, "two_events", "agree", fresh=False)

    jobs = JobStore(tmp_path / "jobs")
    job = jobs.create("compare_learn", {"dry_run": "yes"}, "me")
    await run_job(jobs, job["id"], kinds)
    done = jobs.read(job["id"])
    assert done is not None and done["state"] == "finished", done["error"]
    assert done["counts"] == {
        "judgements": 20,
        **{f"left_out_{why}": 0 for why in learning.LEFT_OUT},
        "one_event": 20,
        "answers": 0,
    }
    assert [f["name"] for f in done["files"]] == ["learnt.txt"]
    report = (jobs.files(job["id"]) / "learnt.txt").read_text().splitlines()
    assert report[0] == "20 judgements read"
    assert report[-1].startswith("Nothing written (a dry run)")
    assert written(db_driver) == []

    job = jobs.create("compare_learn", {"dry_run": "no"}, "me")
    await run_job(jobs, job["id"], kinds)
    assert jobs.read(job["id"])["state"] == "finished"
    assert [f["in_use"] for f in written(db_driver)] == [True]


# ---------------------------------------------------------------------------
# Nothing new; "does this answer that" in use; a fit that would lose it; two runs at once
# ---------------------------------------------------------------------------


@no_type_check
async def test_with_nothing_new_since_the_newest_fit_nothing_is_written(db_driver, learn_from):  # fmt: skip
    """The newest fit, in use or not: as many judgements, the newest made at the same time, the same signature. A
    judgement deleted, or one more, is something new; so is another signature"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids, made = await x_and_y(m, db_driver, 10, 10, "two_events", "agree")
    first = await fits.learn()
    again = await fits.learn()
    assert again.unchanged is not None and again.unchanged["id"] == first.id
    assert again.id is None and again.fits is None
    assert again.lines()[-1].startswith(f"Nothing new since the fit {first.id} of ")
    assert [f["id"] for f in written(db_driver)] == [first.id]
    # (a dry run still fits and compares, and says a run would write nothing)
    dry = await fits.learn(dry_run=True)
    assert dry.fits is not None and dry.unchanged is not None
    assert dry.lines()[-1].startswith("Nothing written (a dry run): the fit would be nothing, as a run would not write it")  # fmt: skip

    # (the newest written is the one compared with, though not in use)
    await fits.use(None)
    assert (await fits.learn()).unchanged["id"] == first.id

    await m.StatementJudgement.delete(made[0])
    second = await fits.learn()
    assert second.unchanged is None and second.id is not None
    await judge(m, ids["xfresha"], ids["xfreshb"], "two_events")
    third = await fits.learn()
    assert third.unchanged is None and third.id is not None
    assert len(written(db_driver)) == 3


@no_type_check
async def test_an_answers_model_in_use_and_a_fit_that_would_lose_it_is_written_not_in_use(db_driver, learn_from):  # fmt: skip
    """Both models of one fit in use, the route answering with both; then too few judgements of orders (some
    deleted): the next fit's "one event or two" passes, its "does this answer that" does not, so it is written and
    not put in use, and says why (`learn`, `status`); `use` still puts it in use"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids, _ = await x_and_y(m, db_driver, 10, 10, "two_events", "agree", fresh=False)
    answered = await orders_answered(m, db_driver, ids, LEARN_FROM + 2)
    first = await fits.learn()
    assert first.examples == {maths.ONE_EVENT: 20, maths.ANSWERS_IT: LEARN_FROM + 2}
    assert first.in_use and first.used(maths.ONE_EVENT) and first.used(maths.ANSWERS_IT), first.lines()  # fmt: skip
    assert first.lines()[-1] == f'Written: the fit {first.id}, in use for "one event or two" and "does this answer that"'  # fmt: skip

    # (the route with "answers" in use: an order and a giving five months after the day ordered, by hand the answer)
    statements = {r["label"]: r["id"] for r in run(db_driver, "MATCH (n:Transfer) RETURN n.label AS label, n.id AS id")}  # fmt: skip
    answer = await compared(statements["to give 20"], "Transfer")
    assert answer["model"]["answers"] is True and answer["model"]["oneEvent"] is True
    (late,) = [e for e in answer["pairs"] if e["other"]["label"] == "gave 20"]
    assert late["workedOut"]["relation"] == "two"
    by_hand = maths.logistic({**dict.fromkeys(maths.ANSWER_WEIGHTS, 0.0), "bias": 1.0, "missed_by": math.log1p(120)}, maths.ANSWER_WEIGHTS)  # fmt: skip
    assert by_hand >= 0.5 > late["likelihood"]

    for id in answered[:3]:
        await m.StatementJudgement.delete(id)
    second = await fits.learn()
    assert second.used(maths.ONE_EVENT) and not second.used(maths.ANSWERS_IT)
    assert not second.in_use and second.lost == (maths.ANSWERS_IT,)
    assert second.not_in_use.startswith(
        f'the fit in use, {first.id}, has "Does this answer that" in use'
    )
    lines = second.lines()
    assert lines[-2].startswith(
        f"Written: the fit {second.id}, not in use: the fit in use, {first.id}, has"
    )
    assert lines[-2].endswith(
        f"(`pangloss compare learn --use {second.id}` puts it in use)"
    )
    assert lines[-1] == f"The fit in use stays in use: {first.id}"
    assert [(f["id"], f["in_use"]) for f in written(db_driver)] == [(first.id, True), (second.id, False)]  # fmt: skip
    (stored,) = [f for f in written(db_driver) if f["id"] == second.id]
    assert stored["one_event_used"] is True and stored["answers_used"] is False
    assert stored["not_in_use"] == second.not_in_use

    said = fits.status_lines(await fits.status())
    assert said[-1].startswith(f"the newest fit, {second.id} of ") and said[
        -1
    ].endswith(second.not_in_use)
    assert any(line.startswith('  "Does this answer that": used;') for line in said)

    used = await fits.use(second.id)
    assert used["one_event_used"] is True and used["answers_used"] is False
    assert (await fits.in_use())["id"] == second.id


@no_type_check
async def test_two_runs_of_learn_at_once_each_write_a_fit_and_one_is_in_use(db_driver, learn_from):  # fmt: skip
    """Nothing stops two runs at once (each reads, fits and writes in its own transactions): each writes its fit,
    or, where the other's was written before it looked, finds nothing new since it; the route and `status` read one
    fit in use, the newest of those marked"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids, _ = await x_and_y(m, db_driver, 10, 10, "two_events", "agree")
    runs = await asyncio.gather(fits.learn(), fits.learn())
    ids_written = {f["id"] for f in written(db_driver)}
    assert {each.id for each in runs if each.id} == ids_written and ids_written
    for each in runs:
        assert each.id is not None or each.unchanged["id"] in ids_written
    # (exactly one marked in use, the newest of those written: `fits.SETTLE_QUERY`)
    marked = [f for f in written(db_driver) if f["in_use"]]
    assert len(marked) == 1
    assert (
        marked[0]["id"] == written(db_driver)[-1]["id"] == (await fits.in_use())["id"]
    )
    assert (await compared(ids["xfresha"]))["model"]["id"] == marked[0]["id"]


@no_type_check
async def test_two_fits_marked_in_use_are_settled_to_the_newest(db_driver, learn_from):
    """Two runs that each unmark what was marked before and mark their own, neither seeing the other's (made here by
    hand, as such a pair of writes would leave them): the next settling leaves only the newest marked"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    ids, _ = await x_and_y(m, db_driver, 10, 10, "two_events", "agree")
    first = await fits.learn()
    await judge(m, ids["xfresha"], ids["xfreshb"], "two_events")
    second = await fits.learn()
    run(db_driver, "MATCH (m:PGCompareModel) SET m.in_use = true")
    assert [f["in_use"] for f in written(db_driver)] == [True, True]
    await fits._settle()
    assert [(f["id"], f["in_use"]) for f in written(db_driver)] == [(first.id, False), (second.id, True)]  # fmt: skip
