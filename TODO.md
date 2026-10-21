# Todo

What is outstanding, as of the version check on updates (after CORS). What works is in `docs/status.md`.

## Before a frontend (next)

- [ ] Typed API client for the frontend: dump `create_app().openapi()` (the models themselves are exported by `pangloss interface export-models`; see [docs/interface.md](docs/interface.md)).

## API and security

- [ ] Permissions beyond logged in / admin (per type, per object).
- [ ] Delete and undelete do not check the version (an `If-Match` could be accepted, as for an update, so a stale page cannot delete what has just been changed).
- [ ] Revoke open sessions when a password is changed (disabling a user already stops their tokens at once).
- [ ] Limit login attempts.
- [ ] CSRF protection for cookie sessions (only `SameSite` protects them now).
- [ ] `ENTITY_BASE_URL` is not used by anything (it was for generating entity URLs).

## Data and the Memgraph backend

- [ ] Remove deleted nodes for good; delete an entity that was marked for deletion when the last reference to it goes.
- [ ] An entity's `ReferenceView` has no `meta`, a document's does.
- [ ] `service.set_admin` / `set_disabled` do not stop the last admin being demoted or disabled (the API stops admins changing their own status).

## Model layer
- [ ] Check whether subclassed relations also have their parent type written to the database, with an appropriate flag ("Derived" stored as a bool); investigate the viability of having "derived" nodes written later as a background job (would involve another thread, locks etc. See DeferredQueryRunner in https://github.com/richardhadden/pangloss/blob/main/pangloss/api.py, which is probably bad and has lots of unwarranted assumptions and race conditions)
- [ ] Optional relations (`Person | None`), optional embedded objects, lists of embedded objects or annotated values, and plain `dict` fields: each raises an error at `initialise()`.
- [ ] The `"subtract"` type wrapper (opposite of `Fulfil`).
- [ ] `Relation[Subject, Object]` (a placeholder class).
- [ ] Interface languages (`INTERFACE_LANGUAGES`).

## Structure and packaging

- [ ] `pangloss-sdk` ("API as database") is stubs; only Memgraph exists as a real backend.
- [ ] `pangloss-core` depends on `pangloss-sdk`, which imports `pangloss-core` back.
- [ ] A project made by `pangloss new-project` has `dependencies = []`, as the Pangloss packages are not published.
- [ ] Running in production: workers, deployment notes (`pangloss run` is one process).

## Database migrations

What works is in [docs/migrations.md](docs/migrations.md) (section 12). Still to do:

**Commands and safety**
- [ ] `migrate --backup`: take a Memgraph snapshot before applying (and require it, or `--no-backup`, for changes that lose data). Not checked: whether a snapshot can be taken from a client with the Memgraph in use.
- [ ] Going backwards: `migrate <app> <earlier>`, with `database_backwards` for each change that can be reversed, `reversible` / `lossy` on each, a confirmation before a lossy one (and, as in the spec, `keep=True` to save what would be lost).
- [ ] Squashing: `squashmigrations app 0001 0007`.
- [ ] `makemigrations <app>` (only one app).
- [ ] A read-only mode while a migration runs (the lock only stops another `migrate`); today the API is stopped, or `MIGRATION_CHECK` stops it starting.
- [ ] `pangloss setup-database` and `migrate` both set up a database (`setup-database` makes the enums of the models directly, which can get ahead of the migrations). Decide how they relate: probably `setup-database` only for a project without migrations, and a warning from it otherwise.

**Changes that cannot be applied yet** (they are found, and refused with `PanglossMigrationNotSupported`)
- [ ] A change of the kind of a model (`AlterModelKind`: Entity to Document and so on) and of the kind of a field (`ChangeFieldKind`), and adding an embedded object that is not made of literals that were there.
- [ ] Wrapping in a conjunction (several slots to fill, so not an automatic change), and unwrapping one.
- [ ] `Fulfils`: the labels a node gets for the classes it fulfils are decided when it is written and are not in the snapshot.
- [ ] Removing a member of, or renaming, an enum whose values are inside a `TypedDict`, an annotated value or an edge model.
- [ ] Indexes, constraints and the text index as changes of their own (`AddIndex`, `RemoveIndex`, `AddConstraint`...): `migrate` only makes the ones `setup-database` makes (`ensure_ready`), and never removes one.
- [ ] Models of two apps that need each other (the planner refuses to share the changes); a model moved from one app to another; migrations that depend on those of a library app (`pangloss_users` and the like).

**Batches and speed**
- [ ] Batches (`--batch-size`) for the changes that are made at once now: removing or renaming a relation, wrapping in a semantic space, `RemoveEnumMember`, unwrapping, `LiteralsToEmbedded`.
- [ ] `check-data` reads one node at a time (~1.5 ms a node, more for large documents); reading several at once.
- [ ] `migrate --dry-run` on a large database runs everything in one transaction.
- [ ] **Writes are planned afresh each time**: the queries that write build parameter names for each call, so Memgraph plans each (a create is ~10 ms, a read now 1 to 2). Fixed parameter names (or a query shape per model) would make creates and updates faster. See "Performance" in [docs/memgraph.md](docs/memgraph.md).

**Code to tidy**
- [ ] `propagate_context` (`migrations/operations.py`) copies `recursively_propagate_context_types` (`base_models.py`), including its sharing of lists. Make it one function used by both, or a test that they agree, so that a change to how the models give context cannot leave migrated data different from written data.
- [ ] The order of the entries of a context label follows the order the edges were made in.
- [ ] `atomic = False` is read from a migration file and means "in batches"; the per-migration choice of batch size is not.
- [ ] The tests leave enums in the test database (Memgraph cannot drop one): `MigrationHue...` and one with a new name for each run of the enum-member test, and `ScratchColour`, `ScratchColour2` in the demo's database from the experiments. A fresh test database is the only way to clear them.
- [ ] `migrate` for a project whose database was made before migrations needs `--fake` for the first; a hint when it finds a non-empty database and no record.

## The interface

See [docs/interface.md](docs/interface.md), "Decisions to make next".

## Open design questions

See `notes/modelling.md`: specific, multi-tenant and generic roles, and when an activity should become a role.
