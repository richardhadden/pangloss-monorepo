# Todo

What is outstanding, as of the version check on updates (after CORS). What works is in `docs/status.md`.

## Before a frontend (next)

- [ ] **Entity URLs in the views.** An entity can be found by URL, but its `HeadView` / `EditView` do not say which URLs it has.
- [ ] **Export the models for the frontend build.** A command (`pangloss export-models <file>`) that loads the settings, imports the apps' models, runs `initialise()` and writes a JSON serialisation of the `ModelFields` (fields, relations and their target types, embedded objects, annotated values, `parameter_type_options` of the generic wrappers, incoming fields, validators). Needs no database or server. Could also dump `create_app().openapi()` for typed API clients.

## API and security

- [ ] Permissions beyond logged in / admin (per type, per object).
- [ ] Delete and undelete do not check the version (an `If-Match` could be accepted, as for an update, so a stale page cannot delete what has just been changed).
- [ ] Routes contributed by installed apps (an `<app>.api` router, as apps add CLI commands).
- [ ] Revoke open sessions when a password is changed (disabling a user already stops their tokens at once).
- [ ] Limit login attempts.
- [ ] CSRF protection for cookie sessions (only `SameSite` protects them now).
- [ ] `ENTITY_BASE_URL` is not used by anything (it was for generating entity URLs).
- [ ] A `500` from a bug has no CORS headers, so a browser reports a CORS error instead (Starlette; documented).

## Data and the Memgraph backend

- [ ] Remove deleted nodes for good; delete an entity that was marked for deletion when the last reference to it goes.
- [ ] A search with a page past the end reports a count of 0 (the plain list gives the real count).
- [ ] An entity's `ReferenceView` has no `meta`, a document's does.
- [ ] `service.set_admin` / `set_disabled` do not stop the last admin being demoted or disabled (the API stops admins changing their own status).

## Model layer

- [ ] Optional relations (`Person | None`), optional embedded objects, lists of embedded objects or annotated values, and plain `dict` fields: each raises an error at `initialise()`.
- [ ] The `"subtract"` type wrapper (opposite of `Fulfil`).
- [ ] `Relation[Subject, Object]` (a placeholder class).
- [ ] Interface languages (`INTERFACE_LANGUAGES`).
- [ ] Check whether "semantic spaces through `UpdateDB`" and "head node type and id through `CreateDB` / `UpdateDB`" are done (they are no longer in `packages/pangloss-models/todo.md`), and if so remove the two "Partial" rows in `docs/status.md`.

## Structure and packaging

- [ ] `pangloss-sdk` ("API as database") is stubs; only Memgraph exists as a real backend.
- [ ] `pangloss-core` depends on `pangloss-sdk`, which imports `pangloss-core` back.
- [ ] A project made by `pangloss new-project` has `dependencies = []`, as the Pangloss packages are not published.
- [ ] Running in production: workers, deployment notes (`pangloss run` is one process).

## Open design questions

See `notes/modelling.md`: specific, multi-tenant and generic roles, and when an activity should become a role.
