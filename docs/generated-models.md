# Generated models

For each declared class, `initialise()` creates a set of Pydantic models and attaches them as class attributes. All of them are subclasses of `_ActionClass`, have `_owner` (the declared class) and share its `_meta`. Field names are accepted in `snake_case` or `camelCase` (`alias_generator=to_camel`, `populate_by_name=True`), and serialised by alias (`camelCase`) in the API. The fields added to the generated models after they are created do not get the alias from the generator, so `initialise()` ends by giving every field of every action class its camelCase alias (`apply_camel_case_aliases`). Every model has a `type` literal field holding the class name, which is the discriminator in unions.

| Attribute | Available on | Purpose | Status |
|-----------|--------------|---------|--------|
| `Create` | Document, Entity, Embedded, ReifiedRelation(Document), SemanticSpace, Conjunction | Validates user input for creating | ✅ |
| `CreateDB` | same | `Create` after ids, labels, semantic spaces and context labels are filled in; what the database layer consumes | ✅ |
| `Update` | same | Validates user input for updating (requires `id`). Nested items are either an `Update` (an existing item, with its `id`) or a `Create` (a new one). It is a full replacement, not a patch | ✅ for Documents and Entities |
| `UpdateDB` | same | Database-side counterpart of `Update` | ✅ for Documents and Entities |
| `View` | same | Nested representation returned from reads | ✅ |
| `HeadView` | Document, Entity, ReifiedRelationDocument | Top-level read model: `id`, `meta` (`created_by`, `created_when`, `updated_*`, `semantic_spaces`, `context_labels`, `head_node_*`), fields and incoming relations | ✅ |
| `EditView` | Entity | A `HeadView` without the incoming relations: `id`, `meta`, the node's own values and its outgoing relations. For editing: incoming relations are written in the documents that hold them. Read with `Entity.get_for_edit`, and can be changed and sent back as an `Update` | ✅ |
| `ReferenceSet` | Entity | `{type, id}` pointer used in `Create`/`Update` to refer to an existing entity (label is dropped if supplied) | ✅ |
| `ReferenceView` | Document, Entity, ReifiedRelationDocument | `{type, id, label, ...}` summary; used in lists and nested reads | ✅ |

Optional literal fields (`X | None`) default to `None` in all of these models, so they can be left out when creating and are `None` when absent from the database.

## What the base classes add

