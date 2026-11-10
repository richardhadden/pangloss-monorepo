"""A stored version in the **read form** of the API, as the interface shows an item: camelCase keys, without the
bookkeeping of the write form, and each entity it refers to with its label *as it is now* (a restore refers to the
entities as they are now, too). An entity that has been deleted since has the label it last had and is marked
`deleted` (a restore brings it back); one there is no trace of is marked `missing`. (implementation_docs/history.md)"""

from collections.abc import Awaitable, Callable, Iterable
from typing import Any
from uuid import UUID

from pangloss_models import Entity, ModelRegistry
from pydantic.alias_generators import to_camel

from pangloss_history.restore import called

# Only in the write form: what the graph works out when it is written, and the flag of an entity written inline
WRITE_ONLY = {"create_new", "context_labels", "db_labels", "semantic_spaces"}

Labels = dict[str, str | None]
LookUp = Callable[[str, str], Awaitable[str | None]]
# (the label an entity last had in the history, by its id: for one that is deleted now)
LookBack = Callable[[str], str | None]
# (in `Labels`, under this key before an id: the label of an entity that is not there now)
WAS = "was:"


def recorded_label(store: Any, id: str) -> str | None:
    """The label of an entity in the last version of it that the history has (`None` if it has none)"""
    try:
        head = UUID(id)
    except ValueError:
        return None
    for record in reversed(store.versions(head)):
        full = store.get(head, record.version)
        data = full.data() if full is not None else None
        if isinstance(data, dict) and data.get("label"):
            return data["label"]
    return None


def entity_types() -> set[str]:
    return {
        name
        for name, model in ModelRegistry.all_models().items()
        if isinstance(model, type) and issubclass(model, Entity)
    }


def references(
    data: Any, entities: set[str], head: Any = None
) -> Iterable[tuple[str, str]]:
    """The `(type, id)` of each reference to an entity in the content (not the head node, which may be one)"""
    if isinstance(data, dict):
        if data is not head and data.get("type") in entities and data.get("id"):
            yield data["type"], str(data["id"])
        for value in data.values():
            yield from references(value, entities, head)
    elif isinstance(data, list):
        for item in data:
            yield from references(item, entities, head)


async def look_up_label(type_name: str, id: str) -> str | None:
    """The label of an entity now (`None` if it is not there, or deleted)"""
    model: Any = ModelRegistry.all_models().get(type_name)
    if model is None:
        return None
    found = await called(model.get(id))
    return found.label if found is not None else None


async def labels_of(
    contents: Iterable[Any],
    look_up: LookUp = look_up_label,
    entities: set[str] | None = None,
    look_back: LookBack | None = None,
) -> Labels:
    """The labels now of every entity that the contents refer to, each looked up once; and of one that is not there
    now, the label it last had (under `WAS + id`), if `look_back` knows it"""
    entities = entity_types() if entities is None else entities
    labels: Labels = {}
    for content in contents:
        for type_name, id in references(content, entities, content):
            if id not in labels:
                labels[id] = await look_up(type_name, id)
                if labels[id] is None and look_back is not None:
                    labels[WAS + id] = look_back(id)
    return labels


def to_view(data: Any, labels: Labels, entities: set[str], head: Any = None) -> Any:
    """The content in the read form (`head`: the content itself, whose own label is its own)"""
    if isinstance(data, dict):
        view = {
            to_camel(key): to_view(value, labels, entities)
            for key, value in data.items()
            if key not in WRITE_ONLY
        }
        if data is not head and data.get("type") in entities and data.get("id"):
            label = labels.get(str(data["id"]))
            view["label"] = label
            if label is None:
                was = labels.get(WAS + str(data["id"]))
                if was is None:
                    view["missing"] = True
                else:
                    view["label"], view["deleted"] = was, True
        return view
    if isinstance(data, list):
        return [to_view(item, labels, entities) for item in data]
    return data


async def view_of(
    data: Any, look_up: LookUp = look_up_label, look_back: LookBack | None = None
) -> Any:
    entities = entity_types()
    labels = await labels_of([data], look_up, entities, look_back)
    return to_view(data, labels, entities, data)


async def views_of(
    contents: list[Any],
    look_up: LookUp = look_up_label,
    look_back: LookBack | None = None,
) -> list[Any]:
    """Several versions in the read form, the labels looked up once for all"""
    entities = entity_types()
    labels = await labels_of(contents, look_up, entities, look_back)
    return [to_view(data, labels, entities, data) for data in contents]
