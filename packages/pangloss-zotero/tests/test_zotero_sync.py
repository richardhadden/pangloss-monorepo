"""One sync of a library, with a Zotero and a store that are dicts"""

import asyncio

import httpx2 as httpx
import pytest
from pangloss_zotero.client import ZoteroAuthError, ZoteroError
from pangloss_zotero.convert import item_url
from pangloss_zotero.mapping import TypeTable
from pangloss_zotero.models import ZoteroObject
from pangloss_zotero.sync import sync_library
from zotero_support import LIBRARY, FakeZotero, MemoryStore, make_item


def sync(zotero: FakeZotero, store: MemoryStore, **kwargs):
    async def main():
        client = zotero.client()
        try:
            return await sync_library(client, store, TypeTable(), LIBRARY, **kwargs)
        finally:
            await client.close()

    return asyncio.run(main())


def url(key: str) -> str:
    return item_url(LIBRARY, key)


def test_the_first_sync_creates_every_item_and_stores_the_version():
    zotero, store = FakeZotero(), MemoryStore()
    for key in ("AAAA", "BBBB"):
        zotero.put(make_item(key))

    report = sync(zotero, store)

    assert (report.created, report.updated, report.errors) == (2, 0, [])
    assert set(store.nodes) == {url("AAAA"), url("BBBB")}
    node = store.nodes[url("AAAA")]
    assert node["_model"] == "ZoteroObject"
    assert node["label"] == "(Smith, AAAA)"
    assert node["creators"] == "Smith, Anne"
    assert store.states[LIBRARY].synced_version == zotero.version == 2


def test_a_second_sync_with_nothing_changed_writes_nothing():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))
    sync(zotero, store)
    store.writes.clear()

    report = sync(zotero, store)

    assert store.writes == []
    assert (report.created, report.updated, report.unchanged) == (0, 0, 0)
    # (Zotero was told the version held, and answered "not modified")
    assert zotero.requests[-1].headers["If-Modified-Since-Version"] == "1"


def test_only_the_item_that_changed_is_written_again():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))
    zotero.put(make_item("BBBB"))
    sync(zotero, store)
    store.writes.clear()

    zotero.put(make_item("BBBB", title="A better title"))
    report = sync(zotero, store)

    assert store.writes == [("update", url("BBBB"))]
    assert report.updated == 1
    assert store.nodes[url("BBBB")]["title"] == "A better title"
    assert store.nodes[url("BBBB")]["zotero_version"] == 3


def test_a_full_sync_reads_everything_but_changes_only_what_differs():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))
    zotero.put(make_item("BBBB"))
    sync(zotero, store)
    store.writes.clear()

    report = sync(zotero, store, full=True)

    assert (report.unchanged, report.updated, report.created) == (2, 0, 0)
    assert store.writes == []


def test_a_library_of_many_items_is_fetched_fifty_keys_at_a_time():
    zotero, store = FakeZotero(), MemoryStore()
    for n in range(120):
        zotero.put(make_item(f"K{n:04d}"))

    report = sync(zotero, store)

    item_requests = [r for r in zotero.requests if r.url.path.endswith("/items")]
    assert [len(r.url.params["itemKey"].split(",")) for r in item_requests] == [
        50,
        50,
        20,
    ]
    assert report.created == 120


def test_attachments_and_notes_are_skipped_and_counted():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))
    zotero.put(make_item("NOTE", item_type="note"))
    zotero.put(make_item("FILE", item_type="attachment"))

    report = sync(zotero, store)

    assert set(store.nodes) == {url("AAAA")}
    assert report.skipped == {"note": 1, "attachment": 1}
    assert store.states[LIBRARY].synced_version == 3  # (skipped is not a failure)


def test_an_item_in_the_trash_is_flagged_and_unflagged_when_it_comes_back():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))
    sync(zotero, store)

    zotero.trash("AAAA")
    report = sync(zotero, store)
    assert store.nodes[url("AAAA")]["removed_from_zotero"] is True
    assert report.removed == 1

    zotero.put(make_item("AAAA"))  # (out of the trash)
    sync(zotero, store)
    assert store.nodes[url("AAAA")]["removed_from_zotero"] is None


