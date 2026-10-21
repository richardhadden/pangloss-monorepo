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
- [ ] Backups: restoring (`RECOVER SNAPSHOT`, not tried), keeping a snapshot past Memgraph's retention count (3 by default; a later snapshot removes the oldest), and one that is copied off the server.
- [ ] Going backwards, what is left: `RenameEnum`, `AlterModelKind` and `ChangeFieldKind` cannot be undone (the first creates a new enum that has been written to since; the others were done by hand); undoing is always one transaction a migration (no batches, no going on from a stop); values that a change lost are not brought back (`keep=True` to save what would be lost, as the spec has it, is not done); a `--backwards` for a migration that failed or is `running`.
- [ ] Going backwards needs the answers (a value for a field that comes back) asked when it runs; they are not kept anywhere, and `--plan` / `--dry-run` do not ask.
- [ ] Squashing, what is left: a squashed migration cannot itself be squashed (delete its originals, squash from the ones after); only a run that begins the app is made smaller than its changes put together (a run in the middle keeps them all, since data is there); `makemigrations` and the planner do not know of `replaces` beyond the numbering; no command deletes the originals once every database has applied them.
- [ ] `makemigrations <app>` (only one app).
- [ ] A read-only mode while a migration runs (the lock only stops another `migrate`); today the API is stopped, or `MIGRATION_CHECK` stops it starting.

**Changes that cannot be applied yet** (they are found, and refused with `PanglossMigrationNotSupported`). Wrapping in a conjunction is not on this list: a conjunction has several slots and nothing says which one an existing node fills, so it is always written by hand (`RunCypher` / `RunPython`, then `StateOnly`).
- [ ] A change of the kind of a model (`AlterModelKind`: Entity to Document and so on) and of the kind of a field (`ChangeFieldKind`), and adding an embedded object that is not made of literals that were there.
- [ ] `Fulfils`: the labels a node gets for the classes it fulfils are decided when it is written and are not in the snapshot.
- [ ] Removing a member of, or renaming, an enum whose values are inside a `TypedDict`, an annotated value or an edge model.
- [ ] Apps: a library app's models that a project's refer to are not tried (the dependency on its migrations is made as for any app); the order of the layers of an app is by name, not by what is cheapest; a cycle that runs through a model's parents or labels (not its fields) is still refused.

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
