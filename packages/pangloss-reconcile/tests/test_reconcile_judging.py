"""A project's judge in the worker, without a database (step 10.5c'; `judging.py`): the settings
`RECONCILE_SUGGEST_WITH` and `RECONCILE_SUGGEST_TIMEOUT` and their refusals by message, at `initialise()` too; each
answer's shape checked (`judging.checked`) with its message; weights to per cent (finite ones near the largest float
too); the one-entity shape takes the heaviest; how the judge is awaited (`judging.call`: its own `CancelledError`, a
sync one in the worker's own threads, `judging.Threads`, which refuse at once when all are busy and leave the loop's
default executor alone); `toolchain_version` and the digest's settings with a judge"""

import asyncio
import contextvars
import threading
import time
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from pangloss_core.settings import configure
from pangloss_models.exceptions import PanglossInitialisationError
from pangloss_reconcile import (
    Asked,
    Leave,
    Suggest,
    Unchanged,
    judging,
    settings,
    suggesting,
)
from pangloss_reconcile.judging import BadAnswer, checked
from pangloss_reconcile.suggest import Alternative, Decision

# (the parts and the models of the settings' tests: `registered` is a fixture, used here as it is there)
from test_reconcile_settings import APPS, WHO, people, registered  # noqa: F401

A, B, C = (str(uuid.UUID(int=n)) for n in (1, 2, 3))
DECIDED = Decision((Alternative(A, "Person", 100),), "suggested")


def given(**values: Any) -> SimpleNamespace:
    return SimpleNamespace(**values)


def person(id: str, kind: str = "Person") -> dict[str, str]:
    return {"type": kind, "id": id}


def a_judge(asked):
    """(named by the tests of the setting)"""
    return None


NOT_A_FUNCTION = 3


# -- the settings --------------------------------------------------------------------------------------------------


def test_there_is_no_judge_and_its_timeout_is_60_unless_given():
    assert settings.suggest_with(given()) is None
    assert settings.judge(given()) is None
    assert settings.suggest_timeout(given()) == 60.0
    assert settings.suggest_timeout(given(RECONCILE_SUGGEST_TIMEOUT=0.2)) == 0.2


def test_a_judge_named_is_imported():
    name = "test_reconcile_judging:a_judge"
    assert settings.judge(given(RECONCILE_SUGGEST_WITH=name)) == (name, a_judge)


@pytest.mark.parametrize(
    "value", ["a_judge", "test_reconcile_judging:", ":a_judge", "a b:c", "a:b.c", 3]
)
def test_a_judge_not_named_as_module_colon_function_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_SUGGEST_WITH names a project's judge as 'package.module:function'",
    ):
        settings.judge(given(RECONCILE_SUGGEST_WITH=value))


@pytest.mark.parametrize(
    ("value", "said"),
    [
        (
            "no_such_module_here:judge",
            r"whose module 'no_such_module_here' cannot be imported: ModuleNotFoundError: No module named "
            r"'no_such_module_here'",
        ),
        (
            "reconcile_judge_raises_on_import:judge",
            r"whose module 'reconcile_judge_raises_on_import' cannot be imported: RuntimeError: this judge's module "
            r"is broken",
        ),
        (
            "test_reconcile_judging:no_such_judge",
            r"but 'test_reconcile_judging' has no 'no_such_judge'",
        ),
        (
            "test_reconcile_judging:NOT_A_FUNCTION",
            r"which is not a function that can be called \(it is a int\)",
        ),
    ],
)
def test_a_judge_that_cannot_be_imported_or_called_is_refused_with_why(value, said):
    with pytest.raises(PanglossInitialisationError, match=said):
        settings.judge(given(RECONCILE_SUGGEST_WITH=value))


@pytest.mark.parametrize("value", [0, -1, "60", True, float("inf"), None])
def test_a_timeout_that_is_not_a_number_above_0_is_refused(value):
    with pytest.raises(
        PanglossInitialisationError,
        match=r"RECONCILE_SUGGEST_TIMEOUT is a number of seconds above 0",
    ):
        settings.suggest_timeout(given(RECONCILE_SUGGEST_TIMEOUT=value))


