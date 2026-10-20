# REST API

The API is the `pangloss-api` package, built with [FastAPI](https://fastapi.tiangolo.com/). So far it has the user endpoints; the routes for documents and entities, and `pangloss run` / `pangloss dev` to start the server, are not written yet ⏳.

```python
from pangloss_api.app import create_app

app = create_app()   # e.g. served with: uvicorn "pangloss_api.app:create_app" --factory
```

`create_app()` uses the settings already imported, or else the module named by the environment variable `PANGLOSS_SETTINGS`. Starting the server (the app's lifespan) imports the `models` module of each installed app, runs `initialise()`, and connects to the database through the `setup` module of `DATABASE_MODULE` (see [Command line](cli.md#what-a-database-backend-supplies)). A short `AUTHJWT_SECRET_KEY` (under 32 characters) gives a warning.

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

A wrong username, password, an unknown user or a disabled user all give the same 401 at login. An admin cannot change their own `admin` or `disabled` status (400), so that the last admin cannot lock everyone out.

| Status | When |
|--------|------|
| 401 | No token, a bad, expired or wrong-type token, a disabled or deleted user |
| 403 | Not an admin, or reading another user's details as an ordinary user |
| 404 | No such user |
| 409 | Username or email already in use |
| 422 | A bad username, email or password (including a wrong old password) |

## Not done yet ⏳

- Revoking tokens: changing a password does not end sessions already open (their tokens last until they expire).
- Limiting login attempts.
- Routes for documents and entities, and for `INSTALLED_APPS` to add their own.
