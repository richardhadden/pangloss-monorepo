"""Review's work in the background, with no database: waiting for it to end"""

import asyncio

from pangloss_review import reconcile


def test_waiting_for_the_background_ends_when_a_task_woke_its_waiter_as_its_last_act():
    """A task whose last act wakes whoever waits has ended, and is still held, when the waiter runs: its callback
    comes after. Waiting for the background then has to give the loop a turn (it span for ever: the hang seen in
    test runs of step 10.5)"""

    async def main() -> bool:
        told = asyncio.get_running_loop().create_future()

        async def work() -> None:
            told.set_result(None)

        reconcile.in_background(work())
        await told
        held = bool(reconcile._background) and all(
            task.done() for task in reconcile._background
        )
        await asyncio.wait_for(reconcile.background_done(), 5)
        return held

    try:
        assert asyncio.run(main()), "the case was not made: the task was not held"
        assert not reconcile._background
    finally:
        reconcile._background.clear()


def test_waiting_for_the_background_waits_for_work_started_by_the_work():
    done: list[str] = []

    async def second() -> None:
        await asyncio.sleep(0.01)
        done.append("second")

    async def first() -> None:
        await asyncio.sleep(0.01)
        reconcile.in_background(second())
        done.append("first")

    async def main() -> None:
        reconcile.in_background(first())
        await asyncio.wait_for(reconcile.background_done(), 5)

    try:
        asyncio.run(main())
        assert done == ["first", "second"]
    finally:
        reconcile._background.clear()
