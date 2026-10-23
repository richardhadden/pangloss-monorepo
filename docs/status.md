# Status and roadmap

A snapshot of what works and what does not, as of this writing.

## Works (with tests)

- Declaring `Document`, `Entity`, `Embedded`, `Trait`, `NonHeritableTrait`, `EdgeModel`, `ReifiedRelation`, `SemanticSpace`, `Conjunction`; `Meta` options; inheritance and generics.
- Literal field types `str`, `int`, `float`, `bool`, `Decimal`, `date`, `datetime`, `Enum`, `TypedDict`, lists of these, and `X | None`; unsupported types are an error.
- Generating `Create`, `CreateDB`, `ReferenceSet`, `ReferenceView`, `View` and `HeadView` models, including unions, traits, `ViaEdge`, field binding, `Fulfils` / `FieldSubclassing`, `DBField` fields and optional literals.
- Memgraph, writing: documents and entities with nested documents, relations to existing entities (by id or URL), edge properties, subclassed edges, semantic spaces, conjunctions, reified relations, reified relation documents, embedded objects and annotated values.
- Memgraph, updating Documents and Entities by replacing the whole tree (`Update(...).save()`), keeping entities, creation info and ids, with a `PGUpdate` record and `meta.updated_by` / `updated_when` / `version` on read, and a check that an update is based on the latest version (`expected_version`); all checks are made before anything is deleted, so a failed update changes nothing.
- Writes that cannot succeed raise typed errors (`PanglossWriteError` subclasses) instead of silently writing nothing.
- Memgraph, reading an entity (`Entity.get`), with the documents that refer to it directly, through embedded objects and through chains of reified relations, subclassed relations shown under their narrower name.
- Memgraph, reading: a document read back as a `HeadView` (nested documents at any depth, with or without entities, semantic spaces, conjunctions, embedded objects, reified relations and reified relation documents, annotated values, dates, unset optionals and empty lists), and listing with pagination, search and deep search.
- Enums stored as the values of their members (plain properties), in fields, lists, `TypedDict`s, edge properties and annotated values, and read back as the models' enums.
- Reading `ViaEdge` fields, with their `edge_properties`.
- Setting up a database (`initialise_database`): indexes, uniqueness constraints on ids, the `label_text` text index and enums; safe to repeat.
- Deleting head documents and unreferenced entities, as a flag (`deleted`) with a `PGDeletion` record, hidden from reads, lists and searches; an entity that is referred to is marked for deletion (`meta.marked_for_deletion`) instead.
- Undeleting head documents and entities (`Document.undelete`, `Entity.undelete`): the flag is removed and a `PGUndeletion` record added, keeping the `PGDeletion` history; `PanglossNotDeletedError` if the node was not deleted.
- Recording the creating user and time on head nodes.
- The interface (`pangloss-interface`): **scaffolding only**: a Solid 2.0 application with SSR and file routing, a component library (`interface-core`) with enforced layers, `pangloss interface` commands and stub endpoints. See [The interface](interface.md).
- The `pangloss` command line (`pangloss-cli`): `make-stubs` (type stubs for the classes made for the models, for completion in an editor), `new-project` and `new-app` (made from templates; `new-app` adds the app to `INSTALLED_APPS`), `run` and `dev` (the API server; `dev` restarts on changes), `setup-database`, `users ...`, and commands added by installed apps' `cli.py` (`pangloss memgraph info`). See [Command line](cli.md).
- The REST API (`pangloss-api`): login by token or cookie session, CORS for frontends, a version check on updates (`If-Match` / `ETag`), endpoints to manage users, and CRUD routes for every Document and Entity (list, get, create, edit, update, delete, undelete; reading is open, changing needs a login). See [REST API](api.md).
- Users (`pangloss-users`, stored by the Memgraph backend as `PGUser` nodes): create, find, list, update, change password (Argon2id), make admin, disable; `authenticate` checks a password. A disabled user cannot write. See [Users](users.md).
- Context labels and semantic-space annotation on create.
- Entity URLs: returned as `urls` in an entity's `HeadView` and `EditView`, and replaced by an update that gives `urls` (checked for conflicts, stored as `PGUrl` nodes).
- Exporting the definitions of the models as plain data (`pangloss_models.export.export_models()`), which the interface turns into a TypeScript module (`pangloss interface export-models`, and on every build). See [The interface](interface.md).
- Routes from installed apps: an app's `api.py` `router` is included by the API (used by `pangloss-interface`).
- The demo project, `pangloss-demo/` (a factoid model with a script that populates it), and its setup: [The demo project](demo-setup.md). Making it fixed two faults in the model layer: an inline entity declared after what refers to it, and field binding into a `list[...]` relation.

## Partial

| Area | State |
|------|-------|
| `pangloss-sdk` (API as database) | The client works (phase 1 of [the SDK](sdk.md)): every model function as a request to the API, login, errors. Not built: the generated project SDK, its serving, git |

## Not implemented

- ⏳ **`ENTITY_BASE_URL`** is not used by anything.
- 🚧 **Database migrations**: `pangloss makemigrations`, `migrate` and `showmigrations` work (renames are asked, not guessed; the answers a change needs are asked and kept in the migration file), for literals, enums, relations, edge properties, wrapping a relation in a reified relation or a semantic space, one wrapper for another, literals becoming an embedded object, and models, applied to Memgraph with a record of what has been applied and a lock. The API does not start with migrations pending or the models changed since (`MIGRATION_CHECK`). `migrate --dry-run` says what each change would do, `check-data` reads everything with the models (`migrate` reads the models the migrations could have affected after applying), and `migrate --batch-size` makes the large changes in batches that a run that stops goes on from. Changes can be written by hand (`RunCypher`, `RunPython`, `makemigrations --empty`). `migrate --backup` takes a Memgraph snapshot first. `migrate <app> <target>` goes back to an earlier migration where its changes can be undone (in batches, and a failed one too); `backups` and `restore`; `cleanmigrations`. `squashmigrations` replaces a run of migrations by one. Indexes and constraints are migrations too (the library's own, `pangloss_memgraph.migrations`); models of apps that need each other are made in two steps. See [Database migrations](migrations.md#12-progress).
- ⏳ **Permissions** beyond admin / not admin, revoking tokens, and limiting login attempts.
- ⏳ **Removing deleted nodes for good**. An entity marked for deletion is not deleted automatically when the last reference to it goes.
- ⏳ **Interface languages** (`INTERFACE_LANGUAGES`). (`INSTALLED_APPS` is used by the command line, to add commands and import models; nothing else reads it yet.)
- ⏳ **Optional relations** (`Person | None`), **optional embedded objects**, **lists of embedded objects or annotated values** and **plain `dict` fields** (use a `TypedDict`) are not supported by the model layer; each raises an error at `initialise()`.
- ⏳ **The `"subtract"` type wrapper** (opposite of `Fulfil`), from `todo.md`.
- ⏳ **`Relation[Subject, Object]`**: placeholder class only.
- ⏳ **Other database backends.** The backend interface is simply the `exposed_functions` module (`get_document`, `create_head_node`, `list_items`), so another backend implements those and is selected by `DATABASE_MODULE`.

## Open design questions

See [`notes/modelling.md`](../notes/modelling.md): how to distinguish specific, multi-tenant and generic roles (e.g. "Prime Minister of the UK" vs "poet laureate" vs "prime minister"), and the open problem of when an activity should be promoted to a role.
