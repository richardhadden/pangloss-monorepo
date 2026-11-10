"""What a person does to make a Zotero item a project class, and to undo it (implementation_docs/zotero-sources.md, "Turning an item into
a project class by hand"):

- `base_on`: an item of the fallback class (a `ZoteroObject`, unless a class says `fallback=True`) becomes a `Book`,
  in place: it keeps its id, its URLs and what refers to it (`changing_class_from`), and takes what the form gives.
- `link_item`: a `Book` made by hand becomes an item. If the item is not a node yet, it takes the item's fields and
  address. If it is (a node of the fallback class), the two are merged, keeping **the node that something refers
  to**, so that nothing has to be re-pointed; if both are referred to, it is refused.
- `unlink_item`: the `Book` keeps its id, its own fields and what refers to it, and loses the Zotero fields and the
  address; the item is written again as a new node of the fallback class.

The fields the sync owns come from the item, never from what a person sends. Zotero may have the type wrong (a book
entered as a document): the person says what it is (`item_type_override`), and that is what the class is asked
about (`accepts`)."""

import datetime
import re
from typing import Any
from uuid import UUID

from pangloss_models import ModelRegistry, PanglossClassChangeError
from pydantic import AnyHttpUrl, ValidationError

from pangloss_zotero import config, convert
from pangloss_zotero.client import ZoteroClient
from pangloss_zotero.mapping import accepts, build_table
from pangloss_zotero.models import OWNED_FIELDS, ZoteroBacked
from pangloss_zotero.store import ModelStore, with_required_lists

ITEM_URL = re.compile(
    r"^https://www\.zotero\.org/((?:groups|users)/\d+)/items/([A-Za-z0-9]+)/?$"
)

# The fields the sync owns, which a person never gives
SYNC_FIELDS = (*OWNED_FIELDS, "removed_from_zotero")
# What a node has of the item: those, and what a person said of its type
ITEM_FIELDS = (*SYNC_FIELDS, "item_type_override")

type Summary = dict[str, Any]


class LinkError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def summary(view: Any) -> Summary:
    return {"id": view.id, "type": view.type, "label": view.label}


def fallback() -> type[ZoteroBacked]:
    """The class of the items no project class stands for: what a person turns into one"""
    return build_table().fallback


def target_class(model_name: str) -> type[ZoteroBacked]:
    """A class that an item can be made into by hand: concrete, built on `ZoteroBacked`, not the fallback"""
    cls = ModelRegistry.all_models().get(model_name)
    if (
        cls is None
        or not isinstance(cls, type)
        or not issubclass(cls, ZoteroBacked)
        or cls._meta.abstract
        or cls is fallback()
    ):
        raise LinkError(
            422, f"{model_name} is not a model that can be linked to Zotero"
        )
    return cls


def item_fields(edit: Any) -> dict[str, Any]:
    return {name: getattr(edit, name, None) for name in ITEM_FIELDS}


def referred_by(cls: type, view: Any) -> list[Any]:
    """What refers to an entity (its view's incoming fields)"""
    return [
        item
        for name in cls._meta.field_definitions.incoming_fields
        for item in getattr(view, name, None) or []
    ]


def check_accepts(cls: type[ZoteroBacked], item_type: str | None) -> None:
    if item_type and not accepts(cls, item_type):
        raise LinkError(
            422,
            f"A {cls.__name__} cannot be a Zotero {item_type}. If Zotero has the type wrong, set "
            "item_type_override to what it is",
        )


async def find_item(item: UUID | str) -> tuple[type[ZoteroBacked], Any]:
    """The node of an item, by its id or its Zotero address, read for editing; refused unless it is of the fallback
    class (one that is of a project class has been decided already)"""
    store = ModelStore()
    found = None
    if isinstance(item, UUID) or not str(item).startswith("http"):
        try:
            id: UUID | AnyHttpUrl = item if isinstance(item, UUID) else UUID(str(item))
        except ValueError:
            raise LinkError(404, f"There is no Zotero item {item}") from None
    else:
        id = AnyHttpUrl(str(item))
    for model in store.classes:
        found = await model.get(id)  # type: ignore[misc]
        if found is not None:
            break
    if found is None or not found.zotero_key:
        raise LinkError(404, f"There is no Zotero item {item}")
    plain = fallback()
    if found.type != plain.__name__:
        raise LinkError(
            409,
            f"{found.zotero_url} is already in the database as {found.type} “{found.label}”",
        )
    edit = await plain.get_for_edit(found.id)  # type: ignore[misc]
    return plain, edit


