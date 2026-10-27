"""The Zotero client: versions, items, deletions, and waiting as Zotero asks"""

import asyncio

import httpx2 as httpx
import pytest
from pangloss_zotero.client import ZoteroAuthError, ZoteroError
from zotero_support import LIBRARY, FakeZotero, make_item


def run(coroutine):
    return asyncio.run(coroutine)


def test_the_key_and_the_api_version_are_sent():
    zotero = FakeZotero()
    zotero.put(make_item("AAAA"))

    async def main():
        client = zotero.client()
        await client.item_versions(LIBRARY, 0)

    run(main())
    request = zotero.requests[0]
    assert request.headers["Zotero-API-Key"] == "key"
    assert request.url.params["includeTrashed"] == "1"
    assert "If-Modified-Since-Version" not in request.headers  # (nothing held yet)


def test_nothing_changed_is_answered_with_nothing():
    zotero = FakeZotero()
    zotero.put(make_item("AAAA"))

    async def main():
        client = zotero.client()
        return await client.item_versions(LIBRARY, 1), await client.deleted_items(
            LIBRARY, 1
        )

    assert run(main()) == (({}, 1), [])


def test_a_busy_zotero_is_waited_for_as_it_says():
    zotero = FakeZotero()
    zotero.put(make_item("AAAA"))
    zotero.script = [
        httpx.Response(429, headers={"Retry-After": "7"}),
        httpx.Response(503),
    ]

    async def main():
        client = zotero.client()
        result = await client.item_versions(LIBRARY, 0)
        return result, client.slept

    (versions, version), slept = run(main())
    assert versions == {"AAAA": 1}
    assert slept[0] == 7.0 and slept[1] == 4.0  # (Retry-After; then 2 ** attempt)


def test_a_backoff_header_holds_back_the_next_request():
    zotero = FakeZotero()
    zotero.put(make_item("AAAA"))
    zotero.script = [
        httpx.Response(
            200, json={}, headers={"Backoff": "30", "Last-Modified-Version": "1"}
        )
    ]

    async def main():
        client = zotero.client()
        await client.item_versions(LIBRARY, 0)
        assert client.slept == []
        await client.item_versions(LIBRARY, 0)
        return client.slept

    slept = run(main())
    assert len(slept) == 1 and 29 < slept[0] <= 30


def test_it_gives_up_after_a_few_attempts():
    zotero = FakeZotero()
    zotero.script = [httpx.Response(503)] * 10

    async def main():
        client = zotero.client()
        with pytest.raises(ZoteroError, match="busy"):
            await client.item_versions(LIBRARY, 0)

    run(main())
    assert len(zotero.requests) == 5


def test_a_wrong_key_is_not_tried_again():
    zotero = FakeZotero()

    async def main():
        client = zotero.client(key="wrong")
        with pytest.raises(ZoteroAuthError):
            await client.item_versions(LIBRARY, 0)

    run(main())
    assert len(zotero.requests) == 1


def test_a_network_failure_is_tried_again_and_then_reported():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ConnectError("no route")

    async def main():
        from pangloss_zotero.client import ZoteroClient

        slept = []

        async def sleep(s):
            slept.append(s)

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = ZoteroClient("key", "https://zotero.test", http=http, sleep=sleep)
        with pytest.raises(ZoteroError, match="could not be reached"):
            await client.item_versions(LIBRARY, 0)
        return slept

    slept = run(main())
    assert len(calls) == 5 and slept == [2.0, 4.0, 8.0, 16.0]


def test_more_than_fifty_keys_in_a_request_is_a_mistake():
    async def main():
        with pytest.raises(ValueError):
            await FakeZotero().client().items(LIBRARY, [str(n) for n in range(51)])

    run(main())
