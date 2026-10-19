# Defining models

All declarable classes live in `pangloss_models.model_bases` and are Pydantic models. Subclassing one registers the class with `ModelRegistry`; nothing is generated until you call `pangloss_models.initialise()` after all classes are defined.

Per-class options are given through a `_meta` attribute, e.g. `_meta = Document.Meta(create_with_id=True)`. Options marked *accumulates* are merged with the parent's; options marked *not inherited* reset on each subclass; the rest are inherited. (This is implemented by `pydantic-meta-kit`.)

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
    was_carried_out_by: Person       # relation to an Entity (by reference)
    action: Action                   # relation to a Document (nested, created together)
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

- `Statement.Create(...).save(return_type="Reference" | "Full")` ✅
- `Statement.Update(id=..., ...).save(return_type="Reference" | "Full")` ✅ replaces the document and everything nested in it; see [Updating](memgraph.md#update_head_nodeinstance-return_typereference-)
- `await Statement.get(id)` ✅ returns a `HeadView`, or `None` if not found
- `await Statement.list(search_terms=None, page_number=None, page_size=None, deep_search=False)` ✅ returns paginated reference views

## Entity

A real-world thing that documents refer to: a person, place, group, or organisation. Entities are referenced from documents rather than created inline: the relation field accepts an `EntityName.ReferenceSet` (`{"type": "Person", "id": ...}`).

```python
class Person(Entity):
    pass
```

`EntityMeta` options: `abstract`, `create_with_id`, `view_extra_fields` and `reference_view_extra_fields` as for Documents, plus:

| Option | Default | Meaning |
|--------|---------|---------|
| `accept_url_as_id` | `True` | Accept a URL as `id`. `CreateDB` then generates a UUID and stores the URL in `urls` |
| `create_inline` | `False` | Allow creating the entity inside another object's payload. Requires `create_with_id=True` (checked; otherwise `PanglossMetaError`) |

`Entity.list(...)` ✅ and `.save()` ✅ are bound. There is **no** `Entity.get` yet (⏳).

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
    thing_carried_out_by: Agent    # accepts Person | Group (and their subclasses)
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

Like a `ReifiedRelation`, but with the lifecycle of a document: it has a label, a `ReferenceView`, a `View` and a `HeadView`, and can be a head node. 🚧 Models are generated and tested, and writing one (with a nested document as its target) is tested against Memgraph. Reading one back is tested. It is never given a `label` when created, so `View` / `HeadView` do not require one; its `ReferenceView`, however, still declares a required `label` (existing tests assert this), so it cannot be built for one that was read back from the database. ⏳ Decide whether it should have a label (for example a computed one).

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
