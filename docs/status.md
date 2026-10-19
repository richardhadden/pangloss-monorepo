# Status and roadmap

A snapshot of what works and what does not, as of this writing.

## Works (with tests)

- Declaring `Document`, `Entity`, `Embedded`, `Trait`, `NonHeritableTrait`, `EdgeModel`, `ReifiedRelation`, `SemanticSpace`, `Conjunction`; `Meta` options; inheritance and generics.
- Generating `Create`, `CreateDB`, `ReferenceSet`, `ReferenceView`, `View` and `HeadView` models, including unions, traits, `ViaEdge`, field binding, `Fulfils` / `FieldSubclassing`, and `DBField` fields.
- Memgraph: saving documents and entities (with nested documents, relations to existing entities, edge properties, subclassed edges, semantic spaces), reading a document back as a `HeadView`, and listing with pagination, search and deep search.
- Recording the creating user and time on head nodes.
- Context labels and semantic-space annotation on create.

## Partial

| Area | State |
|------|-------|
| `Update` / `UpdateDB` models | Generated and tested, but **no backend code consumes them**. There is no way to update stored data. |
| Semantic spaces through `UpdateDB` | Open item in `packages/pangloss-models/todo.md` |
| Head node type and id through `CreateDB` / `UpdateDB` | Open item in `todo.md` |
| `AnnotatedValue` | Declared and modelled; not written/read by the Memgraph backend (no code handles it) |
| `ReifiedRelation(Document)` | Models generated; backend persistence and reading are not covered by Memgraph tests |
| `Conjunction` | Models generated; not covered by Memgraph tests |
| `HeadView` for Entities | Model exists; there is no `Entity.get` |
| Return type `"Detail"` for `save()` | Named in the registry wrapper, not handled by the Memgraph backend |
| `pangloss-sdk` (API as database) | Only settings; the functions are stubs returning dummy data |
| `pangloss-users` | Only the `current_request_username` context variable |

## Not implemented

- ⏳ **REST API / web layer.** The project description mentions one; `BACKEND_CORS_ORIGINS`, `AUTHJWT_SECRET_KEY` and `ENTITY_BASE_URL` exist in settings but nothing uses them.
- ⏳ **Authentication, user management, permissions.**
- ⏳ **Updating and deleting** stored objects.
- ⏳ **Installed apps / plugin discovery** (`INSTALLED_APPS`), **interface languages** (`INTERFACE_LANGUAGES`).
- ⏳ **Index management** (`indexes.py` is empty) and other tooling (`pangloss_memgraph/tooling/` is empty).
- ⏳ **The `"subtract"` type wrapper** (opposite of `Fulfil`), from `todo.md`.
- ⏳ **`Relation[Subject, Object]`**: placeholder class only.
- ⏳ **Other database backends.** The backend interface is simply the `exposed_functions` module (`get_document`, `create_head_node`, `list_items`), so another backend implements those and is selected by `DATABASE_MODULE`.
- ⏳ **Removal of debugging output** (`print` calls, query dumps to disk) in the Memgraph backend.

## Open design questions

See [`notes/modelling.md`](../notes/modelling.md): how to distinguish specific, multi-tenant and generic roles (e.g. "Prime Minister of the UK" vs "poet laureate" vs "prime minister"), and the open problem of when an activity should be promoted to a role.
