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

Built, and documented in [docs/migrations.md](docs/migrations.md) (section 12) and the [user guide](guide/migrations/README.md). What is left:

- [ ] **A smoke test of the real CLI against the real database**, on a scratch project: `makemigrations`, `migrate`, an added field, going back, `squashmigrations`, `cleanmigrations`, `backups`, `restore`. The CLI tests use a fake backend and the Memgraph tests call the functions directly, so nothing has run the real commands together since the enum, `Fulfils`, read-only and batching changes. Do this first.
- [ ] **A test that the shipped library migration is current**: `pangloss_memgraph/migrations/0001_initial.py` is generated from `INDEXES` / `UNIQUE_CONSTRAINTS` / `TEXT_INDEX` in `initialise_database.py`, and nothing fails if one is edited without regenerating the other. A test that the migrations come to `structure()` would catch it.
- [ ] **Try it on a large database** (say 200,000 nodes): batches, the lock and the dry run have only run on test-sized data, and the size a single transaction can reach on a large graph is still unanswered (spec, section 10).
- [ ] **The demo's database**: it still holds old native-enum values and has no record of `pangloss_memgraph.0001_initial`. Repopulate it, then `pangloss migrate --fake` for the library migration.
- [ ] **Commit the new files** (untracked): `pangloss_models/context.py`, `pangloss_models/migrations/fulfils.py`, and the tests `test_fulfils_writes.py`, `test_migration_batch_equivalence.py`, `test_migrations_fulfils.py`, `test_read_only_while_migrating.py` (memgraph), `test_migration_fulfils.py` (models); also `reverse.py`, `test_migration_reverse.py`, `test_migration_squash.py`, `test_migration_structure.py`, `test_migrations_reverse.py`, `test_migrations_structure_ddl.py` and `pangloss_memgraph/migrations/` if not yet added.
- [ ] **Bring sections 1 to 11 of `docs/migrations.md` up to date**: they are still the original design spec, and parts no longer match what was built (`AddEnum` / `AlterEnum`, the `--backwards` flag, enums as native Memgraph enums). Mark what changed, or trim to what is true.
- [ ] A write already running when `migrate` takes its lock is not waited for (the read-only check is made when a write begins). Consider a short wait for writes in flight before applying.
- [ ] **Decide: `keep=True`** (the spec's way to save what a lossy change would remove, so that going back can restore it). Not built: `--backup` is how to keep what a migration would lose. Build it (a `PGKept` node per removed value, restored by the reverse `AddField`) only if backups prove too coarse.
- [ ] **`check-data` reads a node at a time** (~1.5 ms a node, several read transactions each). A batched read (many nodes in one query) is a change to the read layer (`get`), not to migrations; reading in parallel was measured and is not faster against a local Memgraph.
- [ ] `Fulfils`: a migration decides that a node fulfils a class by whether it has what the class requires (a property, an edge); a write validates against the class's `CreateDB`, so a Python validator on a field of the class is not run by the migration.
- [ ] A cycle between apps that cannot be split (neither a field nor a parent class can be added later) is an error that says so: put the models in one app.

The limits that are by design (a squash in the middle of an app keeps all its changes, `--dry-run` is one transaction, a backup is on the server) are in [docs/migrations.md](docs/migrations.md), "Limits that are not going to change".

## The interface

See [docs/interface.md](docs/interface.md), "Decisions to make next".

## Open design questions

See `notes/modelling.md`: specific, multi-tenant and generic roles, and when an activity should become a role.
