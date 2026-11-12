"""A person makes an item a project class by hand (`base_on`), links a hand-made one to an item that is a node already
(the merge), and unlinks it again. Against the backend under test."""

import pytest
from pangloss_models import Document, Entity, initialise
from pangloss_zotero import ZoteroBacked, ZoteroItemType, ZoteroMeta
from pangloss_zotero.convert import item_url
from pangloss_zotero.link import LinkError, base_on, link_item, unlink_item
from pangloss_zotero.mapping import build_table
from pangloss_zotero.store import ModelStore, acting_as, ensure_sync_user
from pangloss_zotero.sync import sync_library
from pydantic import AnyHttpUrl
from zotero_support import fresh_package_models, LIBRARY, FakeZotero, make_item

pytestmark = pytest.mark.asyncio(loop_scope="session")

SYNC = "zotero_sync"


class Settings:
    ZOTERO_LIBRARIES = [LIBRARY]
    ZOTERO_API_KEY = "key"


def models():
    from pangloss_zotero import ZoteroLibrary, ZoteroObject  # noqa: F401

    # (the registry is emptied for each test: the models of the package are put back, made afresh)
    fresh_package_models()

    class Person(Entity):
        pass

    class Book(ZoteroBacked):
        """Claims no types: every item comes in as a ZoteroObject, and a person makes a Book of it"""

        pages: int | None = None
        written_by: list[Person]

    class Letter(ZoteroBacked):
        _zotero_meta = ZoteroMeta(item_types=[ZoteroItemType.LETTER])

    class Cites(Document):
        # (not `ZoteroBacked`: the registry is emptied for each test, but the classes of earlier tests are still its
        # subclasses, and a relation to it would take them)
        source: ZoteroObject | Book

    class AboutItem(Document):
        item: ZoteroObject

    initialise()
    return Person, Book, Letter, Cites, AboutItem, ZoteroObject


def address(key: str) -> str:
    return item_url(LIBRARY, key)


async def run_sync(zotero: FakeZotero):
    await ensure_sync_user(SYNC)
    client = zotero.client()
    try:
        with acting_as(SYNC):
            return await sync_library(client, ModelStore(), build_table(), LIBRARY)
    finally:
        await client.close()


async def synced(zotero: FakeZotero, ZoteroObject, *keys: str):
    for key in keys:
        zotero.put(make_item(key, "book", f"Title {key}"))
    await run_sync(zotero)
    return [await ZoteroObject.get(AnyHttpUrl(address(key))) for key in keys]


def cite(item):
    return {"type": item.type, "id": item.id}


async def test_an_item_becomes_a_book_and_stays_a_zotero_item(live_db):
    Person, Book, _, Cites, _, ZoteroObject = models()
    zotero = FakeZotero()
    (item,) = await synced(zotero, ZoteroObject, "AAAA")
    citation = await Cites.Create(label="Cites it", source=cite(item)).save()
    author = await Person.Create(label="An author").save()

    made = await base_on(
        Settings,
        "Book",
        str(item.id),
        {
            "label": "My book",
            "pages": 10,
            "writtenBy": [{"type": "Person", "id": str(author.id)}],
            # (the fields the sync owns come from the item, whatever the form says)
            "title": "Not the title",
        },
    )

    assert made == {"id": item.id, "type": "Book", "label": "My book"}
    book = await Book.get(item.id)
    assert book.pages == 10 and [p.id for p in book.written_by] == [author.id]
    assert book.title == "Title AAAA" and book.zotero_key == "AAAA"
    assert AnyHttpUrl(address("AAAA")) in book.urls
    assert await ZoteroObject.get(item.id) is None
    assert (await Cites.get(citation.id)).source.type == "Book"

    # it has happened: again is refused
    with pytest.raises(LinkError, match="already in the database as Book") as error:
        await base_on(Settings, "Book", str(item.id), {"label": "Again"})
    assert error.value.status == 409

    # the sync keeps its Zotero fields, and it stays a Book
    zotero.put(make_item("AAAA", "book", "A new title"))
    await run_sync(zotero)
    book = await Book.get(item.id)
    assert book.title == "A new title" and book.pages == 10


