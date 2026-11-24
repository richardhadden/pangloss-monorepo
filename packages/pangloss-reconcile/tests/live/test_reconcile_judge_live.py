"""A project's judge in the worker that suggests (step 10.5c' of implementation_docs/similarity-build-plan.md;
`judging.py`, `suggesting.judged`), on the backend under test.

On the worker's models and world (`test_reconcile_worker_live.py`: two Jon Smyths in different company, one who met
Ada and Ben, one Cy and Dee), the judges are functions of this module named in `RECONCILE_SUGGEST_WITH`; what each
answers is set by the test, by the label of the stand-in asked about (`ANSWERS`). What is claimed: what the judge is
given; that its answers are written as the worker's own are (unchanged, left, replaced, an entity added, further
fields); that a judge that fails leaves that mention as it is, not tried, and the rest of the document written, and
is no failure of the head; that the lease and the claims are kept while it thinks, and a publish meanwhile is found;
that what is kept for learning is the worker's own candidates; and that with no setting nothing of it is made."""

import asyncio
import inspect
import json
import sys
import threading
import time
from typing import Any, no_type_check
from uuid import UUID, uuid4

import pytest
import test_reconcile_worker_live as worker_tests
from pangloss_models.utils import editable
from pangloss_reconcile import Asked, Leave, Suggest, Unchanged
from pangloss_testing.parts import one_turn
from test_reconcile_worker_live import (
    NAME,
    STRANGER,
    TOOLCHAIN,
    as_person,
    drained,
    factoid,
    kept,
    marks,
    percents,
    ref,
    rewriting_save,
    settle,
    stand_ins,
    suggestions,
    unknown,
    worker_models,
    world,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

# (the worker's tests' fixtures: the database emptied, the package's migrations applied, a new worker for each test,
# a setting changed for one test)
database = worker_tests.database
structure = worker_tests.structure
a_new_worker = worker_tests.a_new_worker
setting = worker_tests.setting

HERE = __name__

# What the judges answer, by the label of the stand-in asked about: an answer; an exception, raised; or a function of
# the `Asked`, sync or async, whose result is the answer. A label not there: None
ANSWERS: dict[str, Any] = {}
# Every `Asked` a judge was given, and the threads the sync judge ran in
CALLS: list[Asked] = []
THREADS: list[int] = []


async def _answer(asked: Asked) -> Any:
    answer = ANSWERS.get(asked.stand_in["label"])
    if isinstance(answer, BaseException):
        raise answer
    if callable(answer):
        answer = answer(asked)
        if inspect.isawaitable(answer):
            answer = await answer
    return answer


async def judge(asked: Asked) -> Any:
    """An async judge"""
    CALLS.append(asked)
    return await _answer(asked)


def sync_judge(asked: Asked) -> Any:
    """A sync judge (run in a thread): what it answers may not be awaited"""
    CALLS.append(asked)
    THREADS.append(threading.get_ident())
    answer = ANSWERS.get(asked.stand_in["label"])
    if isinstance(answer, BaseException):
        raise answer
    return answer(asked) if callable(answer) else answer


def unchanged(asked: Asked) -> Any:
    """A judge that says nothing (None)"""
    CALLS.append(asked)
    return None


@pytest.fixture(autouse=True)
def answers():
    """What the judges answer, emptied before and after each test"""
    ANSWERS.clear()
    CALLS.clear()
    THREADS.clear()
    yield ANSWERS
    ANSWERS.clear()
    CALLS.clear()
    THREADS.clear()


@pytest.fixture
def judged_by(setting):
    """`judged_by(name)`: the judge of this module of that name configured"""

    def use(name: str = "judge", timeout: float = 60.0) -> str:
        full = f"{HERE}:{name}"
        setting("RECONCILE_SUGGEST_WITH", full)
        setting("RECONCILE_SUGGEST_TIMEOUT", timeout)
        return full

    return use


def tried(db_driver) -> dict[str, Any]:
    """The stand-ins noted as tried, with the suggestion written in their place (None: left)"""
    return {
        row["stand_in"]: row.get("suggested")
        for row in kept(db_driver, "PGReconcileTried")
    }


def written(db_driver, head: Any) -> dict[str, Any]:
    """The suggestions of a head, by their text"""
    return {row["p"]["text"]: row["p"] for row in suggestions(db_driver, head)}


@no_type_check
async def one_of(m, head: Any, label: str) -> Any:
    """The node in `met` of the first statement of a head whose label, or text, is this"""
    view = await m.Factoid.get(head)
    return next(
        item
        for item in view.statements[0].met
        if getattr(item, "text", None) == label or getattr(item, "label", None) == label
    )


# ---------------------------------------------------------------------------
# What it is given, and an answer that changes nothing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "answer"), [("unchanged", None), ("judge", Unchanged())]
)
@no_type_check
async def test_a_judge_that_answers_none_or_unchanged_leaves_the_decision_and_is_given_plain_data(
    database, judged_by, answers, name, answer
):
    m = worker_models()
    ids = await world(m, database)
    configured = judged_by(name)
    answers[NAME] = answer
    made = await factoid(
        m, ids, unknown(uris=["http://example.org/jon"]), unknown(STRANGER)
    )
    mentions = stand_ins(database, made.id)
    await settle(database)

    assert await drained() == 1

    # (asked of both mentions: the stranger, decided nothing, too)
    assert sorted(asked.stand_in["label"] for asked in CALLS) == sorted(
        [NAME, STRANGER]
    )
    asked = next(a for a in CALLS if a.stand_in["label"] == NAME)
    assert asked.stand_in == {
        "id": mentions[NAME],
        "label": NAME,
        "stood_for": "Person",
        "uris": ["http://example.org/jon"],
        "place": ["statements", "met"],
        "held_by": "Meeting",
    }
    # (the head as Python names it, JSON-ready)
    assert (asked.document["type"], asked.document["id"]) == ("Factoid", str(made.id))
    assert "statements" in asked.document
    json.dumps(asked.document)
    json.dumps(asked.candidates)
    json.dumps(asked.decision)
    json.dumps(asked.takes)
    first = asked.candidates[0]
    assert (first["id"], first["type"], first["label"]) == (ids["jon"], "Person", NAME)
    assert set(first) == {"id", "type", "label", "score", "scores", "shared"}
    assert {"name", "graph"} <= set(first["scores"])
    assert {s["id"] for s in first["shared"]} == {ids["Ada"], ids["Ben"]}
    assert all(set(s) == {"id", "type", "label", "documents"} for s in first["shared"])
    assert len(asked.candidates) <= 5
    assert asked.decision["reason"] == "suggested"
    assert asked.decision["alternatives"][0]["id"] == ids["jon"]
    assert sum(a["percent"] for a in asked.decision["alternatives"]) == 100
    assert asked.takes == {"shape": "alternatives", "classes": ["Person"]}
    stranger = next(a for a in CALLS if a.stand_in["label"] == STRANGER)
    assert stranger.decision["alternatives"] == []
    assert stranger.decision["reason"] in ("low", "none")

    # (written as without a judge, saying the judge was used)
    suggested = await one_of(m, made.id, NAME)
    assert percents(suggested.target) == [
        (a["id"], a["percent"]) for a in asked.decision["alternatives"]
    ]
    assert suggested.toolchain_version == f"profile who, judge {configured}"
    assert tried(database) == {
        mentions[STRANGER]: None,
        mentions[NAME]: str(suggested.id),
    }


