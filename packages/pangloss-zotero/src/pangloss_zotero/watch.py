"""Keeping the libraries up to date: sync once, then listen to Zotero's stream and sync when it says a library
has changed (https://www.zotero.org/support/dev/web_api/v3/websockets).

`watch` is one function: the server runs it as a background task, and `pangloss zotero watch` runs it on its
own (for a deployment with several server workers, where only one should listen).

The stream is told nothing that is not also in the library's version, so an event is only a reason to sync
now: events missed while disconnected are caught up by the sync that follows every reconnect, and events that
arrive during a sync make one more sync, not one each."""

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pangloss_zotero import config
from pangloss_zotero.client import ZoteroAuthError, ZoteroClient, ZoteroError
from pangloss_zotero.mapping import build_table
from pangloss_zotero.store import DryRunStore, ModelStore, acting_as, ensure_sync_user
from pangloss_zotero.sync import Report, Store, sync_library

logger = logging.getLogger("pangloss.zotero.watch")

AUTH_TIMEOUT = 10.0
FIRST_DELAY = 5.0
MAX_DELAY = 300.0
HEALTHY_AFTER = 60.0


class StreamError(Exception):
    pass


def default_connect(url: str):
    from websockets.asyncio.client import connect

    return connect(url)


async def sync_libraries(
    settings: Any,
    libraries: list[str] | None = None,
    *,
    full: bool = False,
    dry_run: bool = False,
    client: ZoteroClient | None = None,
    store: Store | None = None,
) -> list[Report]:
    """One sync of each library (those in the settings, if none are named), as the sync user"""
    names = libraries or config.libraries(settings)
    if not names:
        raise ZoteroError("There is no library to sync: set ZOTERO_LIBRARIES")
    table = build_table()
    own_client = client is None
    client = client or ZoteroClient(config.api_key(settings), config.api_url(settings))
    user = config.sync_user(settings)
    reports = []
    try:
        if store is None:
            store = DryRunStore() if dry_run else ModelStore()
            if not dry_run:
                await ensure_sync_user(user)
        with acting_as(user):
            for library in names:
                report = await sync_library(
                    client,
                    store,
                    table,
                    library,
                    full=full,
                    skip_types=config.skip_types(settings),
                )
                logger.info("%s", report.summary())
                reports.append(report)
    finally:
        if own_client:
            await client.close()
    return reports


async def listen(
    settings: Any,
    libraries: list[str],
    changed: Callable[[str, bool], None],
    *,
    connect: Callable[[str], Any] = default_connect,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    auth_timeout: float = AUTH_TIMEOUT,
) -> None:
    """Hold a connection to the stream for as long as it is cancelled: subscribe, tell `changed(library, ...)`
    of each `topicUpdated`, and after any failure connect again (after a delay that grows). `changed` is also
    told of every library when a connection is made, to catch up with what was missed."""
    topics = [f"/{library}" for library in libraries]
    delay = FIRST_DELAY
    while True:
        began = asyncio.get_running_loop().time()
        try:
            async with connect(config.stream_url(settings)) as socket:
                await subscribe(socket, config.api_key(settings), topics, auth_timeout)
                logger.info("Listening to Zotero for %s", ", ".join(libraries))
                for library in libraries:
                    changed(library, True)
                async for message in socket:
                    event = json.loads(message)
                    if event.get("event") == "topicUpdated":
                        library = str(event.get("topic", "")).lstrip("/")
                        if library in libraries:
                            changed(library, False)
                    elif event.get("event") == "topicRemoved":
                        logger.warning(
                            "Zotero says %s is no longer available: %s",
                            event.get("topic"),
                            event,
                        )
        except asyncio.CancelledError:
            raise
        except StreamError as error:
            logger.error("Zotero's stream: %s", error)
        except OSError as error:  # (no network, or the stream is down: not a fault to give a traceback for)
            logger.warning("Zotero's stream could not be reached: %s", error)
        except Exception:
            logger.exception("The connection to Zotero's stream failed")
        if asyncio.get_running_loop().time() - began >= HEALTHY_AFTER:
            delay = FIRST_DELAY
        logger.info("Connecting to Zotero's stream again in %.0f s", delay)
        await sleep(delay)
        delay = min(delay * 2, MAX_DELAY)


async def subscribe(
    socket: Any, key: str | None, topics: list[str], timeout: float
) -> None:
    """The stream says `connected`; we ask for the topics with the key; it answers `subscriptionsCreated`.
    It sometimes does not answer (the case that hung the earlier plugin): after `timeout` the caller
    connects again."""

    async def read(expected: str) -> dict[str, Any]:
        while True:
            event = json.loads(await asyncio.wait_for(socket.recv(), timeout))
            if event.get("event") == expected:
                return event

    try:
        await read("connected")
        await socket.send(
            json.dumps(
                {
                    "action": "createSubscriptions",
                    "subscriptions": [{"apiKey": key, "topics": topics}],
                }
            )
        )
        created = await read("subscriptionsCreated")
    except TimeoutError as error:
        raise StreamError(f"no answer within {timeout:.0f} s") from error
    problems = created.get("errors") or []
    if problems:
        raise StreamError(f"the subscription was refused: {problems}")


async def watch(
    settings: Any,
    *,
    client: ZoteroClient | None = None,
    store: Store | None = None,
    connect: Callable[[str], Any] = default_connect,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    auth_timeout: float = AUTH_TIMEOUT,
) -> None:
    """Sync every library, and again whenever one changes. Runs until cancelled."""
    libraries = config.libraries(settings)
    if not libraries:
        logger.warning("Zotero: no ZOTERO_LIBRARIES, so nothing to watch")
        return
    build_table()  # (a wrong declaration should stop it now, with its message)
    own_client = client is None
    client = client or ZoteroClient(config.api_key(settings), config.api_url(settings))
    pending: set[str] = set()
    wake = asyncio.Event()

    def changed(library: str, catch_up: bool) -> None:
        pending.add(library)
        wake.set()

    listener = asyncio.create_task(
        listen(
            settings,
            libraries,
            changed,
            connect=connect,
            sleep=sleep,
            auth_timeout=auth_timeout,
        ),
        name="pangloss-zotero-stream",
    )
    pending.update(libraries)
    wake.set()
    try:
        failures = 0
        while True:
            await wake.wait()
            wake.clear()
            batch, pending_now = sorted(pending), set(pending)
            pending.clear()
            try:
                await sync_libraries(settings, batch, client=client, store=store)
                failures = 0
            except ZoteroAuthError as error:
                logger.error("Zotero refused the key: %s", error)
                pending.update(pending_now)
                await sleep(MAX_DELAY)
                wake.set()
            except ZoteroError as error:
                failures += 1
                logger.error("Zotero could not be synced (%s); again in a while", error)
                pending.update(pending_now)
                await sleep(min(FIRST_DELAY * 2**failures, MAX_DELAY))
                wake.set()
    finally:
        listener.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listener
        if own_client:
            await client.close()