async def change_class(
    cls: type[ZoteroBacked], old: type, data: dict[str, Any], version: int
) -> Any:
    try:
        return await cls.Update(**data).save(  # type: ignore[call-arg]
            expected_version=version, changing_class_from=old, detail=True
        )
    except PanglossClassChangeError as error:
        raise LinkError(409, str(error)) from error


def form_data(cls: type[ZoteroBacked], data: dict[str, Any]) -> dict[str, Any]:
    """What a person's form gives for a new `cls`, checked by its `Create`, without the fields the sync owns (but with
    `item_type_override`, which a person says)"""
    given = {
        k: v
        for k, v in data.items()
        if k not in ("id", "type", "createNew", "create_new")
    }
    try:
        created = cls.Create.model_validate({**given, "type": cls.__name__})  # type: ignore[attr-defined]
    except ValidationError as error:
        raise LinkError(422, str(error)) from error
    dumped = created.model_dump(exclude={"id", "create_new"})
    return {k: v for k, v in dumped.items() if k not in SYNC_FIELDS}


async def base_on(
    settings: Any, model_name: str, item: UUID | str, data: dict[str, Any]
) -> Summary:
    """Make an item (by its id or address) a `model_name`, with what a person's form gives (`data`, as for a new one)"""
    cls = target_class(model_name)
    plain, edit = await find_item(item)
    given = form_data(cls, data)
    fields = item_fields(edit)
    # (what the person says of the type, if they say it, over what the item's node said)
    if override := given.pop("item_type_override", None):
        fields["item_type_override"] = override
    check_accepts(cls, fields["item_type_override"] or fields["item_type"])
    urls = [
        *edit.urls,
        *(u for u in given.pop("urls", None) or [] if u not in edit.urls),
    ]
    view = await change_class(
        cls,
        plain,
        {**given, **fields, "id": edit.id, "type": cls.__name__, "urls": urls},
        edit.meta.version,
    )
    return summary(view)


async def link_item(
    settings: Any, client: ZoteroClient, model_name: str, id: UUID, zotero_url: str
) -> Summary:
    """Make a node made by hand an item of the library (by the item's address). Gives the node that is the item now:
    another one, if the item was a node already and something referred to it"""
    cls = target_class(model_name)
    match = ITEM_URL.match(zotero_url.strip())
    if match is None:
        raise LinkError(
            422,
            "A Zotero item's address looks like https://www.zotero.org/groups/123/items/ABCD1234",
        )
    library, key = match.groups()
    if library not in config.libraries(settings):
        raise LinkError(422, f"{library} is not one of the libraries that are synced")

    edit = await cls.get_for_edit(id)  # type: ignore[misc]
    if edit is None:
        raise LinkError(404, f"There is no {model_name} with id {id}")
    if edit.zotero_key:
        raise LinkError(409, f"This is already linked to {edit.zotero_url}")

    address = convert.item_url(library, key)
    if await ModelStore()._read(AnyHttpUrl(address)) is not None:
        return await merge(cls, edit, address)

    item = await client.item(library, key)
    if item is None:
        raise LinkError(404, f"{library} has no item {key}")
    fields = convert.stamp(convert.convert(item, library), _now())
    if fields["item_type"] in config.skip_types(settings):
        raise LinkError(
            422, f"A Zotero {fields['item_type']} is not a text that can be linked"
        )
    check_accepts(cls, edit.item_type_override or fields["item_type"])

    data = edit.model_dump(exclude={"meta"})
    data.update(fields)
    # (0: not a version the sync made, so the node counts as edited by a person, which it has been)
    data["zotero_synced_entity_version"] = 0
    data["urls"] = [*edit.urls, AnyHttpUrl(address)]
    await cls.Update(**data).save(expected_version=edit.meta.version)  # type: ignore[call-arg]
    return summary(await cls.get(edit.id))  # type: ignore[misc]