@pytest.mark.parametrize(
    ("more", "said"),
    [
        ({"RECONCILE_SUGGEST_WITH": "no_such_module_here:judge"}, "cannot be imported"),
        ({"RECONCILE_SUGGEST_WITH": "nocolon"}, "'package.module:function'"),
        ({"RECONCILE_SUGGEST_TIMEOUT": 0}, "RECONCILE_SUGGEST_TIMEOUT"),
    ],
)
def test_the_judge_and_its_timeout_are_checked_at_initialise(
    project_settings, more, said
):
    configure(project_settings(INSTALLED_APPS=APPS, VECTORS_PROFILES=WHO, **more))
    with pytest.raises(PanglossInitialisationError, match=said):
        people()


def test_a_judge_that_is_right_passes_at_initialise(project_settings):
    configure(
        project_settings(
            INSTALLED_APPS=APPS,
            VECTORS_PROFILES=WHO,
            RECONCILE_SUGGEST_WITH="test_reconcile_judging:a_judge",
            RECONCILE_SUGGEST_TIMEOUT=5,
        )
    )
    people()


# -- the answers ---------------------------------------------------------------------------------------------------


def test_none_and_unchanged_leave_the_decision_as_it_was():
    for answer in (None, Unchanged()):
        verdict = checked(answer, "alternatives", DECIDED)
        assert (verdict.decision, verdict.fields, verdict.by_judge) == (
            DECIDED,
            {},
            False,
        )


def test_leave_is_a_decision_of_nothing_by_the_judge():
    verdict = checked(Leave(), "alternatives", DECIDED)
    assert (verdict.decision.alternatives, verdict.decision.reason) == ((), "left")
    assert verdict.by_judge and not verdict.decision.suggested


def test_a_suggestion_s_weights_are_made_whole_per_cent_heaviest_first_and_its_fields_kept():
    verdict = checked(
        Suggest([(person(A), 1), (person(B), 3)], fields={"note": "the letters"}),
        "alternatives",
        DECIDED,
    )
    assert verdict.decision == Decision(
        (Alternative(B, "Person", 75), Alternative(A, "Person", 25)), "judged"
    )
    assert verdict.fields == {"note": "the letters"} and verdict.by_judge


def test_weights_cut_nothing_and_equal_ones_keep_the_judge_s_order():
    verdict = checked(
        Suggest([(person(id), 1.0) for id in (A, B, C)] * 1), "alternatives", DECIDED
    )
    assert [(a.id, a.percent) for a in verdict.decision.alternatives] == [
        (A, 34),
        (B, 33),
        (C, 33),
    ]
    many = [(person(str(uuid.UUID(int=n))), 1) for n in range(1, 101)]
    assert (
        len(checked(Suggest(many), "alternatives", DECIDED).decision.alternatives)
        == 100
    )


def test_where_the_place_takes_one_entity_the_heaviest_is_taken():
    verdict = checked(
        Suggest([(person(A), 1), (person(B, "Scholar"), 2.5), (person(C), 2.5)]),
        "one",
        DECIDED,
    )
    assert verdict.decision.alternatives == (Alternative(B, "Scholar", 100),)


def test_an_id_may_be_a_uuid_and_is_given_as_text():
    verdict = checked(
        Suggest([({"type": "Person", "id": uuid.UUID(A)}, 1)]), "one", DECIDED
    )
    assert verdict.decision.alternatives == (Alternative(A, "Person", 100),)


TWO = Decision(
    (Alternative(A, "Person", 60), Alternative(B, "Person", 40)), "suggested"
)


@pytest.mark.parametrize(
    ("answer", "shape", "decision"),
    [
        (Suggest([(person(A), 1)]), "one", DECIDED),
        # (the heaviest alone, where the place takes one)
        (Suggest([(person(A), 3), (person(B), 1)]), "one", DECIDED),
        (Suggest([(person(A), 5)]), "alternatives", DECIDED),
        (Suggest([(person(A), 1)], fields={}), "alternatives", DECIDED),
        # (the same ids and per cent, in another order)
        (Suggest([(person(B), 2), (person(A), 3)]), "alternatives", TWO),
    ],
)
def test_a_suggestion_the_same_as_the_decision_is_the_decision_and_not_the_judge_s(
    answer, shape, decision
):
    """(nothing written differs from what the worker decided: written as its own, `judged` not said)"""
    assert checked(answer, shape, decision) == judging.Verdict(decision)


