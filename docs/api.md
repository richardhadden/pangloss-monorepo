# REST API

The API is the `pangloss-api` package, built with [FastAPI](https://fastapi.tiangolo.com/). It has the user endpoints, and routes made from the models of the project. Start it with `pangloss run` or, to restart on changes, `pangloss dev` (see [Command line](cli.md#running-the-server)).

```python
from pangloss_api.app import create_app

app = create_app()   # or: uvicorn "pangloss_api.app:create_app" --factory
```

`create_app()` uses the settings already imported, or else the module named by the environment variable `PANGLOSS_SETTINGS`. Building the app imports the `models` module of each installed app and runs `initialise()` (the routes are made from the models); starting the server (the app's lifespan) connects to the database through the `setup` module of `DATABASE_MODULE` (see [Command line](cli.md#what-a-database-backend-supplies)). A short `AUTHJWT_SECRET_KEY` (under 32 characters) gives a warning.

## Authentication

Logging in gives either **tokens** or a **session**.

| | |
|--|--|
| Tokens | `POST /api/users/token` returns an access token and a refresh token. Send the access token as `Authorization: Bearer <token>` |
| Session | `POST /api/users/session` puts the two tokens in HTTP-only cookies (`pangloss_access`, `pangloss_refresh`); a request with the access cookie is logged in |

Both are JWTs signed with `AUTHJWT_SECRET_KEY` (HS256). Each has the username as its subject and a `type` (`access` or `refresh`), and a token of one kind is refused where the other is wanted. The user is looked up on every request, so a user who has been disabled is refused at once, even with a token that has not expired.

An authenticated request sets `current_request_username`, so what the user writes is recorded as theirs.

| Setting | Default | |
|---------|---------|--|
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | |
| `AUTH_REFRESH_TOKEN_EXPIRE_DAYS` | `14` | |
| `AUTH_COOKIE_SAMESITE` | `"lax"` | `"lax"`, `"strict"` or `"none"` (which also sets `Secure`) |
| `AUTH_COOKIE_SECURE` | `False` | Set it when serving over HTTPS |

Cookies are protected from CSRF only by `SameSite`; there is no CSRF token. With `"none"` (a frontend on another site), prefer tokens in the `Authorization` header.

## User endpoints

All under `/api/users`. A `User` never includes a password or its hash.

| Endpoint | Who | |
|----------|-----|--|
| `POST /token` | anyone | Form `username`, `password` (OAuth2). Returns `access_token`, `refresh_token`, `token_type`, `expires_in` |
| `POST /token/refresh` | anyone | `{"refresh_token": ...}` returns a new access token |
| `POST /session` | anyone | Same form; sets the cookies |
| `POST /session/refresh` | the refresh cookie | A new access cookie |
| `DELETE /session` | anyone | Clears the cookies |
| `GET /me` | logged in | The current `User` |
| `PATCH /me` | logged in | `email` and/or `full_name` |
| `PUT /me/password` | logged in | `{"old_password", "new_password"}` |
| `GET /` | admin | All users |
| `POST /` | admin | `username`, `email`, `password`, `full_name`, `admin`. Returns 201 |
| `GET /{username}` | admin, or that user | |
| `PATCH /{username}` | admin | `email`, `full_name` |
| `PUT /{username}/password` | admin | `{"password"}` |
| `PUT /{username}/admin` | admin | `{"admin": bool}` |
| `PUT /{username}/disabled` | admin | `{"disabled": bool}` |

The JSON of the user endpoints is `camelCase` too (`fullName`, `createdWhen`, `oldPassword`). The exception is the two token endpoints (`/token` and `/token/refresh`), which use the names OAuth2 defines (`access_token`, `refresh_token`, `token_type`, `expires_in`), as clients and the interactive docs expect them.

A wrong username, password, an unknown user or a disabled user all give the same 401 at login. An admin cannot change their own `admin` or `disabled` status (400), so that the last admin cannot lock everyone out.

| Status | When |
|--------|------|
| 401 | No token, a bad, expired or wrong-type token, a disabled or deleted user |
| 403 | Not an admin, or reading another user's details as an ordinary user |
| 404 | No such user |
| 409 | Username or email already in use |
| 422 | A bad username, email or password (including a wrong old password) |

## Routes for the models

For every Document and Entity of the project that is not abstract, `NAME` being the class name (so `Person`, not `person`), and `KIND` being `documents` or `entities`:

| Endpoint | Login | |
|----------|-------|--|
| `GET /api/KIND/NAME` | no | A page of a list. Parameters: `q` (searches the labels), `deep` (search more), `page`, `page_size` (up to 500). Includes the subtypes of `NAME`. Returns `results` (summaries), `count`, `page`, `page_size`, `next_page`, `previous_page` |
| `GET /api/KIND/NAME/{id}` | no | The `HeadView`; 404 if there is none, or it has been deleted |
| `POST /api/KIND/NAME` | yes | Create, with the body of `NAME.Create`. Returns 201 and a summary (`ReferenceView`), or with `?detail=true` the whole `HeadView` |
| `GET /api/KIND/NAME/{id}/edit` | yes | What to edit: for an entity its `EditView` (no incoming relations), for a document its `HeadView` |
| `PUT /api/KIND/NAME/{id}` | yes | Update, with the body of `NAME.Update`: a full replacement, which what `/edit` returns can be sent back as. The `id` in the body must be the one in the path (400). Returns a summary, or with `?detail=true` the `HeadView` |
| `DELETE /api/KIND/NAME/{id}` | yes | Delete. 204 |
| `POST /api/KIND/NAME/{id}/undelete` | yes | Undelete. 204 |

Everything can be looked at by anyone; creating, loading for edit, updating, deleting and undeleting need a logged-in user, whose name is recorded as the creator or updater. (Finer permissions are not written yet ⏳.) A disabled user is refused with 401.

The JSON is `camelCase` throughout (`bornIn`, `meta.createdBy`, `aboutPersonReverse`), though the models declare their fields in `snake_case`. Requests accept either. (The models do this with an `alias_generator`, and a pass at the end of `initialise()` that gives the same aliases to the fields added to the generated models afterwards.)

| Status | When |
|--------|------|
| 400 | The `id` in an update body is not the one in the path; deleting a document that is part of another (`PanglossNotDeletableError`); other rejected writes |
| 401 | Not logged in |
| 404 | No such item (also: update, delete or undelete of one that does not exist) |
| 409 | An id already in use; undeleting what is not deleted; deleting an entity that is referred to. For the last, the response also has `referencedBy`, a list of `{id, type, label}`, and the entity is marked for deletion |
| 422 | A body that is not valid for the model; a reference to an entity that does not exist or is of the wrong type; a bad page |

The OpenAPI document (`/openapi.json`, with the interactive `/docs`) describes every route, with the schemas of the models.

## Not done yet ⏳

- Revoking tokens: changing a password does not end sessions already open (their tokens last until they expire).
- Limiting login attempts.
- Routes from `INSTALLED_APPS` (an app's own), reading an entity by one of its URLs, and a route to list the types.
- Per-type or per-object permissions.
