"""A typology's operations: creating a type, moving it, the tree, the path, a type as it is viewed, merging, deleting, and
switching a type on as the other class (`also`).

Reading is done from all the types of the typology (`graph.types`, a vocabulary is small), and the hierarchy is checked
before it is written and again in the transaction that writes it (`graph.move`). A change that would leave the vocabulary
invalid is `Refused`, with the reason.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pangloss_models.model_registry import ModelRegistry
from pydantic import BaseModel

from pangloss_typology import graph, tree
from pangloss_typology.graph import Refused
from pangloss_typology.tree import Row, Rows
from pangloss_typology.typology import (
    IS_CONCRETE,
    IS_SUBTYPE_OF,
    Typology,
    language_field,
    languages_of,
    unmanaged_labels,
)

__all__ = ["NotFound", "Refused"]

LIMIT = 50
MAX_LIMIT = 500


class NotFound(LookupError):
    """There is no such type"""


class TypeRef(BaseModel):
    id: UUID
    label: str


class TypeOut(TypeRef):
    labels: dict[str, str] = {}
    """The label in each other language that has one: `{"de": "Sekretär"}` (`label` is the default language)"""
    description: str | None = None
    is_concrete: bool = False
    """Also the other class (`also`)"""
    supertype: UUID | None = None


class SubtypeOut(TypeRef):
    subtype_count: int
    """Its direct subtypes"""
    entity_count: int
    """The entities with it, and with its subtypes (or with it alone, if the view leaves the subtypes out)"""


class EntityRef(BaseModel):
    type: str
    id: UUID
    label: str


class Entities(BaseModel):
    total: int
    items: list[EntityRef]
    next: str | None = None
    """Pass as `after` for the next page"""


class TypeView(TypeOut):
    parents: list[TypeRef]
    """From the type's own parent up to the root"""
    subtypes: list[SubtypeOut]
    """The direct subtypes"""
    entities: Entities


def label_of(typology: type[Typology]) -> str:
    return typology._typology_meta.name


def out_of(typology: type[Typology], row: Row) -> TypeOut:
    labels = {}
    for code in languages_of(typology._typology_meta):
        text = row.properties.get(language_field(code))
        if text:
            labels[code] = text
    return TypeOut(
        id=UUID(row.id),
        label=row.label,
        labels=labels,
        description=row.properties.get("description"),
        is_concrete=bool(row.properties.get(IS_CONCRETE)),
        supertype=UUID(row.parent) if row.parent else None,
    )


def ref_of(row: Row) -> TypeRef:
    return TypeRef(id=UUID(row.id), label=row.label)


async def rows_of(typology: type[Typology]) -> Rows:
    return await graph.types(label_of(typology))


async def row_of(typology: type[Typology], id: UUID | str) -> tuple[Rows, Row]:
    rows = await rows_of(typology)
    row = rows.get(str(id))
    if row is None:
        raise NotFound(f"There is no {label_of(typology)} {id}")
    return rows, row


# --- changing ----------------------------------------------------------------------------------------


async def create(
    typology: type[Typology],
    label: str,
    *,
    supertype: UUID | str | None = None,
    description: str | None = None,
    labels: dict[str, str] | None = None,
    **fields: Any,
) -> TypeOut:
    """A new type, below `supertype` (a root without it). `labels` are the labels in other languages by code. The
    fields of `also` that a type cannot know take the typology's `defaults`"""
    name = label_of(typology)
    values: dict[str, Any] = {**typology.new_values(), "label": label, **fields}
    if description is not None:
        values["description"] = description
    for code, text in (labels or {}).items():
        field = language_field(code)
        if field not in typology.Type.model_fields:
            raise Refused(f"A {name} has no label in the language {code!r}")
        values[field] = text
    if supertype is not None:
        await row_of(typology, supertype)  # (it must be there)
        values[IS_SUBTYPE_OF] = [{"type": name, "id": str(supertype)}]
    made = await typology.Type.Create(**values).save()  # ty: ignore[unresolved-attribute]
    return await get(typology, made.id)


async def get(typology: type[Typology], id: UUID | str) -> TypeOut:
    _, row = await row_of(typology, id)
    return out_of(typology, row)


async def move(
    typology: type[Typology], id: UUID | str, to: UUID | str | None = None
) -> TypeOut:
    """Make `to` the supertype of the type (a root, for `None`). Refused if that would put it below itself"""
    rows, row = await row_of(typology, id)
    if to is not None:
        await row_of(typology, to)
    if tree.would_loop(rows, row.id, str(to) if to is not None else None):
        raise Refused(
            "A type cannot be moved below itself or below one of its own subtypes"
        )
    await graph.move(label_of(typology), row.id, str(to) if to is not None else None)
    return await get(typology, id)