@no_type_check
async def test_a_witness_place_of_one_entity_is_given_as_one(database, judged_by):
    m = worker_models()
    ids = await world(m, database)
    judged_by("unchanged")
    made = await factoid(m, ids, ref(ids["Dee"]), witness=unknown())
    await settle(database)

    assert await drained() == 1

    (asked,) = CALLS
    assert asked.takes == {"shape": "one", "classes": ["Person"]}
    assert asked.stand_in["place"] == ["statements", "witness"]
    view = await m.Factoid.get(made.id)
    assert [str(t.id) for t in view.statements[0].witness.target] == [ids["jon"]]


# ---------------------------------------------------------------------------
# Its own answers
# ---------------------------------------------------------------------------


@no_type_check
async def test_leave_leaves_the_mention_and_notes_it_as_tried(
    database, judged_by, answers
):
    m = worker_models()
    ids = await world(m, database)
    judged_by()
    answers[NAME] = Leave()
    made = await factoid(m, ids, unknown())
    mentions = stand_ins(database, made.id)
    await settle(database)

    assert await drained() == 1

    assert suggestions(database, made.id) == []
    assert stand_ins(database, made.id) == mentions
    assert tried(database) == {mentions[NAME]: None}
    assert marks(database) == []
    # (tried: the next save does not ask again)
    await rewriting_save(m, await m.Factoid.get(made.id))
    await settle(database)
    assert await drained() == 1
    assert len(CALLS) == 1


