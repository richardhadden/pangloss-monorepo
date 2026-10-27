"""The real store, against a live Memgraph (skipped when there is none)"""

import datetime

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.entity import Entity
from pangloss_zotero import ZoteroBacked, ZoteroItemType, ZoteroMeta
from pangloss_zotero.convert import convert, item_url, stamp
from pangloss_zotero.mapping import build_table
from pangloss_zotero.store import (
    ModelStore,
    ZoteroModelError,
    acting_as,
    ensure_sync_user,
)
from pangloss_zotero.sync import LibraryState, sync_library
from pydantic import AnyHttpUrl
from zotero_support import LIBRARY, FakeZotero, make_item

pytestmark = pytest.mark.asyncio(loop_scope="session")


class Settings:
    ZOTERO_LIBRARIES = [LIBRARY]
    ZOTERO_API_KEY = "key"


NOW = datetime.datetime(2026, 10, 27, 12, 0, tzinfo=datetime.UTC)
SYNC = "zotero_sync"


def models():
    from pangloss_models.model_registry import ModelRegistry
    from pangloss_zotero import ZoteroLibrary, ZoteroObject

    # (the registry is emptied for each test: the models of the package are put back)
    for model in (ZoteroBacked, ZoteroObject, ZoteroLibrary):
        model._initialised = False
        ModelRegistry.register(model)

    class Place(Entity):
        pass

    class TextObject(ZoteroBacked):
        shelfmark: str | None = None
        written_in: list[Place]

    class Atlas(TextObject):
        _zotero_meta = ZoteroMeta(item_types=[ZoteroItemType.BOOK])

    class Mention(Entity):
        about: TextObject

    initialise()
    return Place, TextObject, Atlas, Mention


def url(key: str) -> AnyHttpUrl:
    return AnyHttpUrl(item_url(LIBRARY, key))


async def run_sync(zotero: FakeZotero, **kwargs):
    await ensure_sync_user(SYNC)
    client = zotero.client()
    try:
        with acting_as(SYNC):
            return await sync_library(
                client, ModelStore(), build_table(), LIBRARY, **kwargs
            )
    finally:
        await client.close()


async def test_a_synced_item_is_an_entity_of_the_class_for_its_type(live_db):
    Place, TextObject, Atlas, Mention = models()
    zotero = FakeZotero()
    zotero.put(make_item("AAAA", "book", "An Atlas"))
    zotero.put(make_item("BBBB", "letter", "A Letter"))

    report = await run_sync(zotero)

    assert (report.created, report.errors) == (2, [])
    atlas = await Atlas.get(url("AAAA"))
    assert atlas.title == "An Atlas"
    assert atlas.item_type == "book"
    assert atlas.label == "(Smith, AAAA)"
    assert atlas.creators == "Smith, Anne"
    assert atlas.meta.created_by == SYNC
    assert atlas.zotero_synced_entity_version == atlas.meta.version == 1
    assert url("AAAA") in atlas.urls
    # (no class stands for letters, and none is the fallback: a ZoteroObject)
    from pangloss_zotero import ZoteroObject

    letter = await ZoteroObject.get(url("BBBB"))
    assert letter.type == "ZoteroObject"


async def test_the_state_of_the_library_is_kept(live_db):
    models()
    zotero = FakeZotero()
    zotero.put(make_item("AAAA"))
    await run_sync(zotero)

    store = ModelStore()
    state = await store.library_state(LIBRARY)
    assert (
        state.synced_version == 1
        and state.last_error is None
        and state.last_sync is not None
    )

    await store.save_library_state(LIBRARY, LibraryState(5, NOW, "it broke"))
    state = await store.library_state(LIBRARY)
    assert (state.synced_version, state.last_error) == (5, "it broke")


async def test_a_sync_keeps_what_a_person_added_and_notices_the_edit(live_db):
    Place, TextObject, Atlas, Mention = models()
    zotero = FakeZotero()
    zotero.put(make_item("AAAA", "book", "An Atlas"))
    await run_sync(zotero)
    place = await Place.Create(label="Rome").save()

    # a person adds a shelfmark and a relation
    edit = await Atlas.get_for_edit(url("AAAA"))
    await Atlas.Update(
        **{
            **edit.model_dump(exclude={"meta"}),
            "shelfmark": "MS 12",
            "written_in": [{"type": "Place", "id": place.id}],
        }
    ).save(expected_version=edit.meta.version)
    store = ModelStore()
    existing = await store.find(str(url("AAAA")))
    assert existing.edited_by_person

    zotero.put(make_item("AAAA", "book", "An Atlas, revised"))
    report = await run_sync(zotero)

    assert report.updated == 1
    atlas = await Atlas.get(url("AAAA"))
    assert atlas.title == "An Atlas, revised"
    assert atlas.shelfmark == "MS 12"
    assert [p.id for p in atlas.written_in] == [place.id]
    assert atlas.meta.version == 3
    assert atlas.zotero_synced_entity_version == 3
    assert not (await store.find(str(url("AAAA")))).edited_by_person


