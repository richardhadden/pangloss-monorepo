"""One sync of a library, with a Zotero and a store that are dicts"""

import asyncio

import httpx2 as httpx
import pytest
from pangloss_zotero import ZoteroAuthError, ZoteroError, ZoteroObject
from pangloss_zotero.convert import item_url
from pangloss_zotero.mapping import TypeTable
from pangloss_zotero.sync import Progress, SyncPostponed, stored_version, sync_library
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


def item_requests(zotero: FakeZotero) -> list[list[str]]:
    """The keys of each request for items"""
    return [
        request.url.params["itemKey"].split(",")
        for request in zotero.requests
        if request.url.path.endswith("/items")
    ]


def test_a_long_sync_that_stops_part_way_goes_on_from_where_it_was():
    zotero, store = FakeZotero(), MemoryStore()
    for number in range(120):
        zotero.put(make_item(f"K{number:03d}"))
    # (the versions, two batches of fifty, and then Zotero is away)
    zotero.fail_from_request = 4

    with pytest.raises(ZoteroError, match="500"):
        sync(zotero, store, checkpoint_seconds=0)

    # the hundred that were written are counted as done: the version below the next item's is stored
    assert len(store.nodes) == 100
    assert store.states[LIBRARY].synced_version == 100
    assert store.states[LIBRARY].last_sync is None
    assert store.saved_versions == [50, 100, 100]

    zotero.fail_from_request = None
    zotero.requests.clear()
    report = sync(zotero, store, checkpoint_seconds=0)

    # ... so the rest is all that is asked for
    assert zotero.requests[0].url.params["since"] == "100"
    assert [len(keys) for keys in item_requests(zotero)] == [20]
    assert (report.created, report.unchanged) == (20, 0)
    assert len(store.nodes) == 120
    assert store.states[LIBRARY].synced_version == 120


def test_the_version_is_not_stored_after_every_batch_of_a_sync_that_is_quick():
    zotero, store = FakeZotero(), MemoryStore()
    for number in range(120):
        zotero.put(make_item(f"K{number:03d}"))

    sync(zotero, store)  # (the default: not more often than every thirty seconds)

    assert store.saved_versions == [120]


def test_items_changed_in_one_write_are_not_split_by_the_version_stored():
    zotero, store = FakeZotero(), MemoryStore()
    # (Zotero gives every item of one write the same version: here sixty of them, then one more)
    for number in range(60):
        item = make_item(f"K{number:03d}")
        zotero.items[item["key"]] = {**item, "version": 7}
    zotero.version = 7
    zotero.put(make_item("LAST"))
    zotero.fail_from_request = 3

    with pytest.raises(ZoteroError):
        sync(zotero, store, checkpoint_seconds=0)

    # fifty of the sixty are written, but not all of version 7: so 6 is what is done for certain
    assert len(store.nodes) == 50
    assert store.states[LIBRARY].synced_version == 6


def test_an_item_that_cannot_be_written_does_not_hold_the_rest_back():
    zotero, store = FakeZotero(), MemoryStore()
    for key in ("AAAA", "BBBB", "CCCC"):
        zotero.put(make_item(key))
    store.fail_for.add(url("BBBB"))
    progress = Progress()

    report = sync(zotero, store, progress=progress)

    # the others are written; the version stored is the one below the item that was not
    assert report.created == 2 and len(report.errors) == 1
    assert store.states[LIBRARY].synced_version == 1
    said = store.states[LIBRARY].last_error or ""
    assert "BBBB" in said and "tried again" in said
    assert (progress.read_to, progress.failed) == (3, {"BBBB": 2})

    # the next sync of the same process asks for what is new, and for that item: not for everything again
    zotero.put(make_item("DDDD"))
    zotero.requests.clear()
    report = sync(zotero, store, progress=progress)
    assert zotero.requests[0].url.params["since"] == "3"
    assert item_requests(zotero) == [["BBBB", "DDDD"]]
    assert report.created == 1 and len(report.errors) == 1
    assert store.states[LIBRARY].synced_version == 1

    # ... and when it can be written, the version is that of the library
    store.fail_for.clear()
    zotero.requests.clear()
    report = sync(zotero, store, progress=progress)
    assert item_requests(zotero) == [["BBBB"]]
    assert (report.created, report.errors) == (1, [])
    assert store.states[LIBRARY].synced_version == zotero.version == 4
    assert store.states[LIBRARY].last_error is None
    assert progress.failed == {}