- **`_CreateBase`** is the base of every `Create` model.
  - `_to_db_model()` builds the `CreateDB` instance, propagates semantic-space/context info through it, and resolves `Fulfils` combinations.
  - A model validator applies [field bindings](relations.md#field-binding).
  - Document and Entity `Create` models get a `.save()` method, bound at initialisation to the database module.
- **`_UpdateBase`** is the base of every `Update` model. Like `_CreateBase`, it builds the `UpdateDB` instance with `_to_db_model()`, applies field bindings, and for Documents and Entities has a `.save()` bound to the database module. In `UpdateDB` unions, an entity that can be created inline comes before its `ReferenceSet`, so that a new entity in an update is not mistaken for a reference to an existing one.
- **`_CreateDBBase`** has `type`, `id` (a `uuid7` is generated if missing), `semantic_spaces`, `context_labels` and a `_labels` property that lists the class name, all parent classes (minus non-heritable traits and generic bases) and the kind (`"Document"`, `"Entity"`, ...). These become the node labels. If the declared class defines `to_db`, `to_db_create` or `to_db_update`, it is called to transform the data (a hook for computed database fields).
  - `_EntityCreateDBBase` also converts a URL `id` into a fresh UUID plus an entry in `urls`. (The database stores each URL as a node: see [the Memgraph backend](memgraph.md#graph-schema).)
- **`_ViewBase` / `_HeadViewBase`** convert `neo4j.time.DateTime` values to native datetimes and collapse single-valued relations (which the graph returns as one-item lists) into a single value.
- **`_ListItems[T]`** is the paginated list result: `results`, `count`, `page`, `page_size`, `next_page`, `previous_page`.

## The initialisation pipeline

`pangloss_models.initialise()` runs `ModelRegistry.finalise()`:

1. **Rebuild** every registered model with the full namespace so forward references resolve.
2. **Dependency order.** A stable topological sort over parent classes, generic arguments and annotations. Cyclic models (e.g. a Document with a relation to itself) are initialised in a separate pass.
3. **Field definitions** are built for every model in declaration order (`initialise_field_definitions`). Mistakes such as invalid relation targets raise `PanglossModelError`.
4. **Incoming relations** are worked out for Documents, Entities and ReifiedRelationDocuments.
5. **`ReferenceSet` / `ReferenceView`** models are created.
6. **`Create` + `CreateDB`**, then **`Update` + `UpdateDB`**, then **`View`**, then **`HeadView`** (and, for Entities, **`EditView`**). Each is first created empty and its fields are added afterwards, so models can refer to each other.
7. **Rebuild the action classes** twice so that models see the final versions of the models they reference.
8. **Bind the database.** `SETTINGS.DATABASE_MODULE` names a Python package. `ModelRegistry._bind_database_functions` (run after the models are built) imports `<DATABASE_MODULE>.exposed_functions` and assigns the functions directly; sync and async both work:

   | Bound to | From `exposed_functions` |
   |----------|--------------------------|
   | `Document.get` | `get_document(cls, id)` |
   | `Entity.get` | `get_entity(cls, id)` |
   | `Document.delete` | `delete_document(cls, id)` |
   | `Entity.get_for_edit` | `get_entity_for_edit(cls, id)` |
   | `Entity.delete` | `delete_entity(cls, id)` |
   | `Document.undelete` | `undelete_document(cls, id)` |
   | `Entity.undelete` | `undelete_entity(cls, id)` |
   | `_DocumentCreateBase.save`, `_EntityCreateBase.save` | `create_head_node(instance, detail)` |
   | `_DocumentUpdateBase.save`, `_EntityUpdateBase.save` | `update_head_node(instance, detail, expected_version)` |
   | `Document.list`, `Entity.list` | `list_items(cls, search_terms, page_number, page_size, deep_search)` |

   A missing module raises `PanglossImportError`.

### How the five models are made

`Create`, `CreateDB`, `Update`, `UpdateDB` and `View` are made by one implementation, `initialise_models/builder.py`, driven by a `ModelKind` for each (`initialise_models/kinds.py`). A `ModelKind` is data: the base class for each kind of declared model, which models a relation offers (`Update` offers a new `Create` as well as an `Update`), how an entity is referred to (`ReferenceSet` to write, `ReferenceView` to read), whether bindings and descriptions apply, and when a field is optional. What the five do differently is therefore in one table, with the differences that look accidental marked `quirk` (see [Cleaning up initialise_models](initialise-models-cleanup.md)).

The builder has two steps for a kind: `initialise_model` makes the empty model (named, with `type`, `label`, and `id` and `create_new` if the class can be given an id), and `add_fields` gives it its fields from the field definitions. A relation field's annotation (`relation_annotation`) is a union of what may be given for each type the relation allows: for an entity, a reference and, if the class allows it (`create_inline`), the entity itself; for a document, its model for this kind, made again with the parent's bindings if there are any (`build_bound_model`); for a generic wrapper such as `InRole[Person]`, a model made for that use (`build_generic_model`). The modules `initialise_create_model.py`, `initialise_update_model.py` and the like are the entry points the registry calls.

`ModelRegistry._reset()` clears all registrations and the models made for bindings and generics; the tests call it before every test. Calling `initialise()` again is harmless: models that exist are not made again, and the incoming relations are worked out afresh.

## Exceptions

| Exception | Raised when |
|-----------|-------------|
| `PanglossInitialisationError` | Registry or field-definition misuse, e.g. instantiating `ModelRegistry` |
| `PanglossModelError` | The user's model declaration is invalid, including a field of an [unsupported type](relations.md#field-kinds) |
| `PanglossMetaError` | Invalid `_meta` combination (e.g. `create_inline` without `create_with_id`) |
| `PanglossImportError` | The database module cannot be found |
| `PanglossAwaitingInitialisation`, `PanglossInternalError`, `PanglossRuntimeError` | Defined; used for internal states |
| `PanglossWriteError` | Base class of the errors below. A write was rejected and **nothing was written** |
| `PanglossNotFoundError` | The Document or Entity being updated does not exist, or is not of the given type |
| `PanglossReferenceError` | An existing entity that is referred to does not exist, or is not of a type allowed in that field |
| `PanglossConflictError` | An id given for a new object is already in use, or (in an update) belongs to a different document |
| `PanglossVersionConflictError` | An update said which version it was based on (`expected_version`), and that is not the latest: it has been updated since. Has `current_version` |
| `PanglossUserNotFoundError` | The user doing the write (`current_request_username`) has no `PGUser` node |
| `PanglossNotDeletableError` | A document nested in another document cannot be deleted: only head documents can |
| `PanglossEntityInUseError` | An entity that is referred to cannot be deleted. It **has been marked** for deletion (the one write error that leaves a change), and has `entity_id` and `referenced_by` |
