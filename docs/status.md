# Status and roadmap

A snapshot of what works and what does not, as of this writing.

## Works (with tests)

- Declaring `Document`, `Entity`, `Embedded`, `Trait`, `NonHeritableTrait`, `EdgeModel`, `ReifiedRelation`, `SemanticSpace`, `Conjunction`; `Meta` options; inheritance and generics.
- Literal field types `str`, `int`, `float`, `bool`, `Decimal`, `date`, `datetime`, `Enum`, `TypedDict`, lists of these, and `X | None`; unsupported types are an error.
- Generating `Create`, `CreateDB`, `ReferenceSet`, `ReferenceView`, `View` and `HeadView` models, including unions, traits, `ViaEdge`, field binding, `Fulfils` / `FieldSubclassing`, `DBField` fields and optional literals.
- Memgraph, writing: documents and entities with nested documents, relations to existing entities (by id or URL), edge properties, subclassed edges, semantic spaces, conjunctions, reified relations, reified relation documents, embedded objects and annotated values.
- Memgraph, updating Documents and Entities by replacing the whole tree (`Update(...).save()`), keeping entities, creation info and ids, with a `PGUpdate` record and `meta.updated_by` / `updated_when` on read; all checks are made before anything is deleted, so a failed update changes nothing.
- Writes that cannot succeed raise typed errors (`PanglossWriteError` subclasses) instead of silently writing nothing.
- Memgraph, reading an entity (`Entity.get`), with the documents that refer to it directly, through embedded objects and through chains of reified relations, subclassed relations shown under their narrower name.
- Memgraph, reading: a document read back as a `HeadView` (nested documents at any depth, with or without entities, semantic spaces, conjunctions, embedded objects, reified relations and reified relation documents, annotated values, dates, unset optionals and empty lists), and listing with pagination, search and deep search.
- Enums stored as Memgraph's native enums (made by `initialise_database`), in fields, lists, `TypedDict`s, edge properties and annotated values, and read back as the models' enums.
- Reading `ViaEdge` fields, with their `edge_properties`.
- Setting up a database (`initialise_database`): indexes, uniqueness constraints on ids, the `label_text` text index and enums; safe to repeat.
- Deleting head documents and unreferenced entities, as a flag (`deleted`) with a `PGDeletion` record, hidden from reads, lists and searches; an entity that is referred to is marked for deletion (`meta.marked_for_deletion`) instead.
- Undeleting head documents and entities (`Document.undelete`, `Entity.undelete`): the flag is removed and a `PGUndeletion` record added, keeping the `PGDeletion` history; `PanglossNotDeletedError` if the node was not deleted.
- Recording the creating user and time on head nodes.
- Context labels and semantic-space annotation on create.

## Partial

| Area | State |
|------|-------|
| Semantic spaces through `UpdateDB` | Works and is tested for updates; the item in `packages/pangloss-models/todo.md` is still unticked |
| Head node type and id through `CreateDB` / `UpdateDB` | Open item in `todo.md` |
| Updating a document concurrently | Last write wins; there is no check that the payload was based on the latest version |
| `pangloss-sdk` (API as database) | Only settings; the functions are stubs returning dummy data |
| `pangloss-users` | Only the `current_request_username` context variable |

## Not implemented

- ⏳ **REST API / web layer.** The project description mentions one; `BACKEND_CORS_ORIGINS`, `AUTHJWT_SECRET_KEY` and `ENTITY_BASE_URL` exist in settings but nothing uses them.
- ⏳ **Authentication, user management, permissions.**
- ⏳ **Removing deleted nodes for good**. An entity marked for deletion is not deleted automatically when the last reference to it goes.
- ⏳ **Installed apps / plugin discovery** (`INSTALLED_APPS`), **interface languages** (`INTERFACE_LANGUAGES`).
- ⏳ **A command-line interface** for `initialise_database` (indexes, constraints, the text index and enums), which has to be called from code for now. `indexes.py` and `pangloss_memgraph/tooling/` are empty.
- ⏳ **Optional relations** (`Person | None`), **optional embedded objects**, **lists of embedded objects or annotated values** and **plain `dict` fields** (use a `TypedDict`) are not supported by the model layer; each raises an error at `initialise()`.
- ⏳ **The `"subtract"` type wrapper** (opposite of `Fulfil`), from `todo.md`.
- ⏳ **`Relation[Subject, Object]`**: placeholder class only.
- ⏳ **Other database backends.** The backend interface is simply the `exposed_functions` module (`get_document`, `create_head_node`, `list_items`), so another backend implements those and is selected by `DATABASE_MODULE`.
- ⏳ **Removal of debugging output** (`print` calls, query dumps to disk) in the Memgraph backend.

## Open design questions

See [`notes/modelling.md`](../notes/modelling.md): how to distinguish specific, multi-tenant and generic roles (e.g. "Prime Minister of the UK" vs "poet laureate" vs "prime minister"), and the open problem of when an activity should be promoted to a role.