async def test_an_item_can_be_found_by_its_address_to_be_based_on(live_db):
    _, Book, _, _, _, ZoteroObject = models()
    zotero = FakeZotero()
    (item,) = await synced(zotero, ZoteroObject, "AAAA")
    made = await base_on(
        Settings, "Book", address("AAAA"), {"label": "My book", "writtenBy": []}
    )
    assert made["id"] == item.id


async def test_what_cannot_be_based_on_an_item_is_refused(live_db):
    _, Book, Letter, _, AboutItem, ZoteroObject = models()
    zotero = FakeZotero()
    first, second = await synced(zotero, ZoteroObject, "AAAA", "BBBB")

    for model, message in [
        ("Person", "not a model"),
        ("ZoteroObject", "not a model"),
        ("ZoteroBacked", "not a model"),
        ("Letter", "cannot be a Zotero book"),
    ]:
        with pytest.raises(LinkError, match=message) as error:
            await base_on(Settings, model, str(first.id), {"label": "x"})
        assert error.value.status == 422

    # ... unless the person says Zotero has the type wrong
    made = await base_on(
        Settings, "Letter", str(first.id), {"label": "x", "itemTypeOverride": "letter"}
    )
    letter = await Letter.get(first.id)
    assert made["type"] == "Letter" and letter.item_type_override == "letter"
    assert letter.item_type == "book"

    # something refers to it by a relation that cannot hold a Book
    await AboutItem.Create(label="About it", item=cite(second)).save()
    with pytest.raises(LinkError, match="AboutItem") as error:
        await base_on(Settings, "Book", str(second.id), {"label": "x", "writtenBy": []})
    assert error.value.status == 409
    assert (await ZoteroObject.get(second.id)) is not None

    with pytest.raises(LinkError, match="no Zotero item") as error:
        await base_on(Settings, "Book", address("NOPE"), {"label": "x"})
    assert error.value.status == 404


async def test_linking_a_book_to_an_item_that_nothing_refers_to_keeps_the_book(
    live_db,
):
    _, Book, _, Cites, _, ZoteroObject = models()
    zotero = FakeZotero()
    (item,) = await synced(zotero, ZoteroObject, "AAAA")
    book = await Book.Create(label="My book", pages=5, written_by=[]).save()
    citation = await Cites.Create(label="Cites the book", source=cite(book)).save()

    kept = await link_item(Settings, zotero.client(), "Book", book.id, address("AAAA"))

    assert kept["id"] == book.id
    linked = await Book.get(book.id)
    assert linked.zotero_key == "AAAA" and linked.title == "Title AAAA"
    assert linked.pages == 5
    assert (await Book.get(AnyHttpUrl(address("AAAA")))).id == book.id
    assert await ZoteroObject.get(item.id) is None
    assert (await Cites.get(citation.id)).source.id == book.id
    # the sync now finds the Book by the address
    assert (await ModelStore().find(address("AAAA"))).id == book.id


async def test_linking_a_book_to_an_item_that_is_referred_to_keeps_the_item(live_db):
    _, Book, _, Cites, _, ZoteroObject = models()
    zotero = FakeZotero()
    (item,) = await synced(zotero, ZoteroObject, "AAAA")
    citation = await Cites.Create(label="Cites the item", source=cite(item)).save()
    book = await Book.Create(label="My book", pages=5, written_by=[]).save()
    # (a URL of its own, which it gives to the node that is kept: `Create` takes no URLs, but an update does)
    await Book.Update(
        id=book.id,
        label="My book",
        pages=5,
        written_by=[],
        urls=[AnyHttpUrl("https://example.org/my-book")],
    ).save()

    kept = await link_item(Settings, zotero.client(), "Book", book.id, address("AAAA"))

    assert kept == {"id": item.id, "type": "Book", "label": "My book"}
    merged = await Book.get(item.id)
    assert merged.pages == 5 and merged.zotero_key == "AAAA"
    assert {str(u) for u in merged.urls} == {
        address("AAAA"),
        "https://example.org/my-book",
    }
    assert await Book.get(book.id) is None
    assert (await Cites.get(citation.id)).source.type == "Book"


