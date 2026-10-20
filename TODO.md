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

## The interface

See [docs/interface.md](docs/interface.md), "Decisions to make next".

## Open design questions

See `notes/modelling.md`: specific, multi-tenant and generic roles, and when an activity should become a role.
