"""Background tasks that an installed app keeps running with the server"""

import asyncio
import textwrap

import pytest
from conftest import Settings
from fastapi.testclient import TestClient
from pangloss_api.app import create_app
from pangloss_api.background import BackgroundTask, Supervisor


def run(coroutine):
    return asyncio.run(coroutine)


async def until(condition, timeout=2.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not condition():
        if loop.time() > end:
            raise AssertionError("it did not happen")
        await asyncio.sleep(0.005)


def test_a_task_that_raises_is_started_again_after_a_delay_that_grows():
    calls = []
    sleeps = []

    async def failing(settings):
        calls.append(settings)
        if len(calls) < 4:
            raise RuntimeError("no network")
        await asyncio.sleep(3600)

    async def main():
        real_sleep = asyncio.sleep

        async def fake_sleep(delay):
            if 1 <= delay < 3600:
                sleeps.append(delay)
            await real_sleep(0)

        supervisor = Supervisor("S", [BackgroundTask("t", failing, 1.0, 4.0)])
        asyncio.sleep = fake_sleep  # type: ignore[assignment]
        try:
            supervisor.start()
            await until(lambda: supervisor.status()["t"]["restarts"] == 3)
            await until(lambda: supervisor.status()["t"]["state"] == "running")
        finally:
            asyncio.sleep = real_sleep  # type: ignore[assignment]
        status = supervisor.status()["t"]
        await supervisor.stop()
        return status

    status = run(main())
    assert calls == ["S"] * 4
    assert sleeps[:3] == [1.0, 2.0, 4.0]  # (up to the limit)
    assert status["last_error"] == "RuntimeError: no network"


def test_a_long_run_starts_the_delay_again():
    delays = []
    runs = []

    async def flaky(settings):
        runs.append(1)
        if len(runs) == 3:
            await asyncio.sleep(0.05)  # (a long run, with reset_after 0.01)
        if len(runs) < 5:
            raise RuntimeError("x")
        await asyncio.sleep(3600)

    async def main():
        real_sleep = asyncio.sleep

        async def fake_sleep(delay):
            if delay >= 1:
                delays.append(delay)
                await real_sleep(0)
            else:
                await real_sleep(delay)

        asyncio.sleep = fake_sleep  # type: ignore[assignment]
        try:
            supervisor = Supervisor(
                None, [BackgroundTask("t", flaky, 1.0, 100.0, 0.01)]
            )
            supervisor.start()
            await until(lambda: len(runs) == 5)
        finally:
            asyncio.sleep = real_sleep  # type: ignore[assignment]
        await supervisor.stop()

    run(main())
    assert [d for d in delays if d < 3600] == [1.0, 2.0, 1.0, 2.0]


def test_a_task_that_returns_is_not_started_again():
    calls = []

    async def once(settings):
        calls.append(1)

    async def main():
        supervisor = Supervisor(None, [BackgroundTask("t", once)])
        supervisor.start()
        await until(lambda: supervisor.status()["t"]["state"] == "finished")
        await asyncio.sleep(0.05)
        await supervisor.stop()

    run(main())
    assert calls == [1]


def test_stopping_cancels_the_tasks_and_leaves_none_running():
    cancelled = []

    async def forever(settings):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.append(1)
            raise

    async def main():
        supervisor = Supervisor(
            None, [BackgroundTask("a", forever), BackgroundTask("b", forever)]
        )
        supervisor.start()
        await until(
            lambda: all(s["state"] == "running" for s in supervisor.status().values())
        )
        await supervisor.stop()
        assert supervisor._running == {}
        return {
            t
            for t in asyncio.all_tasks()
            if t.get_name().startswith("pangloss-background")
        }

    assert run(main()) == set()
    assert cancelled == [1, 1]


def test_a_task_that_will_not_stop_is_reported(caplog):
    finish = []

    async def stubborn(settings):
        while not finish:
            try:
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                pass

    async def main():
        supervisor = Supervisor(None, [BackgroundTask("stubborn", stubborn)])
        supervisor.start()
        await until(lambda: supervisor.status()["stubborn"]["state"] == "running")
        await supervisor.stop(timeout=0.05)
        finish.append(1)
        await asyncio.sleep(0.05)

    with caplog.at_level("WARNING", logger="pangloss.api.background"):
        run(main())
    assert "stubborn did not stop" in caplog.text


def test_two_tasks_with_one_name_are_refused():
    async def main():
        async def nothing(settings): ...

        Supervisor(
            None, [BackgroundTask("t", nothing), BackgroundTask("t", nothing)]
        ).start()

    with pytest.raises(ValueError, match="two background tasks"):
        run(main())


API = """
    from pangloss_api.background import BackgroundTask
    import asyncio

    events = []

    async def watch(settings):
        events.append("started")
        try:
            await asyncio.sleep(3600)
        finally:
            events.append("stopped")

    def configure_app(app, settings):
        app.state.background_tasks.append(BackgroundTask("watcher", watch))
"""


def test_the_server_starts_an_apps_tasks_and_stops_them_at_shutdown(
    settings, tmp_path, monkeypatch
):
    import sys

    monkeypatch.syspath_prepend(str(tmp_path))
    package = tmp_path / "taskapp"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "api.py").write_text(textwrap.dedent(API))
    try:
        Settings(INSTALLED_APPS=["taskapp"])
        app = create_app()
        from taskapp import api

        with TestClient(app):
            assert app.state.supervisor.status()["watcher"]["state"] in (
                "running",
                "waiting",
            )
            # (the loop has run by the time the first request is answered)
            assert api.events == ["started"] or api.events == []
        assert api.events[-1] == "stopped"
        assert app.state.supervisor._running == {}
    finally:
        for module in [m for m in sys.modules if m.split(".")[0] == "taskapp"]:
            del sys.modules[module]
