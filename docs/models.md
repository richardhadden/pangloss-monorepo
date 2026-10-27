# Defining models

All declarable classes live in `pangloss_models.model_bases` and are Pydantic models. Subclassing one registers the class with `ModelRegistry`; nothing is generated until you call `pangloss_models.initialise()` after all classes are defined.

Per-class options are given through a `_meta` attribute, e.g. `_meta = Document.Meta(create_with_id=True)`. Options marked *accumulates* are merged with the parent's; options marked *not inherited* reset on each subclass; the rest are inherited. (This is implemented by `pangloss_models.meta_kit`.)

| Kind | Module | Status | Gets `Create` / `Update` / `View` | Has `HeadView` |
|------|--------|--------|:---:|:---:|
| [`Document`](#document) | `document` | ✅ | ✓ | ✓ |
| [`Entity`](#entity) | `entity` | ✅ | ✓ | ✓ |
| [`Embedded`](#embedded) | `embedded` | ✅ | ✓ | |
| [`Trait` / `NonHeritableTrait`](#traits) | `trait` | ✅ | | |
| [`EdgeModel`](#edgemodel) | `edge_model` | ✅ | | |
| [`AnnotatedValue[T]`](#annotatedvalue) | `annotated_value` | ✅ | | |
| [`ReifiedRelation[T]`](#reifiedrelation) | `reified_relation` | ✅ | ✓ | |
| [`ReifiedRelationDocument[T]`](#reifiedrelationdocument) | `reified_relation` | 🚧 | ✓ | ✓ |
| [`SemanticSpace[T]`](#semanticspace) | `semantic_space` | ✅ | ✓ | |
| [`Conjunction`](#conjunction) | `conjunction` | ✅ | ✓ | |
| [`Relation[S, O]`](#relation) | `relation` | ⏳ | | |

## Document

"An arbitrarily complex object, with nestable subdocuments and relations to Entities." A Document is the main unit of research data, for example a statement, an action or a factoid.

```python
class Statement(Document):
    text: str
    was_carried_out_by: Person  # relation to an Entity (by reference)
    action: Action  # relation to a Document (nested, created together)
```

- Calling `Statement(...)` is the same as `Statement.Create(...)`.
- Documents have a required `label` by default.
- Documents nest. Creating a Statement with an `action` creates both nodes in one write, and the nested node records the outer one as its head node.

`DocumentMeta` options:

| Option | Default | Meaning |
|--------|---------|---------|
| `abstract` | `False` (*not inherited*) | Excluded from the concrete types used for listing and for relations to a parent class |
| `create_with_id` | `False` | Allow a client-supplied `id` in `Create` (and an accompanying `create_new` flag) |
| `accept_url_as_id` | `False` | Allow an `AnyHttpUrl` as `id` as well as a UUID |
| `require_label` | `True` | Whether `label` is required |
| `view_extra_fields` | `[]` (*accumulates*) | Extra fields to include in the `View` model |
| `reference_view_extra_fields` | `[]` (*accumulates*) | Extra fields to include in the `ReferenceView` model |
| `use_in_semantic_space_label` | `True` | Whether this document is listed in `context_labels` when nested in a semantic space (see [Semantic spaces](semantic-spaces.md)) |

Database-bound methods, available after `initialise()`:

- `Statement.Create(...).save(detail=False | True)` ✅
- `Statement.Update(id=..., ...).save(detail=False | True)` ✅ replaces the document and everything nested in it; see [Updating](memgraph.md#update_head_nodeinstance-detailfalse-)
- `await Statement.get(id)` ✅ returns a `HeadView`, or `None` if not found. **A read by a class gives an item of a subclass as that subclass**: `Statement.get(id)` of an `Activity` is an `Activity.HeadView`, whose `type` says so (and `Activity.get(id)` of a plain `Statement` is `None`). The same for `Entity.get` and `get_for_edit`. `list` includes the subclasses, as it always did
- `await Statement.list(search_terms=None, page_number=None, page_size=None, deep_search=False)` ✅ returns paginated reference views
- `await Statement.delete(id)` ✅ deletes a head document; see [Deleting](#deleting)

## Entity

> **There are no "inline entities".** An entity is never part of a document, however it came to exist.
> `create_inline` only lets a document's *payload* name an entity that may not exist yet, by a UUID or URL
> that the sender supplies (with `create_new`), so that data from other sources can be **uploaded in batches**
> without first creating every entity it mentions. If the entity exists it is used as it is; if not, it is created
> exactly as `Entity.Create(...).save()` would create it: a separate head node, with its own history, joined to
> the document only by the relation. Do not describe it as embedded, nested or "inline" in the document
> (see [Creating an entity from a document's payload](#creating-an-entity-from-a-documents-payload-create_inline)).

A real-world thing that documents refer to: a person, place, group, or organisation. Documents refer to entities rather than containing them: the relation field accepts an `EntityName.ReferenceSet` (`{"type": "Person", "id": ...}`).

```python
class Person(Entity):
    pass
```

`EntityMeta` options: `abstract`, `create_with_id`, `view_extra_fields` and `reference_view_extra_fields` as for Documents, plus:

| Option | Default | Meaning |
|--------|---------|---------|
| `accept_url_as_id` | `True` | Accept a URL as `id`. `CreateDB` then generates a UUID, and the URL is stored as a node belonging to the entity (unique: no two entities have the same URL) |
| `create_inline` | `False` | Allow the entity to be written in the payload of a document that needs it (with `create_new`), so that a document and the entities it needs can be created in one go. Requires `create_with_id=True` (checked; otherwise `PanglossMetaError`). See below |

Database-bound methods: `Entity.Create(...).save()` ✅, `Entity.Update(id=..., ...).save()` ✅, `await Person.get(id)` ✅ (by id or URL; `None` if not found), `await Person.list(...)` ✅ and `await Person.delete(id)` ✅ (see [Deleting](#deleting)).

### Creating an entity from a document's payload (`create_inline`)

With `create_inline`, a document's payload can name the entity, with the identifier it should have, instead of only referring to one that exists: `{"type": "Person", "id": <UUID or URL>, "label": "...", "create_new": True}`. This is only a convenience. The entity is **not part of the document**:

- It is looked up by its UUID, or its URL. If it exists it is used as it is (the rest of the payload is ignored, and nothing is changed). If it does not, it is created exactly as `Person.Create(...).save()` would create it: a head node with its own record of creation, and no connection to the document other than the relation. A URL given in several documents is one entity.
- It has nothing of the document's context: not its head node, nor the semantic space the document is in.
- Afterwards it is updated, deleted and read like any other entity.
- If the id or URL is that of something that is not an entity, of a deleted entity, or of an entity of a type the field does not allow, the write raises `PanglossConflictError`.

### Reading an entity

`Person.get(id)` returns a `Person.HeadView` with:

- the values stored on the entity, and its own relations (as for a Document);
- `meta` (`created_by`, `created_when`, `updated_by`, `updated_when`, and so on); and
- a field for each **reverse relation**, named after it (`concerns_person_reverse`, or the name given by `RelationConfig(reverse_name=...)`), listing everything that refers to the entity that way. It is an empty list if nothing does.

What each list contains depends on how the document refers to the entity:

| The document refers to the entity... | The list holds |
|---|---|
| directly (`concerns_person: Person`), including from a nested document, a semantic space or a conjunction | a `ReferenceView` of the document that has the field (the nested document, not the document it is nested in; its `meta` says which that is, and whether it is a head node) |
| through embedded objects (`Statement.date: Date`, `Date.about: Person`) | a `ReferenceView` of the document that the chain of embedded objects starts from |
| through a generic wrapper: a reified relation (`involves_person: Identification[Person]`), a semantic space (`spaced: Negative[Person]`) or a conjunction (`joined: Causes[Person, Place]`), or one of them inside another (`Negative[Identification[Person]]`) | that document, with only `id`, `type`, `meta` and the field holding the chain of wrappers: each with its own values and, in the field that holds what it is made for (`target` of a reified relation, `contents` of a semantic space, `cause` and `result` of a conjunction), the next in the chain. The wrapper next to the entity holds all its targets (so the entity and any others). The document's other fields are not included. A wrapper above the first that has another part which is not an entity (a conjunction of the entity's relation and a document) cannot be shown from the entity: it is left out, and the log has a warning |
| through a chain that mixes embedded objects and wrappers | as for wrappers, with the field named as in the embedded object that holds it |

A relation that a subclass narrows is shown only under the narrower name. If `Action` is a `Statement`, and its `carried_out_by` subclasses `Statement.concerns_person`, then an `Action` appears under `carried_out_by_reverse` and not under `concerns_person_reverse`, although both are stored in the graph. (This follows the incoming relations that the models define for the entity, so a document type that is not a possible source of a relation is left out of that field.)

## Deleting

`Statement.delete(id)` and `Person.delete(id)` delete nothing for good: the node is flagged `deleted`, with a record of who deleted it and when, and everything that reads the database leaves it out (`get` returns `None`, `list` and searches do not find it, it can no longer be updated or referred to, and it no longer counts as referring to an entity). Its `id` stays in use.

- **Only head documents** can be deleted. Deleting one that is nested in another document raises `PanglossNotDeletableError`. A nested document goes when its head document does.
- **An entity can only be deleted if nothing refers to it**: no document, and no other entity, that has not itself been deleted. This includes references through nested documents, embedded objects and reified relations.
- **An entity that is referred to is not deleted, but marked.** `delete` raises `PanglossEntityInUseError` (it has `entity_id` and `referenced_by`, with the `id`, `type` and `label` of up to 10 of the head documents or entities that refer to it), and the entity is flagged `marked_for_deletion`, which its `HeadView` shows as `meta.marked_for_deletion`. The mark is kept although the call raised. Delete it again once nothing refers to it, and it is deleted, and the mark cleared. Nothing deletes it automatically.
- A deleted document or entity that does not exist, or is of another type, raises `PanglossNotFoundError`.

## Methods that only the server can run (`@server_only`)

A method that reads the database, or needs anything a client of the API does not have, can be marked `from pangloss_models import server_only` (as the nearest decorator to the function, under `@classmethod`). On the server it is the function. In the SDK the body is replaced by one that raises `PanglossServerOnly`, and what the function imports is not followed, so the models can still be shipped. (Better: keep such code in another module, which the models do not import.) See [the SDK](sdk.md).

## Embedded

Structured data without its own identity or head node, for example a date range belonging to the object that contains it. It is stored as a separate node, linked from its container, and written together with it, and read back with it (tested). `Embedded` classes are used as field types, singly or as a union (`Date | DateRange`), and get their own `Create`/`Update`/`View`/`CreateDB`/`UpdateDB` models. They never require a label. A list of embedded objects (`list[Date]`) and an optional embedded object (`Date | None`) are **not supported**, and raise an error at `initialise()`.

```python
class Date(Embedded):
    when: datetime.datetime


class Statement(Document):
    date: Date
```

## Traits

A trait is a mixin that lets a relation target "any of these entities/documents".

```python
class Agent(Trait): ...


class Person(Entity, Agent): ...


class Group(Entity, Agent): ...


class Statement(Document):
    thing_carried_out_by: Agent  # accepts Person | Group (and their subclasses)
```

- `Trait[T]` is heritable: subclasses of `Person` are also `Agent`s and the trait's name is added to the node labels.
- `NonHeritableTrait` applies only to the classes that directly inherit it, not their subclasses.

## EdgeModel

Properties that live on a relationship rather than a node. Use with [`ViaEdge`](relations.md#viaedge).

```python
class Certainty(EdgeModel):
    level: int
```

Only literal and list-of-literal fields are allowed.

## AnnotatedValue

Binds extra literal fields to a single value.

```python
class WithCertainty[T](AnnotatedValue[T]):
    certainty: int


class Naming(Document):
    name: WithCertainty[str]
```

✅ A field holds exactly one annotated value, stored as a **map property on the node it belongs to** (`{value: "John", certainty: 2}`), not as a node of its own, and read back from it. Both the value and the extra fields are literals (so `Decimal`, `Enum` and dates are converted as for any literal). A list of annotated values (`list[WithCertainty[str]]`) is **not supported** and raises an error at `initialise()`; to annotate a whole list, make the value a list: `WithCertainty[list[str]]`.

## ReifiedRelation

A relationship that is itself an object with fields, for example "proxy identification" or a person-in-role. A reified relation is generic over its `target`:

```python
class IdentificationProxy[T](ReifiedRelation[T]):
    certainty: int


class Statement(Document):
    identified: IdentificationProxy[Person]
```

`ReifiedRelation` has no label requirement and is created inline with the thing that contains it.

## ReifiedRelationDocument

Like a `ReifiedRelation`, but with the lifecycle of a document: it has a label, a `ReferenceView`, a `View` and a `HeadView`, and can be a head node. 🚧 Models are generated and tested, and writing one (with a nested document as its target) is tested against Memgraph. Reading one back is tested. Like a `Document`, it requires a `label` on creation, update and in its views (`Meta.require_label` is `True` by default).

## SemanticSpace

A generic wrapper that places its contents in a named context, such as "Negative", "Hypothetical", or "Reported". See [Semantic spaces](semantic-spaces.md).

```python
class Negative[T](SemanticSpace[T]): ...


class Factoid(Document):
    has_statement: list[Statement | Negative[Statement]]
```

Payload shape: `{"type": "Negative", "contents": [{"type": "Statement", ...}]}`.

## Conjunction

A generic multi-slot join between related objects.

```python
class Causes[TCause, TResult](Conjunction):
    cause: TCause
    result: TResult


class Factoid(Document):
    has_statements: Statement | Causes[Statement, Statement]
```

## Relation

`Relation[Subject, Object]` exists as a class with `subject` and `object` fields but is not registered or initialised, and has no generated models. ⏳ Placeholder.

## Generics and subclassing

- Subclassing a declared class (`class SubTask(Task)`) is supported; relations to `Task` accept `SubTask` as well, and parent class names become additional node labels.
- Generic parameters (`Negative[Statement]`) are resolved when models are initialised and each parametrisation gets its own generated models, named e.g. `Negative[Statement]Create`.
- Docstrings on declared classes and on fields become descriptions in the generated models.
