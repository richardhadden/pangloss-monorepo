# Typology: implementation spec 🚧

**Status: built (steps 0 to 2, 4 and most of 5; see [As built](#13-as-built) for what differs and what is left).** The first round of questions is answered ([§12](#12-decisions-and-open-questions)); all its questions are answered. `Role` and `RoleType` are used throughout only as the example: the package knows no particular typology, and any app declares its own (`OfficeTypology`, `PlaceTypology`, ...).

`pangloss-typology` lets an entity be given a *type* from a vocabulary that is itself arranged in a hierarchy: the role "Maximilian's secretary" has the type "secretary", which is a subtype of "court official". It replaces the `TypedSingleton[T[Role], T[Typology]]` idea in [`notes/modelling.md`](../notes/modelling.md).

## 1. What the user writes

```python
from pangloss_typology import Typology, TypologyMeta


class Role(Entity):
    label: str
    role_type: Typed[RoleTypology] | None = None      # (a stored edge :HAS_TYPE, whatever the field is called)


class RoleTypology(Typology):
    _typology_meta = TypologyMeta(name="RoleType")    # must end in "Type"
```

and with the second feature (a type that is also a concrete entity, [§6](#6-a-type-that-is-also-a-concrete-entity)):

```python
class RoleTypology(Typology):
    _typology_meta = TypologyMeta(name="RoleType", also=Role)
```

Rules, all checked when the class is created (`PanglossMetaError` naming the class):

- `RoleTypology` must inherit **directly** from `Typology`. A subclass of a typology (`class X(RoleTypology)`) is an error: there is one vocabulary per typology, and sub-vocabularies are subtypes in the hierarchy, not subclasses.
- `_typology_meta` is required, and `name` must end in `Type` and be more than `Type` (`RoleType` yes; `Type`, `Role`, `RoleTypes` no).
- `name` must not clash with a declared class or with another typology's name.
- `also`, if given, is a concrete (non-abstract) `Entity` subclass.
- The name of the typology class must end in `Typology`.
- A model may have only **one** `Typed[...]` field for a given typology (see [§3](#3-the-graph)).

## 2. What is generated

A `Typology` is an ordinary Python class, **not** a model: it holds the meta, the generated entity and the operations. Making it creates one `Entity`:

```python
RoleTypology.Type      # the generated entity class, named "RoleType"
```

`RoleType` is declared exactly as if the user had written it, so everything that applies to entities applies to it for free (the `Create`/`View`/`Reference` models, the node label `RoleType`, autocomplete, structured search, history, review, the interface's list and item pages):

```python
class RoleType(Entity):               # (and Role, if also=Role)
    label: str                                  # the default language
    label_de: str | None = None                 # one per other language, see §2a
    description: str | None = None
    supertype: Annotated[RoleType | None, RelationConfig(reverse_name="is_supertype_of")] = None
```

The entity belongs to the app that declares the typology (its migrations are the project's or the app's own, like any model). The class is created in `Typology.__init_subclass__`, so `RoleTypology.Type` exists by the time the next line of the module runs and a relation field can use it.

### 2a. Labels in other languages

`label` is the label in the default language (`DEFAULT_INTERFACE_LANGUAGES`). For each other language of `INTERFACE_LANGUAGES` the entity also has an optional `label_<code>` (`label_de`, `label_fr`), added when the models are initialised (the settings are known then, not when the class is made), or from `TypologyMeta(languages=["de"])` if given. They are properties on the node, so adding a language needs no migration. Reading a type in a language uses `label_<code>` and **falls back to `label`**, the same rule as the interface's strings. The interface's editing of a type shows every language side by side with the missing ones marked ([§7](#7-editing-the-hierarchy-in-the-interface)).

## 3. The graph

| Edges | Meaning |
|-------|---------|
| `(entity)-[:HAS_TYPE]->(t:RoleType)` and `(t)-[:TYPE_OF {reverse: true}]->(entity)` | the entity has the type |
| `(sub:RoleType)-[:IS_SUBTYPE_OF]->(super:RoleType)` and `(super)-[:IS_SUPERTYPE_OF {reverse: true}]->(sub)` | the hierarchy |

Every relation is already stored as two edges with a reverse name ([relations](relations.md)), so `IS_SUBTYPE_OF`/`IS_SUPERTYPE_OF` come from one field, `supertype`.

**The edge is always `HAS_TYPE`** (decided), whatever the field is called, so a query for typed things never needs to know field names. Today a relation's edge is named after its field and `RelationConfig` cannot change that, so this needs one small addition to `pangloss_models`: a `relation_name` on `RelationConfig` (also useful elsewhere), which `Typed[...]` sets to `HAS_TYPE` with reverse `TYPE_OF`. Consequences:

- The edges of two different typologies on one model are told apart by the label of the target (`:RoleType` or `:OfficeType`), so they do not collide.
- Two `Typed` fields of the **same** typology on one model would be indistinguishable, so that is a class-creation error (put the second distinction in a relation of its own, e.g. a `Role` with a `held_as_type`).

The queries that matter:

```cypher
// everything with a type at or below "court official"
MATCH (root:RoleType {id: $id})<-[:IS_SUBTYPE_OF*0..]-(t:RoleType)<-[:HAS_TYPE]-(e)
RETURN DISTINCT e
// the path to the root, for display ("Court official › Secretary")
MATCH p = (t:RoleType {id: $id})-[:IS_SUBTYPE_OF*0..]->(root) WHERE NOT (root)-[:IS_SUBTYPE_OF]->() RETURN p
```

Indexes: `RoleType.id` as for every entity, and an index on the edge-less lookup `label`. Nothing else is needed at the sizes a vocabulary has (hundreds to low thousands).

**One supertype per type** (decided): the hierarchy is a tree, a root has none. There is no DAG option; "the path" is unambiguous and drag-and-drop means what it shows.

## 4. The SDK

All on the typology class, all `async`, all going through the same entity machinery (so history and review see the changes):

```python
await RoleTypology.create("Secretary", supertype=official_id)       # -> RoleType view
await RoleTypology.move(secretary_id, to=chancery_id)                # re-parent; to=None makes it a root
await RoleTypology.tree()                                            # [{id, label, children: [...]}, ...]
await RoleTypology.ancestors(id)  /  .descendants(id)  /  .path(id)
await RoleTypology.merge(from_=a_id, into=b_id)                      # repoint HAS_TYPE edges and children, then delete a
await RoleTypology.delete(id)                                        # refuses if it has subtypes or is in use
```

`move` is an ordinary entity update of the type (its `is_subtype_of`), with one thing more, because it must keep the hierarchy valid:

- **No cycles**: `to` may not be the type itself or one of its descendants. Checked first from the tree, and again inside the update's transaction, under the hierarchy's lock (`graph.check_move`, given to the update as `before_write`).
- Moving replaces the one `IS_SUBTYPE_OF` edge.
- It is one transaction, so a failed move changes nothing. As an update, it makes a new version of the type (which `pangloss-history` records), and an edit made from the version before is refused. (Since 2026-11-01; before, `move` wrote the edges itself, and no version changed.)

`merge` writes through the model layer too (since 2026-11-01). The subtypes and everything that has the type (entities, and the documents whose nodes have it) are relinked by the kit's `relink` (`pangloss_cypher.relink`): in batches of 1,000 heads a transaction, each head that changes gets a new version and a write event, and the properties of a `has_type` edge are kept. A move in a merge is an update. `service.merge_counted` says how many subtypes and heads it changed. A merge of a type used by many documents is therefore a large write.

Using a type from a model needs nothing more than the field: `Role.Create(label="Maximilian's secretary", role_type=<reference to the RoleType>)`. Any type at any level may be used (decided).

## 5. The REST API

Mounted under the app's router by a package-level `router(typology)` (the apps include it); the entity's ordinary endpoints (`/RoleType/...`) already exist, so only the hierarchy is new:

| Method and path | Does |
|-----------------|------|
| `GET /typology/RoleType/tree` | the whole tree, one query; what the interface's tree view loads |
| `POST /typology/RoleType/{id}/move` with `{"to": id \| null}` | `move`; `409` with the reason for a cycle or a bad target |
| `GET /typology/RoleType/{id}/path` | ancestors, for breadcrumbs and for showing a chosen type |
| `GET /typology/RoleType/{id}` | **a type as it is viewed** (below) |

**Viewing a type** returns the entity's own view (label, `label_<code>`s, description, and `is_concrete` if any) plus:

```json
{
  "parents": [{"id": "...", "label": "Court official"}, {"id": "...", "label": "Official"}],
  "subtypes": [{"id": "...", "label": "Private secretary", "subtype_count": 0, "entity_count": 3}],
  "entities": {"total": 41, "items": [{"type": "Role", "id": "...", "label": "Maximilian's secretary"}], "next": "..."}
}
```

- `parents`: the supertypes from the type's own parent up to the root (empty for a root); the same as `/path` without the type itself.
- `subtypes`: the **direct** subtypes, each with how many subtypes it has and how many entities (its own and those of its subtypes, to match the default of `entities`), so the tree can show counts and be opened one level at a time.
- `entities`: the entities that have this type (references, of any entity class, since any model may have a `Typed[RoleTypology]` field), paginated and ordered by label. Query parameters: `include_subtypes=false` to list only those of exactly this type (default true: the type and every subtype below it), `entity_type=Role` to list one class, `limit`/`after`. The `total` is given with either setting.
- `entities` found through `HAS_TYPE` are those *typed* by the type. Entities that merely use a switched-on type as a `Role` ([§6](#6-a-type-that-is-also-a-concrete-entity)) are found through that relation's own reverse edge, not listed here.

The SDK has the same as `await RoleTypology.view(id, include_subtypes=True, entity_type=None, limit=50, after=None)`.

Moving requires the same permission as editing the entity.

## 6. A type that is also a concrete entity

The problem: "X was a secretary" is sometimes a specific role (Maximilian's secretary, held 1490–1493) and sometimes only the *kind* (we know X was "a secretary", nothing more). For the second, a singleton `Role` per type is what we do not want. So **the type is itself a `Role`**: one node carrying both labels, which any relation that accepts a `Role` accepts.

```python
class RoleTypology(Typology):
    _typology_meta = TypologyMeta(
        name="RoleType",
        also=Role,
        concrete="per_type",                      # or "always"; the default when `also` is given
        defaults={"holder_known": False},         # values for Role's required fields, see below
    )
# generated:  class RoleType(Entity, Role)
```

`concrete` says when a type is also a `Role`:

| `concrete` | Meaning |
|------------|---------|
| `"per_type"` (default) | each type has a switch, `is_concrete: bool` (`is_concrete`), off when created. **On**: the node gets the label `Role` too. **Off**: it is only a `RoleType` |
| `"always"` | every type is a `Role` from creation; no switch |

Why this works with what exists: a reference is checked by the labels the target node *has* when it is written ([`validate_write.py`](../packages/pangloss-cypher/src/pangloss_cypher/validate_write.py): "is of an allowed type" compares the field's allowed types with the node's labels), so a node that gains the label `Role` is accepted by `Person.has_role: Role`, and one that loses it is refused. Turning the switch is `SET n:Role` / `REMOVE n:Role` in a transaction with the property.

```python
Person.Create(has_role=[<reference to the RoleType "secretary", switch on>])      # "was a secretary", no singleton
Person.Create(has_role=[<reference to the Role "Maximilian's secretary">])        # a specific role
```

**Defaults for `Role`'s fields.** `RoleType` inherits `Role`'s fields, and a type cannot know most of them. So the generated `RoleType` makes them optional-with-a-default for the type's own `Create`, and `defaults` gives the values to use for the required ones (a field with a default in `Role`, or nullable, needs no entry). The check at class creation lists every required field of `also` that has neither, so the declaration says what is missing instead of the first save failing. The switch can be turned on only when the type satisfies `Role`'s validation with those defaults.

**Switching off** is refused while a relation that requires a `Role` points to the type (the message lists them), since it would leave a reference of the wrong type; the user can first move those to another role.

**Queries.** With `"per_type"`, plain `Role` queries return only the types that are switched on as well as real roles; `Role.list(..., concrete_only=True)` (and `NOT :RoleType` in the structured search) leaves the types out. A type that is also a `Role` can itself have a `role_type` (inherited): allowed, not defaulted to itself, and unrelated to `supertype`.

`also` takes one class. In the interface the card of a `RoleType` is drawn as a type (its own colour and a "type" marker) wherever it appears, whether or not it is also a `Role`.

## 7. Editing the hierarchy in the interface

`pangloss-typology` ships an [interface module](interface-modules-implementation.md) (`pangloss_typology/interface/`, npm name `@pangloss-module/pangloss_typology`) that gives the generated entity:

- a **list page** that is a tree: expand/collapse, drag a node onto another to make it a subtype (drop between siblings to make it a root-level sibling), with the server's `409` shown on the node when the move is refused, and optimistic update with rollback;
- an **item page** with the breadcrumb path, the subtypes, and a count and list of what has this type (with and without its subtypes);
- a **view card** with the path in the label ("Court official › Secretary"), in the reader's language with the fallback of [§2a](#2a-labels-in-other-languages);
- **translation editing**: on the item page every language's label is shown side by side (the default first), the missing ones marked, and edited in place;
- a **picker** for the relation field: a searchable tree in place of the flat autocomplete, for fields whose target is a typology's entity. (The generic form is a later phase; the autocomplete works from the start, since the types are entities.)

These are pointed at from `InterfaceMeta` on the generated entity (`list_page="pangloss_typology:TypeTree"`, ...). Keyboard use: a "Move to..." command on each node using the picker, so dragging is never the only way. The tree is plain Solid and Tailwind (no drag-and-drop library beyond the platform's pointer events unless one is shown to be needed).

## 8. Seeding and importing

A vocabulary is data, but a project usually starts with one:

- `pangloss typology load RoleType roles.jsonc` loads a nested file (`{"label": "Official", "label_de": "Beamter", "children": [...]}`), idempotent by label path, so it can be re-run.
- `pangloss typology dump RoleType` writes the same format.
- SKOS and other formats are not part of the first version.

## 9. Search

- The type's entity is searchable as any entity is.
- "Anything with a type at or below X" is the `$typed` operator of the [structured search](structured-search.md) (`{"role_type": {"$under": "<id>"}}`), compiled to the variable-length match in [§3](#3-the-graph). Step 3 below.

## 10. Packaging

```
packages/pangloss-typology/
  pyproject.toml            # depends on pangloss-models; interface optional
  src/pangloss_typology/
    typology.py             # Typology, TypologyMeta, the checks, the class generation
    graph.py                # the queries (tree, entities, uses) and the checks of a move and a merge
    service.py              # the SDK functions
    api.py  cli.py          # router and `pangloss typology ...`
    interface/              # the Solid module (§7), built only with the interface
  tests/
```

`TypologyMeta` does not need registering as a [meta slot](meta-slots.md): a `Typology` is not a model, so `__init_subclass__` reads `_typology_meta` directly. The package ships no migrations of its own (it has no fixed models); the generated entities are the declaring app's and `makemigrations` writes their indexes into that app.

## 11. Steps

0. **In `pangloss_models`**: `RelationConfig(relation_name=...)`, so an edge need not be named after its field.
1. **Declaration**: `Typology`, `TypologyMeta`, `Typed[...]`, the checks, the generated entity with its language labels (with and without `also`); pure tests; the class is usable in a relation field.
2. **Graph and SDK**: `create`, `tree`, `path`, `ancestors`, `descendants`, `move` (cycle check, one transaction), `merge`, `delete`; live tests including the concurrent-move race.
3. **Search and `also`**: the switch (label set and removed), `concrete_only`, the `$under` operator, the defaults check.
4. **API and commands**: the three endpoints, `load`/`dump`.
5. **Interface module**: the tree list page, item page, card; then the picker.

## 12. Decisions and open questions

Decided: one supertype (no DAG); the field is written `Typed[RoleTypology]`; the edge is always `HAS_TYPE`; `also=` with a per-type switch or always on, and defaults for the other class's fields; plain `label` in the default language and optional `label_<code>`s, editable in the interface; any level may be used; the typology class name must end in `Typology`.

| | Was open | Decided |
|---|-----------|---------|
| **Q8** | Where the `label_<code>` fields come from | `INTERFACE_LANGUAGES` at initialise; `TypologyMeta(languages=[...])` overrides |
| **Q9** | Name of the per-type switch | fixed `is_concrete` (the earlier `also_role` is replaced) |
| **Q10** | Is the bare `RoleTypology.Type` accepted? | Yes; documented only as `Typed[RoleTypology]` |

## 13. As built

`packages/pangloss-typology` (26 tests; 19 live tests in `pangloss-memgraph/tests/test_typology_live.py`; 18 for the interface module). To use it, add `pangloss_typology` to `INSTALLED_APPS` (its API routes, commands and interface module are found there), declare a typology as in [§1](#1-what-the-user-writes), then `makemigrations` (the generated entity is the declaring app's) and `migrate`.

**Where it differs from the spec above**

- **The edge is `has_type`, lower case**, as every edge is named after its field here (`is_subtype_of`, `is_supertype_of`, `type_of`). It is enforced by naming, not by a `relation_name` on `RelationConfig` (the edge label is read from the field name in some thirty places, migrations included): a class can say `__relation_names__ = ("has_type", "type_of")` and `initialise()` refuses a relation to it that is called anything else (`fixed_relation_names`). Two `Typed` fields of one typology on a model are therefore impossible (one `has_type` goes to a union of typologies instead).
- **Optional relations do not exist** in the models (`X | None` is for literals), so a field is `has_type: list[Typed[RoleTypology]]` (add `annotated_types.MaxLen(1)` to allow one), and `is_subtype_of` is a list of at most one.
- **A `Create` requires every field** that is not `X | None = None`, so the service fills what a type cannot know (`Typology.new_values()`: the empty supertype, `defaults`, empty lists) and `is_concrete` is `bool | None` (none: off).
- **`Typed[RoleTypology]` and `RoleTypology.Type` are accepted; the bare `RoleTypology` is not** (there is nothing to turn it into a model at the annotation).
- **The switch** is done with `__labels_unmanaged__` on the generated class (its `Create` and `Update` never put or take away the labels of `also`; `service.set_concrete` does) and `has_allowed_label` in `pangloss_models/model_bases/labels.py`, used by the reference checks of `validate_write.py`: a relation that accepts `Role` accepts a `RoleType` node only if it has the label `Role`. `is_subtype_of` and `is_concrete` are protected from the API (`_protect_meta`), so only the typology endpoints change them.
- **A moved type takes a lock.** Edges made by different transactions do not conflict in Memgraph, and three racing moves did make a loop (found by `test_racing_moves_never_make_a_loop`), so `move` and `merge` first write a node of their own per typology (`:TypologyLock`); one of two racing moves waits (about a second) and is then refused by its own check.
- **The card** marks a type with "type" but does not show the path: a card in a list has no cheap way to get it.
- **2026-11-06, after the smoke test**: (1) **The entity's own `DELETE /api/RoleType/{id}` follows the typology's
  rule.** It used to mark a type in use for deletion (as for any entity that is referred to) and leave it in the
  tree, on what had it and in every search. The type's `Protection` now has `delete_refused`
  (`typology.delete_refused`, which asks `service.why_not_deletable`): 409 with the reason ("Banker is in use by
  ... and 615 more: merge it into another type, or change those first"), nothing marked, and `/deletable` says the
  same, so the interface's Delete dialog shows it. A leaf that nothing has is deleted. (2) **Two types side by side
  cannot have the same name** (ignoring case): `create`, `update` (a new label) and `move` refuse it
  (`service.check_no_namesake`), since `load` already takes the label under a supertype for the type. The same name
  under different supertypes is allowed. Not checked: a type written as a plain entity (`POST /api/RoleType`,
  `RoleType.Create(...).save()`), and `merge`, which is how two that exist are made one. (3) **A typology is found
  by either name**: `RoleType` (its entity) or `RoleTypology` (itself), in the routes and the commands
  (`Typology.named`). (4) **The entity is importable and typed**: `RoleType` is put in the module that declares the
  typology (`from app.models import RoleType`), the stubs have it, and `Typed[RoleTypology]` type-checks
  (`Typed` is generic). The languages of a typology's labels are a *model setting* (`INTERFACE_LANGUAGES`,
  `DEFAULT_INTERFACE_LANGUAGE`), so an SDK's models have the same label fields as the server's ([SDK](sdk.md),
  phase 8).
- **2026-11-04, the interface** ([typology-implementation.md#14-the-tree-in-the-interface-drag-and-drop-a-live-tree-inline-labels-plan-of-2026-11-04-built](typology-implementation.md#14-the-tree-in-the-interface-drag-and-drop-a-live-tree-inline-labels-plan-of-2026-11-04-built)): the tree follows the server
  through a `live()` server function (`treeFeed`, polling the tree every `PANGLOSS_TYPOLOGY_POLL_MS`, 3000 ms); a type is
  moved only by dragging (onto the middle of a row: below it; onto its top or bottom edge: beside it), with no "Move to…"
  list and no top-level strip; a pencil on each row edits the label in place; moves and labels are shown at once and
  undone if the server refuses. Both pages restyled. Types are made in a dialog (each chip's "add a subtype", "Add a
  top-level type", the console's New), through the new `POST /api/typology/{name}`.
- **Added**: `PATCH /api/typology/{name}/{id}` (label, description, labels in other languages, as a new version of the entity), `PUT .../concrete`, `pangloss typology tree`; `load` needs `--user` (the user the types are made as, which must exist); `service.update`. `ModelRegistry.before_finalise` (functions called at the start of `initialise()`, used to add the `label_<code>` fields once the settings are known). The module template has a `vitest.config.ts` (a module's component tests need the Solid plugin), and `ApiClient` has `put` and `patch`.

**Not built**

- The tree picker for relation fields (the autocomplete works, since types are entities).
- No way to move a type without a mouse since 2026-11-04: the "Move to…" list on each row went when the tree became drag
  and drop only ([typology-implementation.md#14-the-tree-in-the-interface-drag-and-drop-a-live-tree-inline-labels-plan-of-2026-11-04-built](typology-implementation.md#14-the-tree-in-the-interface-drag-and-drop-a-live-tree-inline-labels-plan-of-2026-11-04-built)).
- The `$under` operator of the structured search, and `concrete_only` on `Role.list`.
- API endpoints for creating, merging and deleting a type (the SDK and the entity's own `/RoleType` endpoints do these).
- SKOS and other formats for loading.

## 14. The tree in the interface: drag and drop, a live tree, inline labels (plan of 2026-11-04, built)

Plan of 2026-11-04 (module `pangloss_typology/interface`). The user's choices:

- **Hierarchy only.** Dragging changes where a type sits; siblings stay in the order of their labels. No server
  change.
- **A live tree.** A `live()` server function sends the tree whenever it changes, as the review feed does; a move or
  a new label is shown at once (optimistically), kept until the feed brings it back, and undone if the API refuses.
- **Inline label editing on the tree's rows only.** A type's own page keeps its form (every language, description).
- **Both pages restyled.**

### 1. Drag and drop (no "Move to…" list)

- Each row has a handle (⋮⋮) for someone who is logged in; the whole row is draggable, the handle shows that it is.
- Where a row is dropped on decides what happens (`zoneAt(offsetY, height)`):
  - its **middle half**: the dragged type goes **below** it (the row is ringed);
  - its **top or bottom quarter**: **beside** it, at its level (a line at the row's indent, above or below it).
    Beside a top-level type is the top level, so the "Drop here for the top level" strip goes.
- `dropTarget(nodes, dragged, over, zone)` (pure) gives the new supertype (`null`: the top) or `undefined` (not
  allowed: itself, its own subtypes, where it is now). Nothing is shown and nothing happens where it is not allowed.
- A drop is optimistic: the tree has the type in its new place at once.
- The "Move to…" select goes. It was the only way to move a type without a mouse: that is a gap now (noted in
  TODO, not built).

### 2. The live tree (`live()`)

- `src/poll.ts`: `pollTree({ fetchTree, every, signal, wait })`: asks for the tree every `every` ms and yields it when
  it is not what it yielded last; errors are thrown (a 401, the access cookie run out, makes the reader open the
  feed again with a new one: `createFeedReader`; anything else is the page's to show).
- `src/feed.ts`: `treeFeed = live(async function* (type) { "use server"; ... })`: on the interface's server, with the
  request's cookies (unpublished types), every `PANGLOSS_TYPOLOGY_POLL_MS` (default 3000).
- `src/state.ts`: `createTypeTree({ type, feed, api })`: a `createOptimisticStore` over the feed (`{ state, nodes }`),
  with the actions `move(id, to)` and `rename(id, label)`: each changes the store at once, calls the API, and waits
  (`until`, 15 s) for the feed to bring it back. A refusal rejects (the page shows why) and the store is the feed's
  again.
- Pure helpers in `tree.ts`: `withMove(nodes, id, to)`, `withLabel(nodes, id, label)` (both keep each level in the
  order of the labels, as the server does).
- e2e: the stack sets `PANGLOSS_TYPOLOGY_POLL_MS` short, like the review's.

### 3. Inline label editing (tree rows)

- A pencil button beside the label (logged in; shows on hover and focus). It turns the label into a text field with
  the label selected. **Enter** or leaving the field saves (`PATCH {label}`) if it changed and is not empty;
  **Escape** puts it back. While it is being edited the row is not draggable.

### 4. The look

- **Tree:** in line with the console bar (the page's own insets, as `Page`); an outline, not a stack of boxes: rows
  with no border, a hover tint, the children under a hairline indent guide; a chevron, the label, the number of
  subtypes in a small quiet pill; handle and pencil show on hover. Drop indicators in sky.
- **Item page:** a type's label is already in the console bar; under it the path, then sections with the core's
  section headings (uppercase, semibold, small); the labels as a definition list; "Edit labels" and the form's buttons
  with the core's `smallButtonClass` (`pg-button` has no style anywhere); subtypes and entities as hairline-separated
  lists with hover tints, not boxes.

### 5. Tests first

- `tree.test.ts`: `zoneAt`, `dropTarget`, `withMove`, `withLabel`.
- `poll.test.ts`: yields on change only, stops when aborted, throws errors.
- `state.test.ts`: optimistic move/rename, kept until the feed has it, undone on refusal.
- `TypeTree.test.tsx` (rewritten, feed mocked as in the review module): the tree from the feed; no select; drag
  zones (into, beside, refused places); a drop moves at once and calls the API; a refusal is shown and undone; the
  pencil, Enter, Escape, blur; not logged in: no handle, no pencil, not draggable.
- `TypeItem.test.tsx`: still passes (classes only).
- e2e `test_typology.py`: drag into, drag beside (to the top level), refused, live (a move made through the API by
  someone else shows without a reload), inline rename; the select tests go.

### As built (2026-11-04)

As planned, except:

- **The feed is opened in the browser only.** Rendered on the server, the store ran the feed there, sent "Loading…",
  and the browser never opened it after hydration. `TypeTree` now mounts the hierarchy after `onSettled`; until then it
  says "Loading…" (the first tree comes at once).
- **UI state is flushed before an action starts.** A signal written in the same handler as an action (`setOver`,
  `setEditing`) is held in the action's transition until it ends, which here is when the feed acknowledges it (up to
  15 s): the drop mark and the text field stayed. `flush()` before `move()`/`rename()`.
- In Vitest a drag must `settle()` after `dragstart`: Solid 2 does not show a written signal until it flushes, and a
  browser always has a task between the events.
- The item page's subtype rows: the label is the link, stretched over the row, so that the link's name is the label
  alone (the counts are beside it).
- Translations: `typology_edit_label`, `typology_label_of` added; `typology_move`, `typology_move_to`,
  `typology_top_level`, `typology_drop_top` removed (`ui.jsonc`).
- The module's `tsconfig.json` has the `node` types (`process.env` in `feed.ts`), as the review module's has.
- **Chips (later the same day):** each type in the tree is a chip, framed as a reference chip is (hairline, slate),
  with its number of subtypes as a segment at its end (only while they are collapsed) (`typology_subtype_count` as its title); no type tag, since every
  row is the same type. "Below this one" marks the chip (sky border and ring), not the row; the text field takes the
  chip's place inside the same frame. The rows also cancel `dragenter`, not only `dragover`: over the chip's link,
  Playwright's drag (and the spec) wants the drop allowed on entering.
- **Chip segments, adding types (later the same day):** the drag handle is the chip's first segment, the pencil and
  "add a subtype" (a branch down to the right, ↳+) its last. A type is made in a dialog (core `Modal`, the same
  `LabelsForm` as the type's page: default label, each language, description), never on a new page: from each chip
  (a subtype), from "Add a top-level type" above and below the tree, and from the console's New button (core
  `ConsoleProps.onNew`: a list page that makes its own new items gets a button calling it instead of the link to
  `/<type>/new`). The dialog stays open while the API makes the type, and says why if it does not; the type is then
  shown at once (optimistic until the feed has it) and its supertype opened. New route `POST /api/typology/{name}`
  (`{label, supertype?, description?, labels?}`, 201; 404 for a supertype not there, 409 for a language the typology
  lacks, 422 for an empty label), on `service.create`.
- **A type made outside the tree (2026-11-13):** the page `/<Type>/new` and the dialog of a relation (the + of a
  field that holds a type) make it with the core form, which has no field for the supertype (`is_subtype_of` is
  `Protection(read_only=...)`, so on no form). Made the usual way it was refused: the generated `Create` wants every
  relation, and the form left the field out (the export calls it not required, as it has a default). The module's
  `newItemFields.Supertype` row (`NewTypeSupertype.tsx`) adds **Below**: "Top level" until a type is found with the
  entity search (`EntityPicker`), then that type as a chip whose ✕ goes back to the top level. Save goes through it
  (`NewItemForm.sendBy`): the type is made with everything in the form and `isSubtypeOf: []` (the one value a create
  may give a read-only field), then moved below the one chosen (`POST .../move`). Shown for a model whose read-only
  field `is_subtype_of` marks it as a typology's entity.
- **Type tags:** someone who is not logged in sees the type in front of each tree chip (`TypeTag`: the model's name in
  its kind's tint, as a reference chip has it) where someone logged in has the handle; a type's page shows its subtypes
  as chips too, with the tag, the label (the link) and their counts.