async def update(
    typology: type[Typology],
    id: UUID | str,
    *,
    label: str | None = None,
    description: str | None = None,
    labels: dict[str, str] | None = None,
) -> TypeOut:
    """Change what a type says of itself (its label, its description, its labels in other languages) as an entity is
    changed: a new version, and the hierarchy as it was. What is not given is left as it is"""
    name = label_of(typology)
    await row_of(typology, id)
    changes: dict[str, Any] = {}
    if label is not None:
        if not label.strip():
            raise Refused("A type needs a label")
        changes["label"] = label.strip()
    if description is not None:
        changes["description"] = description
    for code, text in (labels or {}).items():
        field = language_field(code)
        if field not in typology.Type.model_fields:
            raise Refused(f"A {name} has no label in the language {code!r}")
        changes[field] = text
    edit = await typology.Type.get_for_edit(UUID(str(id)))  # ty: ignore[unresolved-attribute]
    if edit is None:
        raise NotFound(f"There is no {name} {id}")
    data = {**edit.model_dump(by_alias=False), **changes}
    await typology.Type.Update(**data).save(expected_version=edit.meta.version)  # ty: ignore[unresolved-attribute]
    return await get(typology, id)


async def set_concrete(typology: type[Typology], id: UUID | str, on: bool) -> TypeOut:
    """Switch the type on or off as the `also` class. For a typology that is `always` also, or is not, it is refused"""
    meta = typology._typology_meta
    if meta.also is None:
        raise Refused(f"A {meta.name} is not also anything")
    if meta.concrete == "always":
        raise Refused(f"A {meta.name} is always also a {meta.also.__name__}")
    await row_of(typology, id)
    await graph.set_concrete(meta.name, str(id), on, unmanaged_labels(meta.also))
    return await get(typology, id)


async def delete(typology: type[Typology], id: UUID | str) -> None:
    """Delete a type. Refused while it has subtypes, or anything has it as a type or refers to it (merge it, or move
    those, first)"""
    rows, row = await row_of(typology, id)
    below = tree.children_of(rows, row.id)
    if below:
        raise Refused(
            f"It has subtypes ({', '.join(r.label for r in below[:5])}): move or delete them first"
        )
    users = await graph.uses(label_of(typology), row.id)
    if users:
        names = ", ".join(f"{u['label']}" for u in users[:5])
        raise Refused(
            f"It is in use by {names}"
            + (" and more" if len(users) > 5 else "")
            + ": merge it into another type, or change those first"
        )
    await typology.Type.delete(UUID(row.id))  # ty: ignore[unresolved-attribute]


async def merge(
    typology: type[Typology], from_: UUID | str, into: UUID | str
) -> TypeOut:
    """Everything that has the first type has the second, its subtypes become the second's, and the first is deleted"""
    if str(from_) == str(into):
        raise Refused("A type cannot be merged into itself")
    await row_of(typology, from_)
    await row_of(typology, into)
    await graph.merge(label_of(typology), str(from_), str(into))
    await typology.Type.delete(UUID(str(from_)))  # ty: ignore[unresolved-attribute]
    return await get(typology, into)


# --- reading -----------------------------------------------------------------------------------------


async def tree_of(typology: type[Typology]) -> list[dict[str, Any]]:
    """The whole hierarchy: `[{"id", "label", "children": [...]}]`, each level by label"""
    return tree.nested(await rows_of(typology))


async def path(typology: type[Typology], id: UUID | str) -> list[TypeRef]:
    """From the root to the type itself"""
    rows, row = await row_of(typology, id)
    return [ref_of(r) for r in tree.path(rows, row.id)]


async def ancestors(typology: type[Typology], id: UUID | str) -> list[TypeRef]:
    """The supertypes, from the type's own parent up to the root"""
    rows, row = await row_of(typology, id)
    return [ref_of(r) for r in tree.ancestors(rows, row.id)]


async def descendants(typology: type[Typology], id: UUID | str) -> list[TypeRef]:
    """Everything below the type"""
    rows, row = await row_of(typology, id)
    return [ref_of(r) for r in tree.descendants(rows, row.id)]


def entity_type_of(labels: list[str]) -> str:
    """The class of an entity from its node's labels: the most specific of the models"""
    models = ModelRegistry.all_models()
    known = [name for name in labels if name in models]
    if not known:
        return next((name for name in labels if name != "Entity"), "Entity")
    return max(known, key=lambda name: len(models[name].__mro__))


