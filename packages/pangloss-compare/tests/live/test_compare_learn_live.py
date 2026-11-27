"""Learning from judgements (`pangloss_compare.fits`; implementation_docs/spaces-and-comparison-plan.md, step 6.6), on
the backend under test, with `similar_models.declare(compared=True)` and its `StatementJudgement`.

The judgements are of gatherings by one host told twice (`x_and_y`): an X pair names no guests (the hand-set
likelihood of one event 0.55), a Y pair names guests that are partly the same (0.43). Judged against the hand-set
score (X two events, Y one), a fit corrects it and is put in use; judged as the score has it with few Y, the fit is
worse on judgements held out and is refused. What is claimed: none; too few; a fit in use, which the route then
answers with and says so; a worse one refused; a fit of another signature not used; `use` of none and of an id; a
dry run; a judgement on a statement changed since it was cited left out and counted; the admin job. The commands
are `test_compare_learn_command_live.py`'s."""

import json
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

from test_compare_pairs_live import activity, entities, factoid, ref, settled
from test_compare_route_live import client

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


async def compared(id: str) -> dict:
    async with client() as api:
        response = await api.get(f"/api/compare/Activity/{id}")
    assert response.status_code == 200, response.text
    return response.json()


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
    assert json.loads(fit["compared"])["one_event"] == {"decisions": 20, "model": 20, "baseline": 0}  # fmt: skip
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
        "it called 18 of 20 judgements held out rightly, fewer than the hand-set score (20)"
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
    second = await fits.learn()
    assert first.in_use and second.in_use
    assert [(f["id"], f["in_use"]) for f in written(db_driver)] == [(first.id, False), (second.id, True)]  # fmt: skip
    # (every judgement now as the hand-set score has it, the Y ones few: worse, refused, the second stays)
    for n in range(10):
        await judge(m, ids[f"x{n}a"], ids[f"x{n}b"], "agree")
    for n in range(8):
        await judge(m, ids[f"y{n}a"], ids[f"y{n}b"], "agree")
    third = await fits.learn()
    assert third.left_out[learning.OLDER] == 18
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
    assert fits.status_lines(status)[-1].startswith("it is of other features")
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
    monkeypatch.setattr(core_settings.SETTINGS, "COMPARE_LEARN_FROM", 21)
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
    # (and one that cites the same statement twice; and an older judgement of a pair judged again)
    await judge(m, ids["x1a"], ids["x1a"], "agree")
    await judge(m, ids["x2b"], ids["x2a"], "two_events")

    learnt = await fits.learn()
    assert learnt.judgements == 5
    assert {why: n for why, n in learnt.left_out.items() if n} == {
        learning.CHANGED: 1,
        learning.ITSELF: 1,
        learning.OLDER: 1,
    }
    assert learnt.examples[maths.ONE_EVENT] == 2
    lines = learnt.lines()
    assert "1 judgement left out: a statement it cites has changed since it was cited" in lines  # fmt: skip
    assert "1 judgement left out: it cites one statement twice" in lines


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
