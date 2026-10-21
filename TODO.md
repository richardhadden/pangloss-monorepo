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

Built, and documented in [docs/migrations.md](docs/migrations.md) (section 12) and the [user guide](guide/README.md). What is left:

- [ ] **Decide: `keep=True`** (the spec's way to save what a lossy change would remove, so that going back can restore it). Not built: `--backup` is how to keep what a migration would lose. Build it (a `PGKept` node per removed value, restored by the reverse `AddField`) only if backups prove too coarse.
- [ ] **`check-data` reads a node at a time** (~1.5 ms a node, several read transactions each). A batched read (many nodes in one query) is a change to the read layer (`get`), not to migrations; reading in parallel was measured and is not faster against a local Memgraph.
- [ ] `Fulfils`: a migration decides that a node fulfils a class by whether it has what the class requires (a property, an edge); a write validates against the class's `CreateDB`, so a Python validator on a field of the class is not run by the migration.
- [ ] A cycle between apps that cannot be split (neither a field nor a parent class can be added later) is an error that says so: put the models in one app.

The limits that are by design (a squash in the middle of an app keeps all its changes, `--dry-run` is one transaction, a backup is on the server) are in [docs/migrations.md](docs/migrations.md), "Limits that are not going to change".

## The interface

See [docs/interface.md](docs/interface.md), "Decisions to make next".

## Open design questions

See `notes/modelling.md`: specific, multi-tenant and generic roles, and when an activity should become a role.
