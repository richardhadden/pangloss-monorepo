# Defining models

All declarable classes live in `pangloss_models.model_bases` and are Pydantic models. Subclassing one registers the class with `ModelRegistry`; nothing is generated until you call `pangloss_models.initialise()` after all classes are defined.

Per-class options are given through a `_meta` attribute, e.g. `_meta = Document.Meta(create_with_id=True)`. Options marked *accumulates* are merged with the parent's; options marked *not inherited* reset on each subclass; the rest are inherited. (This is implemented by `pangloss_models.meta_kit`.)

| Kind | Module | Status | Gets `Create` / `Update` / `View` | Has `HeadView` |
|------|--------|--------|:---:|:---:|
| [`Document`](#document) | `document` | ✅ | ✓ | ✓ |
| [`Entity`](#entity) | `entity` | ✅ | ✓ | ✓ |
| [`Embedded`](#embedded) | `embedded` | ✅ | ✓ | |
| [`Trait` / `NonHeritableTrait`](#traits) (and `SemanticTrait` / `SemanticNonHeritableTrait`) | `trait` | ✅ | | |
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
| `label_template` | `None` | 🚧 How the label is worked out from what the document holds, `"Will of {testator}[: {bequests\|join("; ")}]"`, or `LabelTemplate(...)` with alternatives; on every kind of model, inherited. The label may then be left out: the server works it out on each write unless it was written by hand (`label_auto`). Not data, so no migration. See [Label templates](label-templates.md) |
| `create_directly` | `True` | Whether one can be made on its own, as a head document. With `False` it is only ever part of another document (a statement in a factoid): `Create(...).save()` raises `PanglossNotCreatableError` (in every backend, the SDK too, and a bulk load refuses the record), the API has no `POST /api/NAME`, and the interface has no "New" button. Its `Create` is still made, for nesting it; what there is of one can still be read, edited and deleted. Inherited, so setting it on a base class covers all its kinds; a subclass can set `True` again |
| `global_search` | `True` | Whether "search everything", the box of the homepage, finds it. Not inherited: a class built on one that is left out is found unless it says otherwise. Not data, so no migration. See [The homepage](homepage-and-pages.md) |
| `indexes` | `[]` (*not inherited*) | Fields (or `"label"`) of this class to keep a database index of, for searching by their values: each is a label-and-property index on the class (its subclasses' nodes have its label, so it covers them). Only a field with a value of its own (text, number, date, choice, a list of these); checked when the models are initialised. A change is a migration. See [Structured search](structured-search.md#step-5-measured) |
| `view_extra_fields` | `[]` (*accumulates*) | Extra fields to include in the `View` model |
| `reference_view_extra_fields` | `[]` (*accumulates*) | Extra fields to include in the `ReferenceView` model |
| `use_in_semantic_space_label` | `True` | Display only: with `False`, the interface leaves a nested document of this class out of the trail of spaces and documents shown round what is inside it. Storage does not read it: the path (`meta.path`) has every node a node is nested in (see [Semantic spaces](semantic-spaces.md)). A change of it still makes a migration (`AlterModelOption`; open, in [the build plan](spaces-and-comparison-plan.md), 1.3) |

Database-bound methods, available after `initialise()`:

- `Statement.Create(...).save(detail=False | True)` ✅
- `Statement.Update(id=..., ...).save(detail=False | True)` ✅ replaces the document and everything nested in it; see [Updating](memgraph.md#update_head_nodeinstance-detailfalse-expected_versionnone-)
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

`EntityMeta` options: `abstract`, `create_with_id`, `indexes`, `view_extra_fields` and `reference_view_extra_fields` as for Documents, plus:

| Option | Default | Meaning |
|--------|---------|---------|
| `accept_url_as_id` | `True` | Accept a URL as `id`. `CreateDB` then generates a UUID, and the URL is stored as a node belonging to the entity (unique: no two entities have the same URL) |
| `create_inline` | `False` | Allow the entity to be written in the payload of a document that needs it (with `create_new`), so that a document and the entities it needs can be created in one go. Requires `create_with_id=True` (checked; otherwise `PanglossMetaError`). See below |
| `companions` | `[]` | Documents the interface offers with a new entity of the class, written with it in one transaction if anything in them is filled in (a factoid of a new person's naming): `Companion(name=, document=, field=, parts=[CompanionPart(type=, entity_field=)], copies=[CopyFromOuter(field=)], offered=[Within(heads=...), Standalone()])`. Inherited (`[]` on a subclass for none); not data. `Entity.Create(...).save_with_companions({name: document})` in Python. See [companion documents](companion-documents.md) |

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
| through a generic wrapper: a reified relation (`involves_person: Identification[Person]`), a semantic space (`spaced: Negative[Person]`) or a conjunction (`joined: Causes[Person, Place]`), or one of them inside another (`Negative[Identification[Person]]`) | that document, with only `id`, `type`, `meta` and the field holding the chain of wrappers: each with its own values, its own relations (`InRole.role`), the values of the edge into it if that edge has an edge model (`edge_properties`, for `ViaEdge[Identification[Person], Certainty]`) and, in the field that holds what it is made for (`target` of a reified relation, `contents` of a semantic space, `cause` and `result` of a conjunction), the next in the chain. The wrapper next to the entity holds all its targets (so the entity and any others). The document's other fields are not included. A wrapper above the first that has another part which is not an entity (a conjunction of the entity's relation and a document) cannot be shown from the entity: it is left out, and the log has a warning |
| through a chain that mixes embedded objects and wrappers | as for wrappers, with the field named as in the embedded object that holds it |

So a relation through a wrapper that has a relation of its own (`InRole[Person]` with `role: RoleType`), and one through a
wrapper reached by an edge model (`ViaEdge[EdgeA[Person], Certainty]`), are read back with the rest (✅ 2026-11-20,
conformance `test_relation_steps_live.py`; no extra query). Limits: a wrapper's own relation gives what it points at with
that node's own properties only (right for an entity: a reference), so an embedded object or a nested document of a
wrapper's own is not read any deeper; and a direct `ViaEdge` (`plain: list[ViaEdge[Person, Certainty]]`) gives the reference
to the document without the edge's values, where a wrapped one gives them.

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

Structured data without its own identity or head node, for example a date range belonging to the object that contains it. It is stored as a separate node, linked from its container, and written together with it, and read back with it (tested). `Embedded` classes are used as field types, singly or as a union (`Date | DateRange`), and get their own `Create`/`Update`/`View`/`CreateDB`/`UpdateDB` models. They never require a label. An embedded field may be optional (`Date | None`: none is no node; see [Optional relations and embedded objects](relations.md#optional-relations-and-embedded-objects-)). A list of embedded objects (`list[Date]`) is **not supported**, and raises an error at `initialise()`.

```python
class Date(Embedded):
    when: datetime.datetime


class Statement(Document):
    date: Date
```

- **A field typed with a base `Embedded` class accepts its subclasses** (each is told apart by `type` in the `Create` and `Update` models; the base class itself is accepted too).
- **Validators.** The `@model_validator`s (of any mode) and the `@field_validator`s of literal fields that the class declares are copied to the `Create` and `Update` models, so they run once, where a payload is parsed (not again on the database models, nor on the views). What only the database has (a `DBField`, such as the bounds of a date) is filled in by a `@create_validator` / `@update_validator` instead, which run on `CreateDB` / `UpdateDB`. See [Validators, write checks and methods](generated-models.md#validators-write-checks-and-methods-). A field's default (`year: int = 0`) is carried too: such a field may be left out. See [Defaults](relations.md#defaults).
- **Indexes.** `Embedded.Meta(indexes=["field"])` asks for a label-and-property index of a field, as on documents and entities (it is not inherited; the nodes of its subclasses carry the label too). An embedded class has no label index unless it asks for a field.

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
- A trait can carry fields (literal, embedded, `DBField`s), validators of every kind and methods, which the classes that have it get as their
  own. `reference_view_fields: ClassVar[tuple[str, ...]]` on a trait adds those fields to the `ReferenceView` of every class that has it (a
  `DBField` may be one: a reference view is only read). `pangloss_dates.dateable.Dateable` is one: a `date`, and a copy of its sort day and
  text in the reference.
- The export of a model (`export_models`) names its traits (`traits`), for the interface.
- `SemanticTrait` and `SemanticNonHeritableTrait` (2026-11-20) ✅ are for a trait that means something as a class
  (`Agent`: "a person or a group"), where a plain trait is a mixin (`Dateable`). They are stored, labelled and read
  exactly as `Trait` and `NonHeritableTrait` (neither base is a label or a model of its own), so a trait changed from
  one to the other is no change of data. The model layer tells them apart (`pangloss_models.utils.model_is_semantic_trait`;
  a trait below a semantic trait is semantic), and the export of a model lists them in `semanticTraits` as well as in
  `traits`. Nothing in the core gives them a meaning: a package may.

## EdgeModel

Properties that live on a relationship rather than a node. Use with [`ViaEdge`](relations.md#viaedge).

```python
class Certainty(EdgeModel):
    level: int
```

Only literal and list-of-literal fields are allowed.

**An edge says which edge model its values are of** (✅ 2026-11-20). Both edges of a relation with an edge model carry
`pg_edge_model`, the name of the class the relation declares for that value (`pangloss_cypher.build_tree.EDGE_MODEL`,
written by `write_plan`). It is not a field: a read does not show it (`INTERNAL_EDGE_PROPERTIES`), and a payload does
not give it. A search by an edge model goes by it ([structured search](structured-search.md)), so that two edge
models with fields of the same names are told apart; an edge model below another (`class Strong(Certainty)`) is found
by the one above it.

- **For the edges that were there before**, the backends ship a migration (`pangloss_memgraph.0009`,
  `pangloss_neo4j.0007`: the change `RecordEdgeModels`), which gives every edge the edge model the models say it is of,
  at every place of a way (the field's own edge by what it is to, the edges inside each wrapper it can hold). So an
  existing database needs `pangloss migrate`; until then a search by an edge model finds nothing in it. A project
  with no migrations of its own has no models at that point, and nothing is recorded: ⏳ no command does it there.
- **Migrations keep it:** `AlterEdgeModel` and `AlterRelationTarget` record what the relation's edges are of after
  them (a swap between two edge models with the same fields changed nothing in the data before); `RenameModel` of
  an edge model renames it on its edges. It is copied with the edge by a merge, and by a renamed relation.
- **A type is among the types of a field once.** A value says which it is by its `type` alone, so
  `ViaEdge[Person, Certainty] | ViaEdge[Person, Likelihood]`, `Person | ViaEdge[Person, Certainty]` and
  `InRole[Person] | InRole[Place]` are refused by `initialise()` with a `PanglossModelError` that says so (they failed
  before, with an error of pydantic's). Each target its own edge model
  (`ViaEdge[Person, Certainty] | ViaEdge[Place, Likelihood]`) is allowed.
- **A value given for an edge that is no field of its edge model is refused** on a `Create`, an `Update` and a
  `ReferenceSet` (it was dropped quietly), as a key of the document itself is.

## AnnotatedValue

Binds extra literal fields to a single value.

```python
class WithCertainty[T](AnnotatedValue[T]):
    certainty: int


class Naming(Document):
    name: WithCertainty[str]
```

✅ A field holds exactly one annotated value, stored as a **map property on the node it belongs to** (`{value: "John", certainty: 2}`), not as a node of its own, and read back from it. Both the value and the extra fields are literals (so `Decimal`, `Enum` and dates are converted as for any literal). A **list** of annotated values (`names: list[WithCertainty[str]]`) is allowed: a list of maps on the node (`[{value: "John", certainty: 3}, ...]`), written and read back whole, in order, like a list of literals (it is required, and may be empty; a new one on existing nodes starts empty). Neo4j cannot keep a list of maps as a property, so there it is stored as JSON text (`names#json`) and decoded when read, as any list of maps is. To give one certainty to a whole list instead, make the value a list: `WithCertainty[list[str]]`. Changing a single annotated value into a list of them, or back, is a change of kind, which a migration refuses (add a new field and move the data by hand). Not searchable, as a single annotated value is not.

## ReifiedRelation

A relationship that is itself an object with fields, for example "proxy identification" or a person-in-role. A reified relation is generic over its `target`:

```python
class IdentificationProxy[T](ReifiedRelation[T]):
    certainty: int


class Statement(Document):
    identified: IdentificationProxy[Person]
```

`ReifiedRelation` has no label requirement and is created inline with the thing that contains it.

**Classes below a wrapper** (✅ 2026-11-20; the same for a semantic space and a conjunction).

- A generic class below another (`class Reading[T](Identification[T])`) is a wrapper of its own: its node has the
  label `Reading`, not `Identification`. A search that names `Identification` looks for both (see structured search).
- **A field takes the classes below the wrapper it names**, as a field that names `Person` takes a `Saint`:
  `who: list[Identification[Person]]` takes `{"type": "Reading", ...}` too, with `Reading`'s own fields, and so on
  down (`build_relation_options` → `wrapper_uses_below`;
  [the task](reified-relation-inheritance-plan.md)). Writing the union out
  (`Identification[Person] | Reading[Person]`) is the same field. What this means:
  - The classes taken are those that pass their parameters on (`class Reading[T](Identification[T])`) and a class
    with no parameters below the very use the field names (`JohnRole` below, in a field of `InRole[Person]`).
  - Not taken, without a word (name it in the field if it is wanted there): a class with a parameter the use does
    not settle (`class Both[A, B](InRole[A])`), a class below another use (`class GroupRole(InRole[Group])`, or
    `JohnRole` in a field of `InRole[Person | Group]`), and a class below a class with no parameters
    (`class Sub(JohnRole)`).
  - There is no way to keep a class below out of a field that names the class above. A field that should take the
    class below only names that one (`Reading[Person]`).
  - A new class below a wrapper is a migration for every field that names the wrapper (`AlterRelationTarget`,
    additive, no data changes): a project that names `Identification[X]` with `pangloss_library` installed takes an
    `IdentificationByToolchain` there.
  - In the interface a form offers each as it offers the types of a union, and `default_reified_type` may be any of
    them. `InterfaceMeta(headless=True)` is for a field with one type, so a wrapper that has a class below it has
    its head bar in a field that names it.
- A class with no parameters below a *use* of a wrapper (`class JohnRole(InRole[Person])`) is that use, as a class of
  its own with fields of its own: `john: list[JohnRole]`. (Before, such a field had no types and was left out of the
  generated models without a word.) Its node has the label `JohnRole`.
- A wrapper's own relation may be to named types through another wrapper
  (`class InOffice[T](ReifiedRelation[T]): office: Negative[RoleType] | None`, `ranks: list[Sure[RoleType]]`; this
  failed `initialise()` before). Through a wrapper around its own type variable (`list[Sure[T]]`) it is refused, with a
  `PanglossModelError`: ⏳ not supported.

`_meta = ReifiedRelation.Meta(label_index=True)` gives its nodes a label index (a migration), for a kind that is
looked for across documents (the library's `IdentificationByToolchain`, which review lists). Subclasses inherit it,
each for its own label: a node does not have the label of a generic class that its class is made from.

**Stand-ins ✅ (2026-11-10).** A package may let a document go where a relation takes entities, without the models
naming it: it appends a `StandIn(document, stands_for, check, refused_by)` to `pangloss_models.hooks.stand_ins`.
A relation to an entity type that `check(owner, field, entity_type)` accepts then also takes that document (its
option has `stands_in_for`, exported as `standsInFor`), and a `Create`/`Update` refuses one standing for a type the
field does not take. `pangloss_review`'s `Unreconciled` is the one user ([review-update-plan.md](review-update-plan.md)).

A `StandIn` may also say, by `named_type`, the name of a property of its document that holds the name of the one
entity class a value stands for (review's is `"unreconciled_type"`); None, the default, if the document does not say,
and it stands for whatever its field takes ✅ (2026-11-22). Nothing in the core reads it: it is for a package that
works from a write plan and must know which nodes stand in for an entity, and of what class (reconciliation,
[similarity-build-plan.md](similarity-build-plan.md) 10.2).

**A stand-in resolved ✅ (2026-11-23).** A package that has a route of its own for putting an entity in a stand-in's
place says so, after the write of the document has returned, with `await hooks.tell_resolved(Resolution(...))`; a
package that wants to know appends an async function to `hooks.resolved`. A `Resolution` has the stand-in's id and
class (`stand_in_type`: `Unreconciled`, or `MatchesCriteria` as its node says), its `label` and the class it stood
for (`stood_for`, the property `named_type` names), if it has them, its head's id and class, the entity put in its
place (id and class), the `user`, when (`at`), and `direct`: true for the stand-in the person had open, false for one
resolved along with it. It is outside any transaction, so a listener may write to the database (a listener of
`after_write` may not); each is awaited in turn in the request, so a slow one slows it; one that raises is logged and
the others are still told; a write that failed raises nothing. Raised by `pangloss_review.reconcile` (not for a
mention reconciled `in_form`, whose document is not written there; [review.md](review.md)) and
`pangloss_criteria.resolve`, once for each place ([matches-criteria.md](matches-criteria.md)). **It is not every
stand-in that goes**: an edit of a form that replaces one, a restore from history, an update through the SDK or by a
toolchain raise nothing. Made for reconciliation to keep the decisions people take ([similarity-build-plan.md](similarity-build-plan.md)
11.3, 11.4). Tests: `pangloss-models/tests/test_resolved_hook.py`, the conformance `test_resolved_live.py`, and
`pangloss-criteria/tests/live/test_criteria_resolve_live.py`.

**A suggestion confirmed ✅ (2026-11-23).** A package that turns a toolchain's suggestion into a person's
identification says so, after the write of the document has returned, with `await
hooks.tell_confirmed(Confirmation(...))`; a package that wants to know appends an async function to `hooks.confirmed`.
`hooks.resolved` cannot carry it: a suggestion confirmed as it is, with three alternatives, has no one entity. A
`Confirmation` has the suggestion's id (the node keeps it: it is the identification now), the class it was
(`suggestion_type`) and the class it is (`confirmed_type`), its head's id and class, the `user`, when (`at`), the
entities of the confirmed target (`entities`: id and class each, in order; one for an identification of one, several
while alternatives are open), and `direct`: true for the suggestion the person had open and confirmed by its own
route, false for one confirmed along with it or by a save of its document. As for `resolved`: outside any
transaction (a listener may write), each awaited in turn, one that raises logged and the others still told, nothing
for a write that failed. Raised by `pangloss_review.identify` for every way of confirming ([review.md](review.md),
"Confirmed, told to `hooks.confirmed`"). **It is not every suggestion that goes**: one deleted, or edited away to
something that is not the same node as an identification, raises nothing, nor does a write by a toolchain (a user of
kind `toolchain`), nor a restore (a write with `restored_from`, which put back a version in which the node was an
identification: no one judged the suggestion now there; 2026-11-24). Made for reconciliation to learn from people's
confirmations: its one listener is `pangloss_reconcile.decisions.confirmed`, which makes an example only of a
suggestion its worker wrote, confirmed as exactly one entity by a person ([similarity-build-plan.md](similarity-build-plan.md)
10.5f, [reconcile.md](reconcile.md)). Tests: `pangloss-models/tests/test_confirmed_hook.py`, the conformance
`test_confirmed_live.py`.

**The instructions of one write ✅ (2026-11-23).** What a write says of the work that is to follow it
(`save(instructions={"suggest": False})`, `?suggest=false` on the API's create, with-companions and update routes):
an app declares each instruction (`hooks.WriteInstruction(name, values, description)`,
`hooks.declare_write_instruction`), and a function of `hooks.instructed_work`, given the class and the write's
instructions, marks a kind of pending work (`True`) or takes a standing mark of it off (`False`), only in a create or
an update of a head; in one, it is also asked for each entity the write makes, by the entity's class, with the same
instructions. Described in [packages.md](packages.md#the-instructions-of-one-write-); `pangloss-reconcile`'s
`suggest` is the one there is.

**A generic stand-in ✅ (2026-11-19).** The class a `StandIn` names may be a generic wrapper with one type variable
(`pangloss_criteria`'s `MatchesCriteria[T]`, with `CriteriaMeta(allowed=True)` on the entity class and `NoCriteria()`
on a field). The relation then takes the use of it with the topmost entity classes it stands for as its parameter,
as if the annotation said so: a relation to `Agent` takes `MatchesCriteria[Group | Person]`, with the relation's edge
model. The use is made when the fields are analysed and is a model like one written out; a field that writes a use
out has that one alone. It has no `stands_in_for` and no `check`. Nothing stands in for what a generic stand-in
holds, nor for what only computed relations hold ([matches-criteria.md](matches-criteria.md), "As built", step 4).

**A guess no person has confirmed ✅ (2026-11-23).** A package says which wrapper classes hold a guess that no person
has confirmed by appending to `hooks.unconfirmed` a function that gives their names (each class by its own label: a
class below one is named itself); `hooks.unconfirmed_classes()` gives them all, sorted. What is below a node of such
a class is no evidence of anything until a person confirms it (it is then a node of another class). `pangloss-library`
gives every class of suggestion (`IdentificationByToolchain` and those below it). Two packages read it, and nothing
else: the graph part of similarity does not walk below one ([fastrp.md](fastrp.md), "The joined graph"), and
reconciliation does not count what is named below one in what a candidate is named with ([reconcile.md](reconcile.md),
"Reasons"). What uses an entity (lists of what is used, the check before a delete, `references_not_counted`) is not
changed by it. Made for [similarity-build-plan.md](similarity-build-plan.md) 10.5c (the user's answer to row 16).
Tests: `pangloss-fastrp/tests/test_fastrp_unconfirmed.py`, `pangloss-reconcile/tests/test_reconcile_reasons_unconfirmed.py`
and the live tests beside them.

## ReifiedRelationDocument

Like a `ReifiedRelation`, but with the lifecycle of a document: it has a label, a `ReferenceView`, a `View` and a `HeadView`, and can be a head node. 🚧 Models are generated and tested, and writing one (with a nested document as its target) is tested against Memgraph. Reading one back is tested. Like a `Document`, it requires a `label` on creation, update and in its views (`Meta.require_label` is `True` by default).

## SemanticSpace

A generic wrapper that places its contents in a named context, such as "Negative", "Hypothetical", or "Reported". See [Semantic spaces](semantic-spaces.md).

```python
class Negative[T](SemanticSpace[T]): ...


class Factoid(Document):
    has_statement: list[Statement | Negative[Statement]]
```

Payload shape: `{"type": "Negative", "contents": [{"type": "Statement", ...}]}`. A space holds at least one item: an empty `contents` is refused ("Negative holds nothing: a semantic space has at least one item").

✅ `SemanticSpace.Meta(...)` says what the space says of its contents; each option is inherited and may be set anew,
and none is data (no migration). In brief ([in full](semantic-spaces.md#what-a-space-says-of-its-contents-)):

| Option | Default | Effect |
|---|---|---|
| `veridical` | what `logical` implies (`-1` for `"not"`, else `0`) | `1` asserted, `0` neither, `-1` denied |
| `fit` | `"describes"` | or `"prescribes"`: an order, a wish |
| `logical` | `None` | `"not"`, or `Modal(force, flavour, of_not=False)` (`Modal("possibility", "epistemic")`) |
| `unary` | what `logical` implies (`True` for `"not"` and a modal `of_not`, else `False`) | One item at most in `contents`; a second is refused |
| `degree` | `None` | The class's default degree for its contents, in five steps (`"impossible"` to `"expected"`); only where `veridical` is `0` |

`initialise()` refuses options that contradict each other (`logical="not"` with `veridical=1`). Several items in a
space that is not unary are read each by itself, never together. The field that holds a space can say whose it is
and whom it is addressed to: `Annotated[Ordered[Statement], Attribution(by="ordered_by", to="ordered_to")]`
([Attribution](semantic-spaces.md#whose-a-space-is-attribution-)). How likely one space's contents are, the person
who enters it says on a field the project declares and marks `Degree()`:
`how_likely: Annotated[DegreeStep | None, Degree()] = None`, an ordinary literal field whose value is also written
into the space's entry of the path of what it holds (`degree`; the class's default is not)
([Degree()](semantic-spaces.md#a-degree-entered-on-a-space-degree-)).

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