async def entities(
    typology: type[Typology],
    id: UUID | str,
    *,
    include_subtypes: bool = True,
    entity_type: str | None = None,
    limit: int = LIMIT,
    after: str | None = None,
) -> Entities:
    """The entities that have the type (and, by default, any type below it), by label"""
    _, row = await row_of(typology, id)
    limit = max(1, min(limit, MAX_LIMIT))
    total, found = await graph.entities_of(
        label_of(typology),
        row.id,
        include_subtypes=include_subtypes,
        entity_type=entity_type,
        limit=limit,
        after=after,
    )
    page = found[:limit]
    return Entities(
        total=total,
        items=[
            EntityRef(
                type=entity_type_of(item["labels"]),
                id=item["id"],
                label=item["label"] or "",
            )
            for item in page
        ],
        next=graph.cursor_of(page[-1]["label"] or "", page[-1]["id"])
        if len(found) > limit and page
        else None,
    )


async def view(
    typology: type[Typology],
    id: UUID | str,
    *,
    include_subtypes: bool = True,
    entity_type: str | None = None,
    limit: int = LIMIT,
    after: str | None = None,
) -> TypeView:
    """A type as it is viewed: itself, its parents, its direct subtypes (each with its counts) and the entities that
    have it"""
    rows, row = await row_of(typology, id)
    subtypes = tree.children_of(rows, row.id)
    counts = await graph.entity_counts(
        label_of(typology), [r.id for r in subtypes], include_subtypes
    )
    return TypeView(
        **out_of(typology, row).model_dump(),
        parents=[ref_of(r) for r in tree.ancestors(rows, row.id)],
        subtypes=[
            SubtypeOut(
                **ref_of(r).model_dump(),
                subtype_count=len(tree.children_of(rows, r.id)),
                entity_count=counts.get(r.id, 0),
            )
            for r in subtypes
        ],
        entities=await entities(
            typology,
            row.id,
            include_subtypes=include_subtypes,
            entity_type=entity_type,
            limit=limit,
            after=after,
        ),
    )


# --- loading and dumping a vocabulary ------------------------------------------------------------------


@dataclass
class Loaded:
    created: int = 0
    existing: int = 0


def labels_in(typology: type[Typology], entry: dict[str, Any]) -> dict[str, str]:
    """The labels in other languages of an entry of a file: `label_de` is German"""
    found = {}
    for code in languages_of(typology._typology_meta):
        text = entry.get(language_field(code))
        if text:
            found[code] = str(text)
    return found


async def load(
    typology: type[Typology],
    entries: list[dict[str, Any]],
    *,
    below: UUID | str | None = None,
) -> Loaded:
    """Make the types of a nested file: `[{"label": "Official", "label_de": "Beamter", "description": "...", "children": [...]}]`.
    A type that is already there (the same label under the same supertype, ignoring case) is left as it is, so a file
    can be loaded again; the report says how many were made. A label in a language the typology does not have is
    refused before anything is made."""
    known = {language_field(code) for code in languages_of(typology._typology_meta)}

    def check(items: list[dict[str, Any]], where: str) -> None:
        for item in items:
            if not isinstance(item, dict) or not str(item.get("label", "")).strip():
                raise Refused(f"Every type in the file needs a label (in {where})")
            extra = sorted(k for k in item if k.startswith("label_") and k not in known)
            if extra:
                raise Refused(
                    f"{item['label']}: no label in the language of {', '.join(extra)}"
                )
            check(item.get("children", []), item["label"])

    check(entries, "the top level")
    rows = await rows_of(typology)
    report = Loaded()

    async def make(items: list[dict[str, Any]], parent: str | None) -> None:
        for item in items:
            label = str(item["label"]).strip()
            match = next(
                (
                    r
                    for r in tree.children_of(rows, parent)
                    if r.label.casefold() == label.casefold()
                ),
                None,
            )
            if match is not None:
                report.existing += 1
                id = match.id
            else:
                made = await create(
                    typology,
                    label,
                    supertype=parent,
                    description=item.get("description"),
                    labels=labels_in(typology, item),
                )
                report.created += 1
                id = str(made.id)
                rows[id] = Row(id=id, label=label, parent=parent)
            await make(item.get("children", []), id)

    await make(entries, str(below) if below is not None else None)
    return report


async def dump(typology: type[Typology]) -> list[dict[str, Any]]:
    """The vocabulary as `load` reads it: nested, each level by label, with what each type has"""
    rows = await rows_of(typology)
    codes = languages_of(typology._typology_meta)

    def node(row: Row) -> dict[str, Any]:
        entry: dict[str, Any] = {"label": row.label}
        for code in codes:
            text = row.properties.get(language_field(code))
            if text:
                entry[language_field(code)] = text
        if row.properties.get("description"):
            entry["description"] = row.properties["description"]
        if children := tree.children_of(rows, row.id):
            entry["children"] = [node(c) for c in children]
        return entry

    roots = sorted(
        (r for r in rows.values() if r.parent is None or r.parent not in rows),
        key=tree.sort_key,
    )
    return [node(r) for r in roots]