@pytest.mark.parametrize(
    ("answer", "decision"),
    [
        # (another per cent)
        (Suggest([(person(A), 1), (person(B), 1)]), TWO),
        # (fewer alternatives)
        (Suggest([(person(A), 1)]), TWO),
        # (another entity)
        (Suggest([(person(C), 1)]), DECIDED),
        # (the same entity, with a field)
        (Suggest([(person(A), 1)], fields={"note": "x"}), DECIDED),
        # (the worker decided nothing)
        (Suggest([(person(A), 1)]), Decision((), "low")),
    ],
)
def test_a_suggestion_that_differs_from_the_decision_in_anything_is_the_judge_s(
    answer, decision
):
    verdict = checked(answer, "alternatives", decision)
    assert verdict.by_judge and verdict.decision.reason == "judged"


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        (
            {"type": "Person", "id": A},
            r"A judge answers None, Unchanged\(\), Leave\(\) or Suggest\(...\), not dict",
        ),
        (
            DECIDED,
            r"A judge answers None, Unchanged\(\), Leave\(\) or Suggest\(...\), not Decision",
        ),
        ("Person", r"A judge answers .*, not str"),
        (
            Suggest([]),
            r"Suggest has no alternative: answer Leave\(\) to suggest nothing",
        ),
        (
            Suggest([(person(str(uuid.UUID(int=n))), 1) for n in range(1, 102)]),
            r"Suggest has 101 alternatives: at most 100",
        ),
        (
            Suggest(person(A)),
            r"Suggest's alternatives are a list of \(reference, weight\)",
        ),  # ty: ignore[invalid-argument-type]
        (
            Suggest([person(A)]),
            r"Suggest's alternative 1 is a pair \(reference, weight\)",
        ),  # ty: ignore[invalid-argument-type]
        (
            Suggest([(person(A), 1, 2)]),
            r"Suggest's alternative 1 is a pair \(reference, weight\), not 3 values",
        ),  # ty: ignore[invalid-argument-type]
        (Suggest([((A,), 1)]), r"Suggest's alternative 1: the reference is a mapping"),  # ty: ignore[invalid-argument-type]
        (
            Suggest([({"id": A}, 1)]),
            r"Suggest's alternative 1: the reference has no 'type'",
        ),
        (Suggest([({"type": "", "id": A}, 1)]), r"the reference has no 'type'"),
        (
            Suggest([(person(A), 1), ({"type": "Person"}, 1)]),
            r"Suggest's alternative 2: the reference has no 'id'",
        ),
        (Suggest([(person("Ada"), 1)]), r"the reference's 'id' is no UUID: 'Ada'"),
        (
            Suggest([(person(A), 1), (person(A, "Scholar"), 2)]),
            r"Suggest names Scholar .* twice",
        ),
    ],
)
def test_a_bad_answer_is_refused_with_what_was_wrong(answer, said):
    with pytest.raises(BadAnswer, match=said):
        checked(answer, "alternatives", DECIDED)


@pytest.mark.parametrize("weight", [0, -1, "1", True, None, float("nan"), float("inf")])
def test_a_weight_that_is_not_a_number_above_0_is_refused(weight):
    with pytest.raises(
        BadAnswer,
        match=r"Suggest's alternative 2 \(Person .*\): the weight is a number above 0, not",
    ):
        checked(Suggest([(person(A), 1), (person(B), weight)]), "alternatives", DECIDED)


def test_an_int_too_large_for_a_float_is_a_bad_weight():
    with pytest.raises(
        BadAnswer,
        match=r"Suggest's alternative 1 \(Person .*\): the weight is a number above 0, not 1000",
    ):
        checked(Suggest([(person(A), 10**400)]), "alternatives", DECIDED)


@pytest.mark.parametrize(
    ("weights", "percents"),
    [
        # (finite, but their sum is not)
        ((1e308, 1e308), [50, 50]),
        (
            (
                1e307,
                1e307,
                1e307,
                1e307,
                1e307,
                1e307,
                1e307,
                1e307,
                1e307,
                1e307,
                1e307,
                1e307,
            ),
            None,
        ),
        ((1e307, 1), [99, 1]),
        ((4e307, 1e307), [79, 21]),
    ],
)
def test_weights_near_the_largest_float_are_made_per_cent_as_small_ones(
    weights, percents
):
    ids = [str(uuid.UUID(int=n)) for n in range(1, len(weights) + 1)]
    verdict = checked(
        Suggest([(person(id), w) for id, w in zip(ids, weights, strict=True)]),
        "alternatives",
        DECIDED,
    )
    found = [a.percent for a in verdict.decision.alternatives]
    assert sum(found) == 100
    if percents is not None:
        assert found == percents


