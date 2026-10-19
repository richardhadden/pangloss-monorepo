# Generated models

For each declared class, `initialise()` creates a set of Pydantic models and attaches them as class attributes. All of them are subclasses of `_ActionClass`, have `_owner` (the declared class) and share its `_meta`. Field names are accepted in `snake_case` or `camelCase` (`alias_generator=to_camel`, `populate_by_name=True`). Every model has a `type` literal field holding the class name, which is the discriminator in unions.

| Attribute | Available on | Purpose | Status |
|-----------|--------------|---------|--------|
| `Create` | Document, Entity, Embedded, ReifiedRelation(Document), SemanticSpace, Conjunction | Validates user input for creating | ✅ |
| `CreateDB` | same | `Create` after ids, labels, semantic spaces and context labels are filled in; what the database layer consumes | ✅ |
| `Update` | same | Validates user input for updating (requires `id`) | 🚧 models only |
| `UpdateDB` | same | Database-side counterpart of `Update` | 🚧 models only |
| `View` | same | Nested representation returned from reads | ✅ |
| `HeadView` | Document, Entity, ReifiedRelationDocument | Top-level read model: `id`, `meta` (`created_by`, `created_when`, `updated_*`, `semantic_spaces`, `context_labels`, `head_node_*`), fields and incoming relations | ✅ (Documents); Entities ⏳ (no `get`) |
| `ReferenceSet` | Entity | `{type, id}` pointer used in `Create`/`Update` to refer to an existing entity (label is dropped if supplied) | ✅ |
| `ReferenceView` | Document, Entity, ReifiedRelationDocument | `{type, id, label, ...}` summary; used in lists and nested reads | ✅ |

## What the base classes add

- **`_CreateBase`** is the base of every `Create` model.
  - `_to_db_model()` builds the `CreateDB` instance, propagates semantic-space/context info through it, and resolves `Fulfils` combinations.
  - A model validator applies [field bindings](relations.md#field-binding).
  - Document and Entity `Create` models get a `.save()` method, bound at initialisation to the database module.
- **`_CreateDBBase`** has `type`, `id` (a `uuid7` is generated if missing), `semantic_spaces`, `context_labels` and a `_labels` property that lists the class name, all parent classes (minus non-heritable traits and generic bases) and the kind (`"Document"`, `"Entity"`, ...). These become the node labels. If the declared class defines `to_db`, `to_db_create` or `to_db_update`, it is called to transform the data (a hook for computed database fields).
  - `_EntityCreateDBBase` also converts a URL `id` into a fresh UUID plus an entry in `urls`.
- **`_ViewBase` / `_HeadViewBase`** convert `neo4j.time.DateTime` values to native datetimes and collapse single-valued relations (which the graph returns as one-item lists) into a single value.
- **`_ListItems[T]`** is the paginated list result: `results`, `count`, `page`, `page_size`, `next_page`, `previous_page`.

## The initialisation pipeline

`pangloss_models.initialise()` runs `ModelRegistry.finalise()`:

1. **Rebuild** every registered model with the full namespace so forward references resolve.
2. **Dependency order.** A stable topological sort over parent classes, generic arguments and annotations. Cyclic models (e.g. a Document with a relation to itself) are initialised in a separate pass.
3. **Field definitions** are built for every model in declaration order (`initialise_field_definitions`). Mistakes such as invalid relation targets raise `PanglossModelError`.
4. **Incoming relations** are worked out for Documents, Entities and ReifiedRelationDocuments.
5. **`ReferenceSet` / `ReferenceView`** models are created.
6. **`Create` + `CreateDB`**, then **`Update` + `UpdateDB`**, then **`View`**, then **`HeadView`**. Each is first created empty and its fields are added afterwards, so models can refer to each other.
7. **Rebuild the action classes** twice so that models see the final versions of the models they reference.
8. **Bind the database.** `SETTINGS.DATABASE_MODULE` names a Python package. `ModelRegistry._bind_database_functions` (run after the models are built) imports `<DATABASE_MODULE>.exposed_functions` and assigns the functions directly; sync and async both work:

   | Bound to | From `exposed_functions` |
   |----------|--------------------------|
   | `Document.get` | `get_document(cls, id)` |
   | `_DocumentCreateBase.save`, `_EntityCreateBase.save` | `create_head_node(instance, return_type)` |
   | `Document.list`, `Entity.list` | `list_items(cls, search_terms, page_number, page_size, deep_search)` |

   A missing module raises `PanglossImportError`.

`ModelRegistry._reset()` clears all registrations; the tests call it before every test.

## Exceptions

| Exception | Raised when |
|-----------|-------------|
| `PanglossInitialisationError` | Registry or field-definition misuse, e.g. instantiating `ModelRegistry` |
| `PanglossModelError` | The user's model declaration is invalid |
| `PanglossMetaError` | Invalid `_meta` combination (e.g. `create_inline` without `create_with_id`) |
| `PanglossImportError` | The database module cannot be found |
| `PanglossAwaitingInitialisation`, `PanglossInternalError`, `PanglossRuntimeError` | Defined; used for internal states |
