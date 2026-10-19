# Status and roadmap

A snapshot of what works and what does not, as of this writing.

## Works (with tests)

- Declaring `Document`, `Entity`, `Embedded`, `Trait`, `NonHeritableTrait`, `EdgeModel`, `ReifiedRelation`, `SemanticSpace`, `Conjunction`; `Meta` options; inheritance and generics.
- Literal field types `str`, `int`, `float`, `bool`, `Decimal`, `date`, `datetime`, `Enum`, `TypedDict`, lists of these, and `X | None`; unsupported types are an error.
- Generating `Create`, `CreateDB`, `ReferenceSet`, `ReferenceView`, `View` and `HeadView` models, including unions, traits, `ViaEdge`, field binding, `Fulfils` / `FieldSubclassing`, `DBField` fields and optional literals.
- Memgraph, writing: documents and entities with nested documents, relations to existing entities (by id or URL), edge properties, subclassed edges, semantic spaces, conjunctions, reified relations, reified relation documents, embedded objects and annotated values.
- Memgraph, updating Documents and Entities by replacing the whole tree (`Update(...).save()`), keeping entities, creation info and ids, with a `PGUpdate` record and `meta.updated_by` / `updated_when` on read; all checks are made before anything is deleted, so a failed update changes nothing.
- Writes that cannot succeed raise typed errors (`PanglossWriteError` subclasses) instead of silently writing nothing.
- Memgraph, reading: a document read back as a `HeadView`, and listing with pagination, search and deep search.
- Recording the creating user and time on head nodes.
- Context labels and semantic-space annotation on create.

## Partial

| Area | State |
|------|-------|
| Semantic spaces through `UpdateDB` | Works and is tested for updates; the item in `packages/pangloss-models/todo.md` is still unticked |
| Head node type and id through `CreateDB` / `UpdateDB` | Open item in `todo.md` |
| Reading a nested document with no entity or document below it | `get` fails validation (expected-failure test) |
| Reading back `Conjunction` | Written, but `get` does not return the field (expected-failure test) |
| Reading back `date` fields | `get` fails validation (expected-failure test); `datetime` is fine |
| Reading back `Embedded`, `AnnotatedValue`, `ReifiedRelation(Document)` | Written and tested; reading them back is untested |
| `Enum` storage | Stored by value for now; native Memgraph enums need a database setup command that does not exist yet |
| `HeadView` for Entities | Model exists; there is no `Entity.get` |
| Updating a document concurrently | Last write wins; there is no check that the payload was based on the latest version |
| Return type `"Detail"` for `save()` | Named in the registry wrapper, not handled by the Memgraph backend |
| `pangloss-sdk` (API as database) | Only settings; the functions are stubs returning dummy data |
| `pangloss-users` | Only the `current_request_username` context variable |

## Not implemented

- ⏳ **REST API / web layer.** The project description mentions one; `BACKEND_CORS_ORIGINS`, `AUTHJWT_SECRET_KEY` and `ENTITY_BASE_URL` exist in settings but nothing uses them.
- ⏳ **Authentication, user management, permissions.**
- ⏳ **Deleting** stored objects.
- ⏳ **Installed apps / plugin discovery** (`INSTALLED_APPS`), **interface languages** (`INTERFACE_LANGUAGES`).
- ⏳ **Database setup command**: installing indexes (currently only done by the test fixtures; `indexes.py` and `pangloss_memgraph/tooling/` are empty) and creating native Memgraph enum types for `Enum` fields.
- ⏳ **Optional relations** (`Person | None`) are not supported by the model layer and raise an error at `initialise()`; neither is a plain `dict` field (use a `TypedDict`).
- ⏳ **The `"subtract"` type wrapper** (opposite of `Fulfil`), from `todo.md`.
- ⏳ **`Relation[Subject, Object]`**: placeholder class only.
- ⏳ **Other database backends.** The backend interface is simply the `exposed_functions` module (`get_document`, `create_head_node`, `list_items`), so another backend implements those and is selected by `DATABASE_MODULE`.
- ⏳ **Removal of debugging output** (`print` calls, query dumps to disk) in the Memgraph backend.

## Open design questions

See [`notes/modelling.md`](../notes/modelling.md): how to distinguish specific, multi-tenant and generic roles (e.g. "Prime Minister of the UK" vs "poet laureate" vs "prime minister"), and the open problem of when an activity should be promoted to a role.