@no_type_check
async def test_its_own_alternatives_among_the_candidates_replace_the_decision_and_are_kept_as_written(
    database, judged_by, answers
):
    m = worker_models()
    ids = await world(m, database)
    judged_by()
    answers[NAME] = Suggest(
        [(ref(ids["jon"]), 1), ({"type": "Person", "id": UUID(ids["namesake"])}, 3)]
    )
    made = await factoid(m, ids, unknown())
    await settle(database)

    assert await drained() == 1

    suggested = await one_of(m, made.id, NAME)
    assert percents(suggested.target) == [(ids["namesake"], 75), (ids["jon"], 25)]
    (row,) = kept(database)
    assert row["id"] == str(suggested.id)
    rows = json.loads(row["rows"])
    # (the worker's own candidates and their numbers; displayed: what was written)
    assert ids["jon"] in [r["id"] for r in rows]
    assert {r["id"] for r in rows if r["displayed"]} == {ids["jon"], ids["namesake"]}
    assert [a["id"] for a in json.loads(row["alternatives"])] == [
        ids["namesake"],
        ids["jon"],
    ]


@no_type_check
async def test_an_entity_that_is_no_candidate_is_written_kept_as_none_of_those_offered_and_learnt_so(
    database, judged_by, answers
):
    from pangloss_review import identify

    m = worker_models()
    ids = await world(m, database)
    judged_by()
    made = await factoid(m, ids, unknown())
    await settle(database)
    # (made after the marks were worked off: no part has a vector of him yet, he is no candidate; his mark is newer
    # than the worker's, which does not wait for it)
    zed = str((await m.Person.Create(label="Zed").save()).id)
    answers[NAME] = Suggest([(ref(zed), 1)])

    assert await drained() == 1

    asked = CALLS[0]
    assert zed not in [c["id"] for c in asked.candidates]
    suggested = await one_of(m, made.id, NAME)
    assert percents(suggested.target) == [(zed, 100)]
    (row,) = kept(database)
    rows = json.loads(row["rows"])
    assert rows and zed not in [r["id"] for r in rows]
    assert not any(r["displayed"] for r in rows)

    # (a person confirms him: "none of those offered")
    with as_person(database):
        await identify.confirm(UUID(str(suggested.id)), "ann")
    (example,) = kept(database, "PGReconcileExample")
    assert (example["via"], example.get("taken")) == ("suggestion", None)
    assert example["rows"] == row["rows"]


@no_type_check
async def test_further_fields_of_a_subclass_of_suggestion_are_written(
    database, judged_by, answers, setting
):
    def noted(library):
        class NotedSuggestion[T](library.IdentificationByToolchainFromText[T]):
            note: str | None = None

        return {"NotedSuggestion": NotedSuggestion}

    m = worker_models(noted)
    ids = await world(m, database)
    setting("RECONCILE_SUGGEST_AS", "NotedSuggestion")
    judged_by()
    answers[NAME] = Suggest([(ref(ids["jon"]), 1)], fields={"note": "by the letters"})
    made = await factoid(m, ids, unknown())
    await settle(database)

    assert await drained() == 1

    suggested = await one_of(m, made.id, NAME)
    assert (suggested.type, suggested.note) == ("NotedSuggestion", "by the letters")
    assert percents(suggested.target) == [(ids["jon"], 100)]


@no_type_check
async def test_a_sync_judge_runs_in_a_thread(database, judged_by, answers):
    m = worker_models()
    ids = await world(m, database)
    judged_by("sync_judge")
    answers[NAME] = Suggest([(ref(ids["namesake"]), 1)])
    made = await factoid(m, ids, unknown())
    await settle(database)

    assert await drained() == 1

    assert THREADS and threading.get_ident() not in THREADS
    assert percents((await one_of(m, made.id, NAME)).target) == [(ids["namesake"], 100)]


