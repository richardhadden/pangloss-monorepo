# Typology: a vocabulary of types in a hierarchy

`pangloss-typology` gives entities a **type** drawn from a controlled vocabulary that is itself a hierarchy: "secretary" is
a subtype of "court official", which is a subtype of "official". Asking for everything typed "court official" finds the
secretaries too.

## Declaring one

Add `"pangloss_typology"` to `INSTALLED_APPS`, then in your models:

```python
from typing import Annotated
from pangloss_models import Entity
from pangloss_typology import Typed, Typology, TypologyMeta


class Role(Entity):
    has_type: list[Typed[RoleTypology]]          # annotated_types.MaxLen(1) to allow only one


class RoleTypology(Typology):
    _typology_meta = TypologyMeta(name="RoleType")
```

`Typology` generates an entity class, here `RoleType` (also `RoleTypology.Type`), with a `label`, a `description`, a
`supertype`, and a `label_<code>` for each other language of `INTERFACE_LANGUAGES` (so no migration is needed to add a
language). It is an ordinary entity: lists, autocomplete, search, history and review work on it. The rules, all checked
when the class is made:

- The class is called `…Typology`, inherits directly from `Typology` (a subvocabulary is a subtype, not a subclass), and
  has a `_typology_meta` whose `name` ends in `Type`.
- A model has at most one `Typed[…]` field for a given typology. The edge is always `has_type` (reverse `type_of`),
  whatever you hope to call the field, so the field is called `has_type`.
- Use `Typed[RoleTypology]`, not the bare class.

Then make and apply the migration (the generated entity belongs to the app that declares the typology):

```bash
pangloss makemigrations
pangloss migrate
```

### A type that is also a concrete entity

Sometimes a type is itself a thing: "Pope" the office type, and "Pope Leo X"'s role. `TypologyMeta(name="RoleType",
also=Role)` makes `RoleType` a `Role` too. A type is then only usable *as* a role where it is switched on (`is_concrete`),
so a relation to `Role` does not accept every type by accident.

## Using it

```python
from pangloss_typology import service        # or on the class: RoleTypology.create(...), etc.

official  = await RoleTypology.create("Court official")
secretary = await RoleTypology.create("Secretary", supertype=official.id)
await RoleTypology.move(secretary.id, to=chancery.id)       # re-parent (to=None: make it a root)
await RoleTypology.tree()                                    # [{id, label, children: [...]}, ...]
await RoleTypology.path(secretary.id)                        # its ancestors and itself, from the root down
await RoleTypology.merge(from_=a.id, into=b.id)              # repoint everything typed a, then delete a
await RoleTypology.delete(id)                                # refused if it has subtypes or is in use

await Role.Create(label="Maximilian's secretary", has_type=[{"type": "RoleType", "id": secretary.id}]).save()
```

A type is deleted only when it has no subtypes and nothing has it. That holds for the entity's own route too:
`DELETE /api/RoleType/{id}` on a type in use answers 409 with the reason and changes nothing (it does not mark the type
for deletion, as it would any other entity that is referred to). Merge it into another type, or change what has it, first.

Two types side by side (below the same supertype, or both at the top level) cannot have the same name, ignoring case:
making, renaming or moving one so that they would is refused (409). If they are the same thing, `merge` them. Under
different supertypes the same name is fine.

`move` and `merge` keep the hierarchy a tree: a move to the type itself or to a descendant is refused (409), the move is
one transaction, and two racing moves take a lock so that the loser is refused instead of making a loop. Any type at any
level may be given to an entity.

To see a type with its parents, direct subtypes (each with counts) and the entities that have it, use
`RoleTypology.view(id, include_subtypes=True)`.

## Loading a vocabulary

```bash
pangloss typology load RoleType roles.jsonc --user ada      # types are made as this (existing) user
pangloss typology dump RoleType --to roles.jsonc
pangloss typology tree RoleType
```

The file is nested as the hierarchy is:

```jsonc
[
  {"label": "Official", "label_de": "Beamter", "children": [
    {"label": "Court official", "children": [{"label": "Secretary"}]}
  ]}
]
```

Loading is repeatable: a type already there (the same label under the same supertype) is left alone.

## HTTP

| | |
|---|---|
| `GET /api/typology/RoleType/tree` | The whole hierarchy in one query |
| `GET /api/typology/RoleType/{id}` | A type viewed: parents, subtypes with counts, entities (`include_subtypes`, `entity_type`, `limit`, `after`) |
| `GET /api/typology/RoleType/{id}/path` | The ancestors, for breadcrumbs |
| `POST /api/typology/RoleType` | A new type: `{"label", "supertype": id or null, "description", "labels"}` (201) |
| `PATCH /api/typology/RoleType/{id}` | Label, description, labels in other languages |
| `POST /api/typology/RoleType/{id}/move` | `{"to": id or null}` |
| `PUT /api/typology/RoleType/{id}/concrete` | Switch the concrete entity on or off |

`supertype` and `is_concrete` are protected: the ordinary entity endpoints will not change them, only these do.
In these routes, and in the `pangloss typology` commands, the typology is named by its entity (`RoleType`) or by its own
name (`RoleTypology`).

## Not yet

The tree picker for relation fields in the interface (autocomplete works, since types are entities); the structured-search
operator "under this type" (`$under`); API routes to create, merge and delete a type (use the entity's own endpoints or the
service); SKOS and other formats for loading. [Typology: implementation spec](../../docs/typology-implementation.md) has the
design and where it differs.
