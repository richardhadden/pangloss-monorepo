# Users

`pangloss_users` holds the user models, password hashing and a `service` module; the users themselves are stored by the database backend (as `(:PGUser)` nodes in Memgraph). Tokens, sessions, permissions and the API routes are not written yet ⏳.

```python
from pangloss_users import service

user = await service.create_user("john", "john@example.com", "a long password", admin=True)
user = await service.authenticate("john", "a long password")   # a User, or None
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

A username can contain letters, numbers, `_`, `.` and `-` (at most 64 characters). A user made by hand, such as `pangloss_default_user` in the tests, may have no email or password; it cannot log in.

## Passwords

Hashed with Argon2id (`argon2-cffi`) and a random salt; at least 8 characters. `authenticate` checks a hash even when there is no such user, so the time taken does not show whether the username exists, and re-hashes the password if the hash was made with weaker parameters than are now used. (Hashes from the earlier, bcrypt, version of Pangloss are not accepted.)

## `service`

All are `async`.

| Function | Notes |
|----------|-------|
| `create_user(username, email, password, full_name=None, admin=False)` | `PanglossInvalidUserError` for a bad username, email or password; `PanglossUserExistsError` if the username or email is taken |
| `get_user(username)`, `get_user_by_email(email)` | `User` or `None` |
| `list_users()` | Ordered by username |
| `authenticate(username, password)` | The `User`, or `None` if the password is wrong, there is no such user, or the user is disabled (it does not say which) |
| `update_user(username, UserUpdate)` | `PanglossUserDoesNotExistError`; `PanglossUserExistsError` for an email in use |
| `set_password(username, password)`, `change_password(username, old, new)` | `change_password` checks the old one |
| `set_admin(username, admin)`, `set_disabled(username, disabled)` | A disabled user cannot log in or write; what they wrote stays |

Nothing stops the last admin being disabled or demoted ⏳.

## What a backend supplies

`service` calls these in the `exposed_functions` of `DATABASE_MODULE`: `create_user_in_db(user)`, `get_user_in_db(username)`, `get_user_in_db_by_email(email)`, `list_users_in_db()` and `update_user_in_db(username, changes)`. The Memgraph versions are in `pangloss_memgraph/databases/memgraph/users.py`; `initialise_database` adds unique constraints on `PGUser.username` and `PGUser.email`.

## Writes by a user

`current_request_username` names who is writing. The Memgraph backend refuses a write by a user with no node (`PanglossUserNotFoundError`) or a disabled one (`PanglossUserDisabledError`).