async def test_linking_is_refused_when_both_are_referred_to(live_db):
    _, Book, _, Cites, _, ZoteroObject = models()
    zotero = FakeZotero()
    (item,) = await synced(zotero, ZoteroObject, "AAAA")
    book = await Book.Create(label="My book", written_by=[]).save()
    await Cites.Create(label="Cites the item", source=cite(item)).save()
    await Cites.Create(label="Cites the book", source=cite(book)).save()

    with pytest.raises(LinkError, match="Cites the item.*Cites the book") as error:
        await link_item(Settings, zotero.client(), "Book", book.id, address("AAAA"))
    assert error.value.status == 409
    assert (await Book.get(book.id)).zotero_key is None
    assert (await ZoteroObject.get(item.id)) is not None


async def test_linking_to_an_item_that_is_already_a_book_is_refused(live_db):
    _, Book, _, _, _, ZoteroObject = models()
    zotero = FakeZotero()
    (item,) = await synced(zotero, ZoteroObject, "AAAA")
    await base_on(Settings, "Book", str(item.id), {"label": "One", "writtenBy": []})
    other = await Book.Create(label="Two", written_by=[]).save()
    with pytest.raises(LinkError, match="already in the database as Book") as error:
        await link_item(Settings, zotero.client(), "Book", other.id, address("AAAA"))
    assert error.value.status == 409


async def test_unlinking_splits_the_book_from_the_item(live_db):
    _, Book, _, Cites, _, ZoteroObject = models()
    zotero = FakeZotero()
    (item,) = await synced(zotero, ZoteroObject, "AAAA")
    citation = await Cites.Create(label="Cites it", source=cite(item)).save()
    await base_on(
        Settings,
        "Book",
        str(item.id),
        {"label": "My book", "pages": 7, "writtenBy": []},
    )

    split = await unlink_item(Settings, "Book", item.id)

    book = await Book.get(item.id)
    assert book.pages == 7 and book.label == "My book"
    assert book.zotero_key is None and book.title is None and book.zotero_url is None
    assert AnyHttpUrl(address("AAAA")) not in book.urls
    # what referred to it still refers to the Book
    assert (await Cites.get(citation.id)).source.id == item.id
    # the item is a node of its own again
    again = await ZoteroObject.get(AnyHttpUrl(address("AAAA")))
    assert again.id != item.id and again.title == "Title AAAA"
    assert split == {"id": again.id, "type": "ZoteroObject", "label": again.label}
    # and the sync finds it, not the Book
    assert (await ModelStore().find(address("AAAA"))).id == again.id

    with pytest.raises(LinkError, match="not linked") as error:
        await unlink_item(Settings, "Book", item.id)
    assert error.value.status == 409
    with pytest.raises(LinkError, match="not a model") as error:
        await unlink_item(Settings, "ZoteroObject", again.id)
    assert error.value.status == 422


async def test_an_item_of_the_library_is_the_survivor_of_a_merge_never_the_one_absorbed(
    live_db,
):
    from pangloss_models import PanglossMergeError

    Person, Book, _, Cites, _, ZoteroObject = models()
    zotero = FakeZotero()
    item, other = await synced(zotero, ZoteroObject, "AAAA", "BBBB")
    by_hand = await ZoteroObject.Create(label="Entered by hand").save()
    citation = await Cites.Create(label="Cites it", source=cite(by_hand)).save()

    # (decision 28) the linked one must stay: the sync finds the item by its node
    with pytest.raises(PanglossMergeError, match="merge the other into it"):
        await ZoteroObject.merge(absorb=item.id, into=by_hand.id)
    with pytest.raises(PanglossMergeError, match="Both are items of a Zotero library"):
        await ZoteroObject.merge(absorb=other.id, into=item.id)
    preview = await ZoteroObject.merge_preview(absorb=item.id, into=by_hand.id)
    assert not preview.possible

    result = await ZoteroObject.merge(absorb=by_hand.id, into=item.id)
    assert result.merge.moved == 1
    assert (await Cites.get(citation.id)).source.id == item.id
    # the item is the item still, with what Zotero gave it, and the next sync finds it
    merged = await ZoteroObject.get(item.id)
    assert (merged.zotero_key, merged.title) == ("AAAA", "Title AAAA")
    await run_sync(zotero)
    assert (await ZoteroObject.get(AnyHttpUrl(address("AAAA")))).id == item.id
    assert Person and Book