async def test_a_factoid_can_name_an_item_before_it_is_synced_and_the_sync_fills_it_in(
    live_db,
):
    Place, TextObject, Atlas, Mention = models()
    await Mention.Create(
        label="A mention",
        about={
            "type": "TextObject",
            "id": url("AAAA"),
            "label": "Stub for AAAA",
            "create_new": True,
            "written_in": [],
        },
    ).save()
    stub = await TextObject.get(url("AAAA"))
    assert stub.label == "Stub for AAAA" and stub.zotero_key is None

    zotero = FakeZotero()
    zotero.put(make_item("AAAA", "book", "An Atlas"))
    report = await run_sync(zotero)

    # (one node, which keeps the class it was made as, and now has the Zotero fields)
    assert (report.created, report.updated) == (0, 1)
    item = await TextObject.get(url("AAAA"))
    assert item.id == stub.id and item.type == "TextObject"
    assert item.title == "An Atlas" and item.zotero_key == "AAAA"
    assert item.label == "(Smith, AAAA)"
    assert [m.label for m in item.about_reverse] == [
        "A mention"
    ]  # (what cited the stub cites the item)


async def test_deletions_follow_whether_the_item_is_used(live_db):
    Place, TextObject, Atlas, Mention = models()
    zotero = FakeZotero()
    for key in ("FREE", "USED"):
        zotero.put(make_item(key, "book"))
    await run_sync(zotero)
    await Mention.Create(label="m", about={"type": "Atlas", "id": url("USED")}).save()

    zotero.remove("FREE")
    zotero.remove("USED")
    report = await run_sync(zotero)

    assert (report.deleted, report.removed) == (1, 1)
    assert await Atlas.get(url("FREE")) is None
    used = await Atlas.get(url("USED"))
    assert used.removed_from_zotero is True
    assert used.meta.marked_for_deletion in (None, False)  # (it was not even tried)

    # a deleted item that is in Zotero again is restored
    zotero.put(make_item("FREE", "book", "Back again"))
    report = await run_sync(zotero)
    assert (report.restored, report.created) == (1, 0)
    free = await Atlas.get(url("FREE"))
    assert free.title == "Back again"


async def test_a_class_with_a_required_field_the_sync_cannot_give_is_explained(live_db):
    class Strict(ZoteroBacked):
        must_have: str

    initialise()
    await ensure_sync_user(SYNC)
    with acting_as(SYNC), pytest.raises(
        ZoteroModelError,
        match="Strict cannot be made from a Zotero item: must_have is required",
    ):
        await ModelStore().create(
            "Strict", stamp(convert(make_item("AAAA"), LIBRARY), NOW)
        )


async def test_a_text_object_made_by_hand_is_linked_to_an_item(live_db):
    from pangloss_zotero.link import LinkError, link_item
    from pangloss_zotero.store import acting_as  # noqa: F401

    Place, TextObject, Atlas, Mention = models()
    zotero = FakeZotero()
    zotero.put(make_item("AAAA", "book", "An Atlas"))
    zotero.put(make_item("LLLL", "letter", "A Letter"))
    made = await Atlas.Create(label="My atlas", shelfmark="MS 1", written_in=[]).save()

    class S(Settings):
        ZOTERO_LIBRARIES = [LIBRARY]

    client = zotero.client()
    address = item_url(LIBRARY, "AAAA")

    # an Atlas cannot be a letter
    with pytest.raises(LinkError, match="cannot be a Zotero letter"):
        await link_item(S, client, "Atlas", made.id, item_url(LIBRARY, "LLLL"))
    # ... unless the person says Zotero has it wrong, and that it is a book
    edit = await Atlas.get_for_edit(made.id)
    await Atlas.Update(
        **{**edit.model_dump(exclude={"meta"}), "item_type_override": "book"}
    ).save(expected_version=edit.meta.version)
    await link_item(S, client, "Atlas", made.id, item_url(LIBRARY, "LLLL"))

    linked = await Atlas.get(made.id)
    assert linked.title == "A Letter" and linked.zotero_key == "LLLL"
    assert linked.shelfmark == "MS 1"
    assert AnyHttpUrl(item_url(LIBRARY, "LLLL")) in linked.urls
    assert (await Atlas.get(AnyHttpUrl(item_url(LIBRARY, "LLLL")))).id == made.id

    # the sync then finds that node by the address, and treats it as edited by a person
    store = ModelStore()
    existing = await store.find(item_url(LIBRARY, "LLLL"))
    assert existing.id == made.id and existing.edited_by_person

    # linking again, or to an item that is already a node, is refused
    with pytest.raises(LinkError, match="already linked"):
        await link_item(S, client, "Atlas", made.id, address)
    await run_sync(zotero)  # (AAAA becomes a node of its own)
    other = await Atlas.Create(label="Another", written_in=[]).save()
    with pytest.raises(LinkError, match="already in the database"):
        await link_item(S, client, "Atlas", other.id, address)
    with pytest.raises(LinkError, match="no item"):
        await link_item(S, client, "Atlas", other.id, item_url(LIBRARY, "NOPE"))
    with pytest.raises(LinkError, match="not one of the libraries"):
        await link_item(
            S, client, "Atlas", other.id, "https://www.zotero.org/groups/9/items/AAAA"
        )
    with pytest.raises(LinkError, match="looks like"):
        await link_item(S, client, "Atlas", other.id, "https://example.com/x")
    await client.close()