def test_an_item_deleted_for_good_that_nothing_uses_is_deleted():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))
    sync(zotero, store)

    zotero.remove("AAAA")
    report = sync(zotero, store)

    assert report.deleted == 1
    assert store.nodes[url("AAAA")]["_deleted"] is True


def test_an_item_deleted_for_good_that_something_refers_to_is_kept_and_flagged():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))
    sync(zotero, store)
    store.referenced.add(url("AAAA"))

    zotero.remove("AAAA")
    report = sync(zotero, store)

    assert report.deleted == 0 and report.removed == 1
    node = store.nodes[url("AAAA")]
    assert node["_deleted"] is False
    assert node["removed_from_zotero"] is True
    assert node["citation"] == "(Smith, AAAA)"  # (it can still be cited)


def test_an_item_deleted_for_good_that_a_person_has_edited_is_kept_and_flagged():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))
    sync(zotero, store)
    store.person_edits("AAAA")

    zotero.remove("AAAA")
    sync(zotero, store)

    assert store.nodes[url("AAAA")]["_deleted"] is False
    assert store.nodes[url("AAAA")]["removed_from_zotero"] is True


def test_an_item_that_was_deleted_here_and_is_in_zotero_again_is_restored():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))
    sync(zotero, store)
    zotero.remove("AAAA")
    sync(zotero, store)  # (deleted)

    zotero.put(make_item("AAAA", title="Back"))
    report = sync(zotero, store)

    node = store.nodes[url("AAAA")]
    assert node["_deleted"] is False
    assert node["title"] == "Back"
    assert (report.restored, report.created) == (1, 0)


def test_an_item_that_cannot_be_written_is_reported_and_the_version_is_not_stored():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))
    zotero.put(make_item("BBBB"))
    store.fail_for.add(url("AAAA"))

    report = sync(zotero, store)

    assert report.created == 1
    assert len(report.errors) == 1 and "AAAA" in report.errors[0]
    assert store.states[LIBRARY].synced_version == 0
    assert "could not be written" in (store.states[LIBRARY].last_error or "")

    # (it works the next time, and the one that was written is left alone)
    store.fail_for.clear()
    report = sync(zotero, store)
    assert (report.created, report.unchanged, report.errors) == (1, 1, [])
    assert store.states[LIBRARY].synced_version == 2
    assert store.states[LIBRARY].last_error is None


def test_a_zotero_that_cannot_be_reached_is_recorded_and_raised():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))
    zotero.script = [httpx.Response(500)]

    with pytest.raises(ZoteroError, match="500"):
        sync(zotero, store)

    assert store.states[LIBRARY].synced_version == 0
    assert "500" in (store.states[LIBRARY].last_error or "")


def test_a_wrong_key_is_an_auth_error_and_is_not_tried_again():
    zotero, store = FakeZotero(), MemoryStore()

    async def main():
        client = zotero.client(key="wrong")
        with pytest.raises(ZoteroAuthError):
            await sync_library(client, store, TypeTable(), LIBRARY)

    asyncio.run(main())
    assert len(zotero.requests) == 1


def test_the_class_for_the_type_comes_from_the_table():
    from pangloss_zotero.models import ZoteroBacked

    class Atlas(ZoteroObject):
        pass

    table = TypeTable({"book": Atlas})
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA", item_type="book"))
    zotero.put(make_item("BBBB", item_type="letter"))

    async def main():
        client = zotero.client()
        await sync_library(client, store, table, LIBRARY)

    asyncio.run(main())
    assert store.nodes[url("AAAA")]["_model"] == "Atlas"
    assert store.nodes[url("BBBB")]["_model"] == "ZoteroObject"
    assert issubclass(Atlas, ZoteroBacked)