# ---------------------------------------------------------------------------
# A judge that fails: that mention left, not tried; the rest written
# ---------------------------------------------------------------------------


async def deleted_person(m: Any) -> dict[str, str]:
    person = await m.Person.Create(label="Gone").save()
    await m.Person.delete(person.id)
    return ref(person.id)


@pytest.mark.parametrize(
    "bad",
    [
        "a class the place does not take",
        "not of the class it says",
        "not there",
        "deleted",
        "merged away",
        "an unknown field",
        "raises",
        "a bad answer",
    ],
)
@no_type_check
async def test_a_judge_that_fails_for_one_mention_leaves_it_untried_and_the_other_is_written(
    database, judged_by, answers, caplog, a_new_worker, bad
):
    import logging

    m = worker_models()
    ids = await world(m, database)
    judged_by()
    household = str(
        (await m.Household.Create(label="the Smyths", members=[]).save()).id
    )
    if bad == "merged away":
        elder = str((await m.Person.Create(label="Elder").save()).id)
        younger = str((await m.Person.Create(label="Younger").save()).id)
        await m.Person.merge(absorb=UUID(younger), into=UUID(elder))
    answers[NAME] = {
        "a class the place does not take": Suggest([(ref(household, "Household"), 1)]),
        "not of the class it says": Suggest([(ref(household), 1)]),
        "not there": Suggest([(ref(uuid4()), 1)]),
        "deleted": Suggest([(await deleted_person(m), 1)])
        if bad == "deleted"
        else None,
        "merged away": Suggest([(ref(younger), 1)]) if bad == "merged away" else None,
        "an unknown field": Suggest([(ref(ids["jon"]), 1)], fields={"nonsense": 1}),
        "raises": RuntimeError("the model's API is down"),
        "a bad answer": Suggest([(ref(ids["jon"]), 0)]),
    }[bad]
    answers[STRANGER] = Suggest([(ref(ids["Dee"]), 1)])
    made = await factoid(m, ids, unknown(), unknown(STRANGER))
    mentions = stand_ins(database, made.id)
    await settle(database)
    before = worker_tests.versions(database)[str(made.id)]

    with caplog.at_level(logging.WARNING, logger="pangloss.reconcile.worker"):
        assert await drained() == 1

    # (one update: the stranger written, Jon Smyth left as he was, with his id, and not tried)
    assert worker_tests.versions(database)[str(made.id)] == before + 1
    assert list(written(database, made.id)) == [STRANGER]
    assert stand_ins(database, made.id) == {NAME: mentions[NAME]}
    assert mentions[NAME] not in tried(database)
    assert mentions[STRANGER] in tried(database)
    assert marks(database) == []
    # (no failure of the head)
    assert a_new_worker._failures == {}
    assert a_new_worker.stats.refused == 0
    assert a_new_worker.stats.judge_failures == 1
    (warning,) = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "judge" in r.getMessage()
    ]
    said = warning.getMessage()
    assert mentions[NAME] in said and str(made.id) in said and HERE in said
    expected = {
        "a class the place does not take": "this place takes Person",
        "not of the class it says": "is not a Person",
        "not there": "is not there",
        "deleted": "is deleted",
        "merged away": "was merged into",
        "an unknown field": "would be refused by the write",
        "raises": "RuntimeError: the model's API is down",
        "a bad answer": "the weight is a number above 0",
    }[bad]
    assert expected in said, said

    # (the mark was completed; the next save asks the judge again of Jon Smyth, and him alone)
    CALLS.clear()
    answers[NAME] = Suggest([(ref(ids["jon"]), 1)])
    await rewriting_save(m, await m.Factoid.get(made.id))
    await settle(database)
    assert await drained() == 1
    assert [asked.stand_in["label"] for asked in CALLS] == [NAME]
    assert sorted(written(database, made.id)) == [NAME, STRANGER]