@pytest.mark.parametrize("field", judging.WORKER_FIELDS)
def test_a_field_the_worker_fills_is_refused(field):
    with pytest.raises(
        BadAnswer, match=rf"Suggest's fields name {field}, which the worker fills"
    ):
        checked(
            Suggest([(person(A), 1)], fields={"note": "x", field: "y"}),
            "alternatives",
            DECIDED,
        )


def test_fields_that_are_not_a_mapping_of_names_are_refused():
    with pytest.raises(BadAnswer, match=r"Suggest's fields are a mapping"):
        checked(Suggest([(person(A), 1)], fields=["note"]), "one", DECIDED)  # ty: ignore[invalid-argument-type]
    with pytest.raises(BadAnswer, match=r"Suggest's fields are named by text"):
        checked(Suggest([(person(A), 1)], fields={1: "x"}), "one", DECIDED)


# -- how a judge is awaited ----------------------------------------------------------------------------------------

ASKED = Asked(stand_in={}, document={}, candidates=[], decision={}, takes={})


@pytest.mark.asyncio
async def test_an_async_judge_is_awaited_and_a_sync_one_runs_in_a_thread():
    async def asynchronous(asked):
        return Leave()

    where = []

    def synchronous(asked):
        where.append(threading.get_ident())
        return Unchanged()

    threads = judging.Threads()
    try:
        assert await judging.call(asynchronous, ASKED, 1, threads=threads) == Leave()
        assert await judging.call(synchronous, ASKED, 1, threads=threads) == Unchanged()
    finally:
        threads.shutdown()
    assert where and where[0] != threading.get_ident()
    assert threads.busy == 0


@pytest.mark.asyncio
async def test_what_a_sync_judge_gives_that_can_be_awaited_is_awaited():
    async def later():
        return Leave()

    threads = judging.Threads()
    try:
        assert (
            await judging.call(lambda asked: later(), ASKED, 1, threads=threads)
            == Leave()
        )
    finally:
        threads.shutdown()


@pytest.mark.asyncio
async def test_a_judge_past_its_timeout_is_timed_out_and_its_own_timeout_error_is_its_own():
    async def slow(asked):
        await asyncio.sleep(5)

    with pytest.raises(judging.TimedOut, match=r"no answer within 0.05 s"):
        await judging.call(slow, ASKED, 0.05, threads=judging.Threads())

    async def failing(asked):
        raise TimeoutError("its own call timed out")

    with pytest.raises(TimeoutError, match="its own call") as raised:
        await judging.call(failing, ASKED, 5, threads=judging.Threads())
    assert not isinstance(raised.value, judging.TimedOut)


@pytest.mark.asyncio
async def test_a_judge_s_own_cancelled_error_is_its_failure_and_the_worker_s_cancellation_goes_out():
    async def cancels(asked):
        raise asyncio.CancelledError()

    def cancels_in_a_thread(asked):
        raise asyncio.CancelledError()

    threads = judging.Threads()
    try:
        for judge in (cancels, cancels_in_a_thread):
            with pytest.raises(
                judging.JudgeCancelled, match="CancelledError of its own"
            ):
                await judging.call(judge, ASKED, 5, threads=threads)
            assert asyncio.current_task().cancelling() == 0

        # (the worker's task cancelled while the judge thinks: the cancellation goes out as it is)
        started = asyncio.Event()

        async def thinks(asked):
            started.set()
            await asyncio.sleep(5)

        task = asyncio.create_task(judging.call(thinks, ASKED, 10, threads=threads))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()
    finally:
        threads.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [SystemExit(3), KeyboardInterrupt()])
async def test_system_exit_and_keyboard_interrupt_of_a_judge_go_out_as_they_are(error):
    async def leaves(asked):
        raise error

    with pytest.raises(type(error)):
        await judging.call(leaves, ASKED, 5, threads=judging.Threads())