def test_a_new_process_tries_an_item_that_could_not_be_written_again():
    zotero, store = FakeZotero(), MemoryStore()
    for key in ("AAAA", "BBBB", "CCCC"):
        zotero.put(make_item(key))
    store.fail_for.add(url("BBBB"))
    sync(zotero, store, progress=Progress())
    store.fail_for.clear()
    zotero.requests.clear()

    # (nothing is remembered: it starts from the version stored, which is below the item)
    report = sync(zotero, store)

    assert zotero.requests[0].url.params["since"] == "1"
    assert (report.created, report.unchanged, report.errors) == (1, 1, [])
    assert store.states[LIBRARY].synced_version == 3


def test_an_item_to_try_again_that_zotero_no_longer_has_is_forgotten():
    zotero, store = FakeZotero(), MemoryStore()
    zotero.put(make_item("AAAA"))
    store.fail_for.add(url("AAAA"))
    progress = Progress()
    sync(zotero, store, progress=progress)
    assert progress.failed == {"AAAA": 1}

    zotero.remove("AAAA")
    report = sync(zotero, store, progress=progress)

    assert report.errors == [] and progress.failed == {}
    assert store.states[LIBRARY].synced_version == zotero.version
    assert store.states[LIBRARY].last_error is None


def test_a_database_that_is_being_migrated_postpones_the_sync():
    zotero, store = FakeZotero(), MemoryStore()
    for key in ("AAAA", "BBBB"):
        zotero.put(make_item(key))
    sync(zotero, store)
    zotero.put(make_item("CCCC"))
    zotero.put(make_item("AAAA", title="Changed"))
    store.read_only = True
    progress = Progress()

    # (not an error for each item, and the version not stored for it: it stops, to go on later)
    with pytest.raises(SyncPostponed, match="takes no writes now.*from version 2"):
        sync(zotero, store, progress=progress)

    assert store.states[LIBRARY].synced_version == 2
    assert store.states[LIBRARY].last_error is None
    assert progress.failed == {}

    store.read_only = False
    report = sync(zotero, store, progress=progress)
    assert (report.created, report.updated, report.errors) == (1, 1, [])
    assert store.states[LIBRARY].synced_version == zotero.version


def test_a_deletion_that_fails_is_tried_again_and_holds_the_version():
    zotero, store = FakeZotero(), MemoryStore()
    for key in ("AAAA", "BBBB"):
        zotero.put(make_item(key))
    sync(zotero, store)
    zotero.remove("AAAA")
    zotero.put(make_item("CCCC"))
    store.fail_for.add(url("AAAA"))
    progress = Progress()

    report = sync(zotero, store, progress=progress)

    assert len(report.errors) == 1 and report.created == 1
    assert store.states[LIBRARY].synced_version == 2
    assert progress.undeleted == {"AAAA": 3}
    assert not store.nodes[url("AAAA")]["_deleted"]

    store.fail_for.clear()
    report = sync(zotero, store, progress=progress)
    assert (report.deleted, report.errors) == (1, [])
    assert store.nodes[url("AAAA")]["_deleted"]
    assert store.states[LIBRARY].synced_version == zotero.version
    assert progress.undeleted == {}


def test_the_version_stored_is_below_what_failed_and_never_goes_back():
    assert stored_version(0, 120) == 120
    assert stored_version(0, 120, {"A": 40}) == 39
    assert stored_version(0, 120, {"A": 40}, {"B": 12}) == 11
    assert stored_version(50, 120, {"A": 40}) == 50
    assert stored_version(50, 30) == 50


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
    from pangloss_zotero import ZoteroBacked

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