@no_type_check
async def test_a_judge_that_fails_again_and_again_is_never_a_failure_of_the_head(
    database, judged_by, answers, a_new_worker
):
    from pangloss_reconcile import suggesting

    m = worker_models()
    ids = await world(m, database)
    judged_by()
    answers[NAME] = RuntimeError("down")
    made = await factoid(m, ids, unknown())
    await settle(database)
    for _ in range(suggesting.FAILURES + 1):
        assert await drained() == 1
        assert marks(database) == []
        await rewriting_save(m, await m.Factoid.get(made.id))
        await settle(database)

    assert len(CALLS) == suggesting.FAILURES + 1
    assert a_new_worker.stats.refused == 0
    assert a_new_worker._failures == {}
    assert NAME in stand_ins(database, made.id)


@no_type_check
async def test_a_judge_past_its_timeout_leaves_the_mention_and_the_other_is_written(
    database, judged_by, answers, caplog
):
    import logging

    m = worker_models()
    ids = await world(m, database)
    judged_by(timeout=0.2)

    async def slow(asked):
        await asyncio.sleep(5)
        return Suggest([(ref(ids["jon"]), 1)])

    answers[NAME] = slow
    answers[STRANGER] = Suggest([(ref(ids["Dee"]), 1)])
    made = await factoid(m, ids, unknown(), unknown(STRANGER))
    mentions = stand_ins(database, made.id)
    await settle(database)
    started = time.monotonic()

    with caplog.at_level(logging.WARNING, logger="pangloss.reconcile.worker"):
        assert await drained() == 1

    assert time.monotonic() - started < 4
    assert list(written(database, made.id)) == [STRANGER]
    assert mentions[NAME] not in tried(database)
    assert any("did not answer within 0.2 s" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# A slow judge: the lease and the claims kept; a publish meanwhile found
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["judge", "sync_judge"])
@no_type_check
async def test_a_slow_judge_keeps_the_lease_and_the_claims_and_holds_no_transaction(
    database, judged_by, answers, name
):
    from pangloss_reconcile.suggesting import Settings, Worker

    m = worker_models()
    ids = await world(m, database)
    judged_by(name)

    thinking = []

    def slowly(asked):
        # (longer than the lease, three times: renewed meanwhile)
        thinking.append(time.monotonic())
        time.sleep(1.2)
        thinking.append(time.monotonic())
        return Suggest([(ref(ids["namesake"]), 1)])

    async def slowly_async(asked):
        thinking.append(time.monotonic())
        await asyncio.sleep(1.2)
        thinking.append(time.monotonic())
        return Suggest([(ref(ids["namesake"]), 1)])

    answers[NAME] = slowly if name == "sync_judge" else slowly_async
    made = await factoid(m, ids, unknown())
    await settle(database)
    one, other = Worker(Settings(lease=0.4)), Worker(Settings(lease=0.4))
    assert await one.take_lease()

    ticks = []

    async def ticking():
        while True:
            ticks.append(time.monotonic())
            await asyncio.sleep(0.05)

    ticker = asyncio.create_task(ticking())
    working = asyncio.create_task(one.process_batch())
    try:
        await asyncio.sleep(0.8)
        assert not working.done()
        assert CALLS, "the judge is thinking"
        assert await other.claim() == []
        assert not await other.take_lease()
        # (no lock is held meanwhile: a person's save, which says nothing of suggestions, goes through, and the
        # worker finds the version moved on)
        view = await m.Factoid.get(made.id)
        with as_person(database):
            await m.Factoid.Update(**editable(view.model_dump())).save(
                expected_version=view.meta.version
            )
        assert await working == 1
    finally:
        ticker.cancel()
        if not working.done():
            working.cancel()

    # (the loop went on while the judge thought: a sync judge is not run in it)
    start, end = thinking
    assert len([t for t in ticks if start < t < end]) >= 10
    assert one.stats.conflicts == 1
    assert suggestions(database, made.id) == []


@no_type_check
async def test_a_head_published_while_the_judge_thinks_is_left_as_a_published_one(
    database, judged_by, answers, caplog
):
    from pangloss_cypher.write_functions import set_review_status_in_db

    m = worker_models()
    ids = await world(m, database)
    judged_by()
    made = await factoid(m, ids, unknown())
    await settle(database)

    async def publishing(asked):
        await set_review_status_in_db(made.id, "published", True, "ann")
        return Suggest([(ref(ids["namesake"]), 1)])

    answers[NAME] = publishing

    await worker_tests.left_alone(database, caplog, "published")

    assert len(CALLS) == 1
    assert suggestions(database, made.id) == []
    assert (await m.Factoid.get(made.id)).meta.published is True


