"""The watcher: the stream, and syncing when Zotero says a library has changed"""

import asyncio
import json

import pytest
from pangloss_zotero import watch as watch_module
from pangloss_zotero.convert import item_url
from pangloss_zotero.watch import StreamError, subscribe
from zotero_support import LIBRARY, FakeZotero, MemoryStore, make_item


class Settings:
    ZOTERO_API_KEY = "key"
    ZOTERO_LIBRARIES = [LIBRARY]
    ZOTERO_STREAM_URL = "wss://stream.test"


class FakeSocket:
    """A stream: `script` is what the server sends, in order; an `Exception` is raised from the socket; a
    `Callable` is called (to change the world) and sends nothing"""

    def __init__(self, script, sent):
        self.script = list(script)
        self.sent = sent

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send(self, message):
        self.sent.append(json.loads(message))

    async def recv(self):
        while True:
            if not self.script:
                await asyncio.sleep(3600)
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            if callable(item):
                item()
                continue
            return json.dumps(item)

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.recv()


CONNECTED = {"event": "connected", "retry": 10000}
SUBSCRIBED = {"event": "subscriptionsCreated", "subscriptions": [], "errors": []}


def updated(version=1):
    return {"event": "topicUpdated", "topic": f"/{LIBRARY}", "version": version}


async def until(condition, timeout=3.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while not condition():
        if loop.time() > end:
            raise AssertionError("it did not happen")
        await asyncio.sleep(0.005)


def run_watch(zotero, store, connections, check, sleeps=None, settle=0.0):
    """Run the watcher on fake connections (one per script) until `check(sent, opened)` is true, then cancel it"""
    sent: list = []
    scripts = list(connections)
    opened = []

    def connect(url):
        opened.append(url)
        return FakeSocket(scripts.pop(0) if scripts else [], sent)

    async def sleep(seconds):
        if sleeps is not None:
            sleeps.append(seconds)
        await asyncio.sleep(0)

    async def main():
        client = zotero.client()
        task = asyncio.create_task(
            watch_module.watch(
                Settings,
                client=client,
                store=store,
                connect=connect,
                sleep=sleep,
                auth_timeout=0.05,
            )
        )
        try:
            await until(lambda: check(sent, opened))
            await asyncio.sleep(settle)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await client.close()
        leftover = [
            t for t in asyncio.all_tasks() if t.get_name().startswith("pangloss-zotero")
        ]
        assert leftover == []

    asyncio.run(main())
    return sent, opened


def url(key):
    return item_url(LIBRARY, key)


def test_it_syncs_at_the_start_subscribes_with_the_key_and_syncs_again_on_an_update():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))

    def add_item():
        zotero.put(make_item("BBBB"))

    sent, opened = run_watch(
        zotero,
        store,
        [[CONNECTED, SUBSCRIBED, add_item, updated(2)]],
        lambda sent, opened: url("BBBB") in store.nodes,
    )

    assert url("AAAA") in store.nodes
    assert opened == ["wss://stream.test"]
    assert sent == [
        {
            "action": "createSubscriptions",
            "subscriptions": [{"apiKey": "key", "topics": ["/groups/1"]}],
        }
    ]


def test_after_the_connection_drops_it_connects_again_with_a_delay_and_catches_up():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))
    sleeps: list[float] = []

    def add_while_away():
        zotero.put(make_item("MISSED"))

    sent, opened = run_watch(
        zotero,
        store,
        [
            [CONNECTED, SUBSCRIBED, ConnectionError("dropped")],
            [add_while_away, CONNECTED, SUBSCRIBED],
        ],
        lambda sent, opened: url("MISSED") in store.nodes,
        sleeps,
    )

    assert len(opened) == 2
    assert 5.0 in sleeps  # (the first delay; no events came to say about "MISSED")


def test_a_stream_that_does_not_answer_is_connected_to_again():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))

    sent, opened = run_watch(
        zotero,
        store,
        [
            [CONNECTED],
            [CONNECTED, SUBSCRIBED],
        ],  # (the first never says it has subscribed)
        lambda sent, opened: len(opened) == 2 and len(sent) == 2,
    )

    assert len(opened) == 2


def test_a_refused_subscription_is_an_error_that_is_reported():
    async def main():
        script = [
            CONNECTED,
            {"event": "subscriptionsCreated", "errors": [{"error": "Invalid API key"}]},
        ]
        with pytest.raises(StreamError, match="refused"):
            await subscribe(FakeSocket(script, []), "bad", ["/groups/1"], 1.0)

    asyncio.run(main())


def test_events_during_a_sync_make_one_more_sync_not_one_each():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))
    syncs = []
    real = watch_module.sync_libraries

    async def counting(settings, libraries=None, **kwargs):
        await asyncio.sleep(0.05)  # (a slow sync, with events arriving during it)
        result = await real(settings, libraries, **kwargs)
        syncs.append(libraries)
        return result

    watch_module.sync_libraries = counting
    try:
        run_watch(
            zotero,
            store,
            [[CONNECTED, SUBSCRIBED, updated(2), updated(3), updated(4), updated(5)]],
            lambda sent, opened: len(syncs) >= 2,
            settle=0.2,
        )
    finally:
        watch_module.sync_libraries = real
    # (the start; then the connection's catch-up and the four events together)
    assert syncs == [["groups/1"], ["groups/1"]]


def test_a_zotero_that_cannot_be_reached_is_tried_again_later_not_given_up():
    from zotero_support import httpx

    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))
    zotero.script = [httpx.Response(500)]
    sleeps: list[float] = []

    run_watch(
        zotero, store, [[]], lambda sent, opened: url("AAAA") in store.nodes, sleeps
    )

    assert any(s >= 5 for s in sleeps)


def test_an_item_that_could_not_be_written_is_tried_again_without_zotero_saying_anything():
    zotero, store = FakeZotero(), MemoryStore()
    for key in ("AAAA", "BBBB"):
        zotero.put(make_item(key))
    store.fail_for.add(url("AAAA"))
    sleeps: list[float] = []

    def written_at_last(sent, opened):
        # (the first try failed and a later one is waited for: then the database takes it)
        if 10.0 in sleeps:
            store.fail_for.clear()
        return url("AAAA") in store.nodes

    # (the stream says nothing after the subscription)
    run_watch(zotero, store, [[CONNECTED, SUBSCRIBED]], written_at_last, sleeps)

    assert 10.0 in sleeps
    assert store.states[LIBRARY].synced_version == zotero.version
    assert store.states[LIBRARY].last_error is None
    # the item was asked for on its own, not the library again
    alone = [
        request.url.params["itemKey"]
        for request in zotero.requests
        if request.url.path.endswith("/items")
    ]
    assert alone[0] == "AAAA,BBBB" and set(alone[1:]) == {"AAAA"}


def test_a_database_being_migrated_is_waited_for_and_nothing_is_reported_as_failed():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))
    store.read_only = True
    sleeps: list[float] = []

    def done(sent, opened):
        if sleeps:
            store.read_only = False
        return url("AAAA") in store.nodes

    run_watch(zotero, store, [[CONNECTED, SUBSCRIBED]], done, sleeps)

    assert any(s >= 5 for s in sleeps)
    assert store.states[LIBRARY].last_error is None
    assert store.states[LIBRARY].synced_version == zotero.version