async def merge(cls: type[ZoteroBacked], edit: Any, address: str) -> Summary:
    """A node made by hand (`edit`) and the node of an item, one: the one that something refers to is kept"""
    plain, item = await find_item(address)
    fields = item_fields(item)
    if edit.item_type_override:
        fields["item_type_override"] = edit.item_type_override
    check_accepts(cls, fields["item_type_override"] or fields["item_type"])

    made_view = await cls.get(edit.id)  # type: ignore[misc]
    item_view = await plain.get(item.id)  # type: ignore[misc]
    to_made, to_item = referred_by(cls, made_view), referred_by(plain, item_view)
    if to_made and to_item:
        names = lambda found: ", ".join(f"“{r.label}”" for r in found)  # noqa: E731
        raise LinkError(
            409,
            f"Both are referred to, so they cannot be joined without changing what refers to them: the Zotero item "
            f"by {names(to_item)}, and this {cls.__name__} by {names(to_made)}",
        )
    own = edit.model_dump(exclude={"meta", *ITEM_FIELDS})

    if not to_item:
        # (the item's node is let go of: its address goes to the node made by hand, then it is deleted)
        await free_urls(plain, item)
        try:
            await cls.Update(  # type: ignore[call-arg]
                **{**own, **fields, "urls": [*edit.urls, *item.urls]}
            ).save(expected_version=edit.meta.version)
        except Exception:
            await give_back_urls(plain, item)
            raise
        await plain.delete(item.id)  # type: ignore[misc]
        return summary(await cls.get(edit.id))  # type: ignore[misc]

    # (the node made by hand is let go of: the item's node becomes one of its class, with what it held)
    if edit.urls:
        await free_urls(cls, edit)
    try:
        view = await change_class(
            cls,
            plain,
            {
                **own,
                **fields,
                "id": item.id,
                "type": cls.__name__,
                "urls": [*item.urls, *edit.urls],
            },
            item.meta.version,
        )
    except Exception:
        if edit.urls:
            await give_back_urls(cls, edit)
        raise
    await cls.delete(edit.id)  # type: ignore[misc]
    return summary(view)


async def free_urls(cls: type, edit: Any) -> None:
    current = await cls.get_for_edit(edit.id)  # type: ignore[attr-defined]
    await cls.Update(**{**current.model_dump(exclude={"meta"}), "urls": []}).save(  # type: ignore[attr-defined]
        expected_version=current.meta.version
    )


async def give_back_urls(cls: type, edit: Any) -> None:
    current = await cls.get_for_edit(edit.id)  # type: ignore[attr-defined]
    await cls.Update(  # type: ignore[attr-defined]
        **{**current.model_dump(exclude={"meta"}), "urls": edit.urls}
    ).save()


async def unlink_item(settings: Any, model_name: str, id: UUID) -> Summary:
    """Take an item off a node of a project class: the item is a node of the fallback class again. Gives that node"""
    cls = target_class(model_name)
    edit = await cls.get_for_edit(id)  # type: ignore[misc]
    if edit is None:
        raise LinkError(404, f"There is no {model_name} with id {id}")
    if not edit.zotero_url:
        raise LinkError(409, f"This {model_name} is not linked to a Zotero item")
    address = edit.zotero_url
    fields = item_fields(edit)
    kept = {
        **edit.model_dump(exclude={"meta"}),
        **{name: None for name in ITEM_FIELDS},
        "urls": [u for u in edit.urls if str(u) != str(AnyHttpUrl(address))],
    }
    await cls.Update(**kept).save(expected_version=edit.meta.version)  # type: ignore[call-arg]

    plain = fallback()
    label = fields["citation"] or fields["title"] or fields["zotero_key"]
    try:
        await plain.Create(  # type: ignore[call-arg]
            id=AnyHttpUrl(address),
            create_new=True,
            **with_required_lists(
                plain, {**fields, "label": label, "zotero_synced_entity_version": 1}
            ),
        ).save()
    except Exception:
        # (the item goes back on the node, so that it is not lost)
        current = await cls.get_for_edit(id)  # type: ignore[misc]
        await cls.Update(  # type: ignore[call-arg]
            **{**current.model_dump(exclude={"meta"}), **fields, "urls": edit.urls}
        ).save()
        raise
    return summary(await plain.get(AnyHttpUrl(address)))  # type: ignore[misc]


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)
