# Users, logins and the REST API

`pangloss-users` holds users and passwords; `pangloss-api` is the FastAPI application that serves your models and logs
people in. The two packages are always installed together on a server.

## Users

```bash
pangloss users create --username ada --email ada@example.org --admin      # prompts for a password
pangloss users list
pangloss users set-password ada
pangloss users --help
```

A user is a node in the database. Passwords are hashed with Argon2id (at least 8 characters). A **disabled** user is
refused at once, even with a token that has not expired. There are two levels of permission only: logged in, and admin.
Finer permissions (per type, per object) are not written; the decision is on the [TODO](../../TODO.md).

From Python: `pangloss_users.service.create_user`, `authenticate`, `change_password`, `set_admin`, `set_disabled`
([Users](../../docs/users.md)).

## Running the API

```bash
pangloss run --port 8000          # one process
pangloss dev                      # restarts on changes
```

It makes CRUD routes for every Document and Entity: `GET /api/Person` (list, `?q=`, `?deep=true`, paged), `GET
/api/Person/{id}`, `POST`, `GET /{id}/edit`, `PUT` (with `If-Match: <version>`), `DELETE`, `undelete`. **Reading is open;
changing needs a login.** Routes added by installed apps (history, review, typology, calendar, SDK, interface) are under
their own prefixes. The API's documentation is at `/docs`.

## Logging in

| | |
|---|---|
| `POST /api/users/token` (form: `username`, `password`) | An access token (30 minutes) and a refresh token (14 days). Send `Authorization: Bearer <access token>` |
| `POST /api/users/token/refresh` | A new access token from the refresh token |
| `POST /api/users/session` | The same tokens in HTTP-only cookies, for a browser |
| `POST /api/users/token/revoke`, `DELETE /api/users/session` | Log out: the token is revoked |
| `POST /api/users/me/logout-all` | End every session. A password change does too |
| `GET /api/users/me` | Who you are |

Wrong passwords are limited per username (`LOGIN_MAX_FAILURES`, default 10 in `LOGIN_FAILURE_WINDOW_SECONDS`, 300): the
username then gets `429` with `Retry-After`.

### Personal access tokens: for scripts

A long-lived, named, revocable token with a scope, for a script, an import job, `git` and `pip`:

```bash
pangloss users tokens create ada --name "nightly import" --scope read --expires-days 90     # printed once
pangloss users tokens list ada
pangloss users tokens revoke ada <token id>
```

Users can make their own at `POST /api/users/me/tokens`. Use `Authorization: Bearer pgl_…`, or the token as the password of
HTTP Basic. Scope `read` can only `GET`. Logging everyone out does not end a token; revoking it, or disabling the user,
does.

## Writing safely: versions

Every head document has a `meta.version`. An update sends the version it was based on as `If-Match`; if someone saved
first the answer is `412` (with `currentVersion`) and nothing changes. The Python and SDK form is `save(expected_version=…)`.

## From a browser

Set `BACKEND_CORS_ORIGINS` to the frontend's origin(s). With cookies, use one host name for the page and the API (cookies are
per site), set `AUTH_COOKIE_SECURE` over HTTPS, and note that only `SameSite` protects them from CSRF. A frontend on
another site should use tokens. [REST API](../../docs/api.md) has the table of every setting and route.

## From a script

Do not write HTTP by hand: use the [SDK](../sdk/README.md). It is the same API with your models as classes.