@pytest.mark.asyncio
async def test_a_judge_that_swallows_the_cancellation_of_its_timeout_is_timed_out():
    async def stubborn(asked):
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            return Leave()

    with pytest.raises(judging.TimedOut, match=r"no answer within 0.05 s"):
        await judging.call(stubborn, ASKED, 0.05, threads=judging.Threads())


WHO_ASKS = contextvars.ContextVar("who_asks", default="nobody")


@pytest.mark.asyncio
async def test_a_sync_judge_runs_in_the_worker_s_own_threads_and_when_all_are_held_it_fails_at_once():
    """(a sync judge that blocks on an event, past its timeout: its thread is held; with every thread of the pool held,
    the next asks fail at once, and the loop's default executor is untouched)"""
    release = threading.Event()
    names: list[str] = []
    contexts: list[str] = []

    def blocks(asked):
        names.append(threading.current_thread().name)
        contexts.append(WHO_ASKS.get())
        release.wait(10)
        return Suggest([(person(A), 1)])

    threads = judging.Threads(2)
    token = WHO_ASKS.set("the toolchain")
    try:
        for _ in range(2):
            with pytest.raises(judging.TimedOut):
                await judging.call(blocks, ASKED, 0.05, threads=threads)
        assert threads.busy == 2
        started = time.monotonic()
        with pytest.raises(
            judging.Busy, match="the judge's threads are all still busy"
        ):
            await judging.call(blocks, ASKED, 5, threads=threads)
        assert time.monotonic() - started < 0.5
        assert len(names) == 2
        # (the default executor is free: the server's and the driver's)
        loop = asyncio.get_running_loop()
        assert await loop.run_in_executor(None, lambda: "free") == "free"
        assert await asyncio.wait_for(asyncio.to_thread(lambda: 2), 1) == 2
    finally:
        WHO_ASKS.reset(token)
        release.set()
    # (the judges past their timeout return: their threads are given back, and the next ask runs)
    for _ in range(100):
        if threads.busy == 0:
            break
        await asyncio.sleep(0.02)
    assert threads.busy == 0
    try:
        assert await judging.call(blocks, ASKED, 5, threads=threads) == Suggest(
            [(person(A), 1)]
        )
    finally:
        threads.shutdown()
    assert all(name.startswith("pangloss-reconcile-judge") for name in names)
    # (in the caller's context: its user, what it sees)
    assert contexts[:2] == ["the toolchain", "the toolchain"]


@pytest.mark.asyncio
async def test_threads_let_go_count_what_still_runs_against_the_next_pool():
    release = threading.Event()

    def blocks(asked):
        release.wait(10)

    threads = judging.Threads(1)
    try:
        with pytest.raises(judging.TimedOut):
            await judging.call(blocks, ASKED, 0.05, threads=threads)
        threads.shutdown()
        with pytest.raises(judging.Busy):
            await judging.call(blocks, ASKED, 5, threads=threads)
    finally:
        release.set()
        threads.shutdown()


# -- what the worker says of a judge -------------------------------------------------------------------------------


def seen(fit_id: str | None, judge: str | None) -> suggesting.Seen:
    return suggesting.Seen(
        states=None,
        today={"profile": "who"},
        fit=None,
        fit_id=fit_id,
        toolchain="pangloss-reconcile",
        decided_by="",
        judge=None if judge is None else suggesting.Judge(judge, a_judge, 60.0),
    )


def test_toolchain_version_says_that_a_judge_was_used_after_the_profile_and_the_fit():
    assert suggesting.toolchain_version(seen(None, None)) == "profile who"
    assert suggesting.toolchain_version(seen("f1", None)) == "profile who, fit f1"
    assert (
        suggesting.toolchain_version(seen(None, "project.judges:ask"))
        == "profile who, judge project.judges:ask"
    )
    assert (
        suggesting.toolchain_version(seen("f1", "project.judges:ask"))
        == "profile who, fit f1, judge project.judges:ask"
    )


def test_the_settings_a_stand_in_is_tried_with_name_the_judge_only_when_there_is_one():
    without = suggesting.decided_by("f1")
    assert "judge" not in without
    assert suggesting.decided_by("f1", None) == without
    assert suggesting.decided_by("f1", "project.judges:ask") != without
    assert '"judge": "project.judges:ask"' in suggesting.decided_by(
        "f1", "project.judges:ask"
    )