# ---------------------------------------------------------------------------
# With no setting, nothing of it
# ---------------------------------------------------------------------------


@no_type_check
async def test_with_no_setting_nothing_of_a_judge_is_made_imported_or_called(
    database, monkeypatch
):
    from pangloss_reconcile import judging, suggesting

    def never(*args, **options):
        raise AssertionError("nothing of a judge is made with no setting")

    monkeypatch.setattr(suggesting.Judging, "of", never)
    monkeypatch.setattr(judging, "call", never)
    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown())
    await settle(database)

    assert await drained() == 1

    assert len(suggestions(database, made.id)) == 1
    assert "reconcile_judge_raises_on_import" not in sys.modules
    assert CALLS == []
    assert (await one_of(m, made.id, NAME)).toolchain_version == "profile who"


@no_type_check
async def test_with_no_setting_the_statements_are_those_with_a_judge_that_changes_nothing_less_its_candidates(
    database, setting, monkeypatch
):
    """(what a judge that answers None adds is the one read of the candidates' reference views, `api.answered`: the
    rest, the update's own statements included, is the same, in the same order)"""
    from pangloss_reconcile import api
    from pangloss_testing.conformance.test_query_costs import recorded

    m = worker_models()
    ids = await world(m, database)
    # (the toolchain made, and the first batch's reads done, before anything is counted)
    await factoid(m, ids, unknown())
    await settle(database)
    assert await drained() == 1

    async def statements() -> list[str]:
        await factoid(m, ids, unknown())
        await settle(database)
        with recorded() as r:
            recording.append(r)
            assert await drained() == 1
        return [query for query, _ in r.statements]

    recording = []
    spans = []
    real = api.answered

    async def answered(*args, **options):
        start = len(recording[-1].statements)
        try:
            return await real(*args, **options)
        finally:
            spans.append((start, len(recording[-1].statements)))

    monkeypatch.setattr(api, "answered", answered)
    without = await statements()
    assert spans == []
    setting("RECONCILE_SUGGEST_WITH", f"{HERE}:unchanged")
    with_judge = await statements()
    ((start, end),) = spans
    assert end > start
    assert with_judge[:start] + with_judge[end:] == without
    assert len(CALLS) == 1


# ---------------------------------------------------------------------------
# No more evidence than the worker's own
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_judge_s_suggestion_changes_no_later_score(
    database, judged_by, answers
):
    """(as 10.5c's live test: the namesake, who met Cy and Dee, suggested by the judge for a Jon Smyth who met Ada and
    Ben; another stored mention of Jon Smyth with Ada and Ben: the namesake's score and what he shares, the same)"""
    from pangloss_reconcile import candidates_of
    from pangloss_reconcile.stored import stored_plan

    m = worker_models()
    ids = await world(m, database)
    judged_by()
    answers[NAME] = Suggest([(ref(ids["namesake"]), 1)])
    other = await m.Factoid.Create(
        label="Ada met Ben and Jon again",
        statements=[
            worker_tests.meeting(ref(ids["Ada"]), [ref(ids["Ben"]), unknown()])
        ],
    ).save()
    (asked,) = stand_ins(database, other.id).values()

    async def candidates() -> dict[str, Any]:
        plan = await stored_plan(asked)
        (found,) = await candidates_of(
            plan, see_unpublished=True, limit=10, only=[asked]
        )
        return {c.id: (c.score, c.scores, c.shared) for c in found.candidates}

    made = await factoid(m, ids, unknown())
    await settle(database)
    before = await candidates()
    assert ids["namesake"] in before

    assert await drained() == 1
    assert percents((await one_of(m, made.id, NAME)).target) == [(ids["namesake"], 100)]
    assert await one_turn(database) > 0

    after = await candidates()
    score, scores, shared = before[ids["namesake"]]
    assert after[ids["namesake"]][0] == pytest.approx(score, abs=1e-6)
    assert after[ids["namesake"]][1] == pytest.approx(scores, abs=1e-6)
    assert after[ids["namesake"]][2] == shared
    assert TOOLCHAIN in {
        s["p"]["identified_by"] for s in suggestions(database, made.id)
    }
