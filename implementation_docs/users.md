# Users

`pangloss_users` holds the user models, password hashing and a `service` module; the users themselves are stored by the database backend (as `(:PGUser)` nodes in Memgraph). The tokens, sessions and routes for users are in the [REST API](api.md); permissions are not written yet ⏳.

```python
from pangloss_users import service

user = await service.create_user(
    "john", "john@example.com", "a long password", admin=True
)
user = await service.authenticate("john", "a long password")  # a User, or None
await service.change_password("john", "a long password", "another password")
await service.set_disabled("john", True)
```

## Models

| Model | Purpose |
|-------|---------|
| `User` | A user as it can be shown: `username`, `email`, `full_name`, `admin`, `disabled`, `created_when`. Never has a password or hash |
| `UserCreate` | `username`, `email`, `password`, `full_name` |
| `UserUpdate` | `email`, `full_name`; what is left out is kept |
| `UserInDB` | A `User` with `hashed_password`; only the backend and `service` see it |
| `AccessTokenInfo`, `AccessTokenRecord` | A personal access token as it can be shown, and as it is stored (with `token_hash`) |

`User` also has `token_generation` (not shown): raising it ends the user's sessions. `set_password` and `end_sessions` do. `service` also has `revoke_session` / `is_session_revoked`, and `create_access_token`, `list_access_tokens`, `revoke_access_token` and `authenticate_access_token` (see [the API](api.md#sessions-ending-and-personal-access-tokens)); a backend supplies `revoke_session_in_db`, `is_session_revoked_in_db`, `create_access_token_in_db`, `get_access_token_in_db_by_hash`, `list_access_tokens_in_db` and `delete_access_token_in_db`.

A username can contain letters, numbers, `_`, `.` and `-` (at most 64 characters). A user made by hand, such as `pangloss_default_user` in the tests, may have no email or password; it cannot log in.

## Toolchains, and who made an item ✅

A **toolchain** is a user of `kind` `toolchain` (`User.kind`: `user` or `toolchain`): a program that makes data from
what a person prepared. It has no email or password and cannot log in; `service.create_toolchain(name, full_name)`,
`pangloss users create-toolchain NAME`, `POST /api/users/toolchains` (admin) and **New toolchain** on the admin page
make one. It is listed with the users, flagged.

An item is made by one or more people, and perhaps a toolchain: `meta.created_by` is a **list** of
`pangloss_models.Creator` (`username`, `kind`, and for a toolchain the `version` and `date` of the run), people
first, in the order given; `meta.uploaded_by` is the admin who wrote it for them. Stored as a `created_by` edge for
each from the `PGCreation` record (`position`, `version`, `date` on the edge; `uploaded_by` on the record); a record
with one edge and no position is what all data had before, and reads as one creator. A part of a document keeps who
made it in its own `meta`: the name, for one person, or JSON text of the list.

```python
await Factoid.Create(...).save(created_by=["ann", "bob"], toolchain=ToolchainRun("extractor", version="1.2"))
```

Over the API, `?created_by=ann&created_by=bob&toolchain=extractor&toolchain_version=1.2&toolchain_date=2026-11-01` on
a `POST`, for an admin (403 otherwise); a name that is not a user, or of the wrong kind, is a 422. In a script,
`with pangloss_models.creators.writing_as(creators_asked([...])):` does it for what is created inside. `updated_by`
is one name, whoever made the update. `current_request_is_admin` (beside `current_request_username`) says whether the
user of the request is an admin; true outside a request.

## Passwords

Hashed with Argon2id (`argon2-cffi`) and a random salt; at least 8 characters. `authenticate` checks a hash even when there is no such user, so the time taken does not show whether the username exists, and re-hashes the password if the hash was made with weaker parameters than are now used. (Hashes from the earlier, bcrypt, version of Pangloss are not accepted.)

## `service`

All are `async`.

| Function | Notes |
|----------|-------|
| `create_user(username, email, password, full_name=None, admin=False)` | `PanglossInvalidUserError` for a bad username, email or password; `PanglossUserExistsError` if the username or email is taken |
| `get_user(username)`, `get_user_by_email(email)` | `User` or `None` |
| `list_users()` | Ordered by username |
| `list_user_summaries()` | Everyone, as `UserSummary` (`username`, `full_name`): what any logged-in user may see |
| `list_user_items(username, page=1, page_size=25)` | A page (`UserItems`) of the entities and top-level documents the user made or changed, the last touched first, each once with its last `action` (`created` or `modified`) and `when`. What the request may not see is left out; `PanglossUserDoesNotExistError` |
| `authenticate(username, password)` | The `User`, or `None` if the password is wrong, there is no such user, or the user is disabled (it does not say which) |
| `update_user(username, UserUpdate)` | `PanglossUserDoesNotExistError`; `PanglossUserExistsError` for an email in use |
| `set_password(username, password)`, `change_password(username, old, new)` | `change_password` checks the old one |
| `set_admin(username, admin)`, `set_disabled(username, disabled)` | A disabled user cannot log in or write; what they wrote stays |

`service` does not stop the last admin being disabled or demoted (the API does not let admins change their own status).

## In the interface ✅

`pangloss_users` has an interface module (`pangloss_users/interface/`), for someone logged in: `/users` (linked from the navigation bar) and `/users/:username`, what that user has made or changed, the most recent first. A name in the console's "created" and "modified" rows links to that page (`userHref` in the module's manifest; logged out it is plain text).

With `pangloss_admin` installed, the module also adds a **Users** section to `/admin` ✅ (a `slots` entry; `UsersAdminSection.tsx`), which does all that `pangloss users` does: list, create, set a password, make or remove an admin, disable or enable, and make, list and revoke personal access tokens; it also edits the full name and email and ends a user's sessions. A change is made at once, with no Save: a button acts when pressed, and a name or email is sent when the field is left or Enter is pressed. It is shown at once too (`createOptimisticStore`, `state.ts`), held until the feed brings it back, and undone with the reason if the API refuses; a new user or token appears dimmed until then. What is shown comes from `live()` feeds (`feed.ts`: the interface's server asks `GET /api/users`, and `GET /api/users/{username}/tokens` while the tokens dialog is open, every `PANGLOSS_ADMIN_POLL_MS`, default 1000), so a change made by another admin or at the command line appears on the open page. A feed is closed while its tab is hidden (`whileVisible`), as each open one holds one of the browser's six connections to the host. An admin cannot change their own admin or disabled status there (the API refuses, unlike the command line). Ending your own sessions, or setting your own password, logs you out.

The routes for admins beside those for the status are `POST /api/users/{username}/logout-all` and `GET`, `POST`, `DELETE /api/users/{username}/tokens[/{id}]` (making a token, as with `/me/tokens`, needs a login and not another token).

## What a backend supplies

`service` calls these in the `exposed_functions` of the storage backend (`STORAGE`): `create_user_in_db(user)`, `get_user_in_db(username)`, `get_user_in_db_by_email(email)`, `list_users_in_db()` and `update_user_in_db(username, changes)`. The Memgraph versions are in `pangloss_memgraph/databases/memgraph/users.py`; `initialise_database` adds unique constraints on `PGUser.username` and `PGUser.email`.

## Writes by a user

`current_request_username` names who is writing. The Memgraph backend refuses a write by a user with no node (`PanglossUserNotFoundError`) or a disabled one (`PanglossUserDisabledError`).
