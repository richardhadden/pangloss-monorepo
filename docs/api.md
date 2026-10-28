# REST API

The API is the `pangloss-api` package, built with [FastAPI](https://fastapi.tiangolo.com/). It has the user endpoints, and routes made from the models of the project. Start it with `pangloss run` or, to restart on changes, `pangloss dev` (see [Command line](cli.md#running-the-server)).

```python
from pangloss_api.app import create_app

app = create_app()  # or: uvicorn "pangloss_api.app:create_app" --factory
```

`create_app()` uses the settings already imported, or else the module named by the environment variable `PANGLOSS_SETTINGS`. Building the app imports the `models` module of each installed app and runs `initialise()` (the routes are made from the models); starting the server (the app's lifespan) connects to the database through the `setup` module of `DATABASE_MODULE` (see [Command line](cli.md#what-a-database-backend-supplies)). A short `AUTHJWT_SECRET_KEY` (under 32 characters) gives a warning.

## CORS: using the API from a frontend

A browser only lets a page use the API if the API says that the page's origin may. Put the origins of the frontends in `BACKEND_CORS_ORIGINS`:

```python
BACKEND_CORS_ORIGINS: list = ["http://localhost:5173", "https://app.example.com"]
```

An origin is a scheme, host and port, with no path (a trailing `/` is dropped, and the case does not matter); a string of origins separated by commas is accepted, so it can be set in the environment or `.env` as `BACKEND_CORS_ORIGINS=http://localhost:5173,https://app.example.com` (if the class does not declare the field again; a JSON list works anyway). A project made with `pangloss new-project` allows `http://localhost:5173`, where the dev server of Vite and SvelteKit runs. With the list empty there is no CORS: only a page of the API's own origin can use it.

For those origins, the API answers preflight requests and allows the methods `GET POST PUT PATCH DELETE`, and the headers `Authorization`, `Content-Type`, `Accept` and `If-Match`; the frontend can read the response header `ETag`. Errors carry the headers too, so that the frontend can read them, including a `500` from a bug (answered with `{"detail": "Internal server error"}`, and the exception is logged).

- **Tokens:** send `Authorization: Bearer <access token>`; nothing more is needed.
- **Cookie sessions:** the frontend has to ask for the cookies to be used, with `fetch(url, { credentials: "include" })`, and the API allows that for the origins in the list. Cookies are sent between pages and an API of the same *site*, which is the host name without the port (`localhost:5173` and `localhost:8000`, yes; `127.0.0.1:5173` and `localhost:8000`, no, so use one name for both). Between different sites, the cookies need `AUTH_COOKIE_SAMESITE = "none"` and HTTPS (`Secure` is then set), or tokens should be used instead.
- **`*`** allows any site to use the API, but without credentials, so only tokens work (a cookie of a visitor must not be usable by any site). It gives a warning.

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

## Sessions ending, and personal access tokens

Each access and refresh token has an id (`jti`) and the user's `token_generation` at the time. A token is refused (401) if it has been **revoked** (logout: `POST /token/revoke`, `DELETE /session`; the id is kept until the token would have expired anyway), or if it was made before the user's sessions were **ended**: a password change (by the user, an admin, or the CLI) and `POST /me/logout-all` raise the user's generation. The access token is checked on every request, as the user already is, at the cost of one more lookup.

A **personal access token** (`pgl_...`) is for scripts and `git`: long-lived, named, revocable, optionally expiring, and with a scope: `read` can only use `GET`, `HEAD` and `OPTIONS` (403 otherwise), `write` does what the user can. It is used as `Authorization: Bearer pgl_...`, or as the password of HTTP Basic (the SDK's downloads and git). It is not a session's: `logout-all` does not end it, only revoking it does, or disabling the user. Memgraph keeps them as `PGAccessToken` nodes (the hash, never the token) and revocations as `PGRevokedSession`; they are indexed (unique) by a migration of `pangloss_memgraph`, and a token notes when it was last used (at most once in 10 minutes).

**Wrong passwords** are limited: after `LOGIN_MAX_FAILURES` for a username within `LOGIN_FAILURE_WINDOW_SECONDS` the username gets `429` with `Retry-After` (even for the right password) until the oldest failure is out of the window. It is kept in memory in each server process, so it slows guessing and is not a proxy's rate limit.

## User endpoints

All under `/api/users`. A `User` never includes a password or its hash.

| Endpoint | Who | |
|----------|-----|--|
| `POST /token` | anyone | Form `username`, `password` (OAuth2). Returns `access_token`, `refresh_token`, `token_type`, `expires_in` |
| `POST /token/refresh` | anyone | `{"refresh_token": ...}` returns a new access token |
| `POST /session` | anyone | Same form; sets the cookies |
| `POST /session/refresh` | the refresh cookie | A new access cookie |
| `DELETE /session` | anyone | Clears the cookies, and revokes the tokens in them |
| `POST /token/revoke` | anyone with the token | `{"refresh_token": ...}`: it stops working (204; a token that is not good is ignored). An access token already made lasts until it expires |
| `GET /me` | logged in | The current `User` |
| `PATCH /me` | logged in | `email` and/or `full_name` |
| `PUT /me/password` | logged in | `{"old_password", "new_password"}`. **Ends every session**, this one too: log in again |
| `POST /me/logout-all` | logged in | End every session of yours: all tokens made until now stop working (204). Personal access tokens go on |
| `POST /me/tokens` | logged in (not with a personal access token) | `{"name", "scope": "read" \| "write", "expiresDays"}`: a **personal access token**. The token is in the answer once (`token`); it is kept only as a hash. 201 |
| `GET /me/tokens` | logged in | Your tokens (id, name, scope, dates), never the tokens |
| `DELETE /me/tokens/{id}` | logged in | Revoke one (204; 404 if it is not yours) |
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

For every Document and Entity of the project, `NAME` being the class name (so `Person`, not `person`). Class names are unique, so the kind is not in the path: the server knows which a name is. **An abstract class has only the two routes that read** (`GET /api/NAME` and `GET /api/NAME/{id}`): they list and find the items of its subclasses, each as its own class (`type` says which, and `Content-Location` is its route). Nothing is created, edited, updated or deleted at an abstract class: `POST` is a 405, and the other routes are not there. Use the subclass.

(A model cannot be called `users`, `docs`, `redoc` or `openapi.json`, whatever the case: those are used by the API, and `initialise` refuses it.)

| Endpoint | Login | |
|----------|-------|--|
| `GET /api/NAME` | no | A page of a list. Parameters: `q` (searches the labels), `deep` (search more), `page`, `page_size` (up to 500). Includes the subtypes of `NAME`. Returns `results` (summaries), `count`, `page`, `page_size`, `next_page`, `previous_page` |
| `GET /api/autocomplete` | no | Entities whose label has every word of `q`, over the entity types named by `type` (repeated; or `Entity`). A page: `page`, `page_size` (up to 50). Returns `results` (`id`, `type`, `label`), `count`, `page`, `page_size`, `next_page`, `previous_page`. See [Autocomplete](autocomplete.md) |
| `POST /api/search` | no | Head documents or entities that fit a JSON pattern (`type`, `where`: field → condition, `page`, `page_size` up to 100). Answers a page of reference views, as the lists do; a pattern that cannot be made is a 422 naming the field and operator. So far: literal fields, lists, and relations by id or by a nested pattern, with `$all`, `$any_of`, `$not`, `$any`, `$somewhere`, `$mentions`, `$spaces`, `$incoming` and `through`. A search that takes longer than `SEARCH_TIMEOUT_SECONDS` is a `504`. See [Structured search](structured-search.md) |
| `GET /api/NAME/{id}` | no | The `HeadView`; 404 if there is none, or it has been deleted. For an entity, `{id}` can be one of its URLs (see below). **If the item is a subclass of `NAME`, this is the view of that subclass** (its `type` says which) and the header `Content-Location` is its own route (`/api/Sub/{id}`) |
| `POST /api/NAME` | yes | Create, with the body of `NAME.Create`. Returns 201 and a summary (`ReferenceView`), or with `?detail=true` the whole `HeadView` |
| `GET /api/NAME/{id}/edit` | yes | What to edit: for an entity its `EditView` (no incoming relations), for a document its `HeadView`. For an item that is a subclass of `NAME`: **`308` to `/api/Sub/{id}/edit`**, as the edit view and the body of an update are the subclass's |
| `PUT /api/NAME/{id}` | yes | Update, with the body of `NAME.Update`: a full replacement, which what `/edit` returns can be sent back as. The `id` in the body must be the one in the path (400); the item must be a `NAME` and not a subclass of it (409, naming the route to use); and the header `If-Match` says which version it is based on (see below). Returns a summary, or with `?detail=true` the `HeadView` |
| `DELETE /api/NAME/{id}` | yes | Delete. 204 |
| `POST /api/NAME/{id}/undelete` | yes | Undelete. 204 |

**Versions: editing without overwriting.** Each Document and Entity has a `meta.version`: 1 when it is made, and 1 more for each update. An update replaces the whole thing, so if two people load it, and both save, the second would silently undo the first. To prevent that, an update says which version it is based on:

1. `GET /api/NAME/{id}/edit` returns the version in the header `ETag` (`"3"`), as well as in `meta.version`. (The create and update responses have it too: `"1"`, and the version made.)
2. `PUT /api/NAME/{id}` has to have the header `If-Match: "3"`. If that is still the latest version, the update is made, and the response has the new `ETag` (`"4"`; after `?detail=true`, from the `HeadView`).
3. If someone has updated it since, nothing is written and the response is **412 Precondition Failed**, with `currentVersion` and the current `ETag`. The frontend loads the edit view again, to show what has changed, and the user saves from there. Nothing is merged for them.
4. Without the header the response is **428 Precondition Required**: an update cannot be blind. `If-Match: *` updates whatever the version is (a deliberate overwrite; the response then has no `ETag`, so load it again to go on). A header that is not a version, or is a weak ETag (`W/"3"`), is 400.

The version belongs to the thing itself: a change in what refers to an entity does not change the entity's version, and deleting or undeleting does not change it.

Everything can be looked at by anyone; creating, loading for edit, updating, deleting and undeleting need a logged-in user, whose name is recorded as the creator or updater. (Finer permissions are not written yet ⏳.) A disabled user is refused with 401.

The JSON is `camelCase` throughout (`bornIn`, `meta.createdBy`, `aboutPersonReverse`), though the models declare their fields in `snake_case`. Requests accept either. (The models do this with an `alias_generator`, and a pass at the end of `initialise()` that gives the same aliases to the fields added to the generated models afterwards.)

| Status | When |
|--------|------|
| 412 | An update based on a version that is no longer the latest (see below) |
| 428 | An update without `If-Match` |
| 400 | The `id` in an update body is not the one in the path; loading to edit, updating, deleting or undeleting an entity at a URL; deleting a document that is part of another (`PanglossNotDeletableError`); other rejected writes |
| 401 | Not logged in |
| 404 | No such item (also: update, delete or undelete of one that does not exist) |
| 409 | (Every error answer has `detail` and `error`, the name of the exception class, which the SDK raises again.) An id already in use; undeleting what is not deleted; deleting an entity that is referred to. For the last, the response also has `referencedBy`, a list of `{id, type, label}`, and the entity is marked for deletion |
| 422 | A body that is not valid for the model; a reference to an entity that does not exist or is of the wrong type; a bad page |

**URLs.** An entity can be given URLs, such as its address in another database, by creating it with a URL as its `id` (if its class has `create_with_id`; the entity still gets an id of its own). To get an entity, one of its URLs can be put in the path instead of its `{id}`, as it is:

```
GET /api/Person/https://example.com/people/john-smith
```

The response has the entity's `id`. **Everything else is only ever at an id**: loading it to edit (`/edit`), and update, delete and undelete, are refused at a URL with 400 ("this is done at the id of an entity"), so get the entity at its URL first to find the id. Documents are found by id only. A URL can also refer to an entity in the body of a request (`{"type": "Person", "id": "http://..."}`). Details:

- The rest of the path is the URL, so one that ends in `/edit` or `/undelete` is taken for the route of that name.
- `http:/` is read as `http://`, as servers and proxies often merge slashes.
- The query string of the request is the URL's (`.../Place/http://example.com/p?id=5` is the URL with `?id=5`).
- Percent-encoded characters are decoded in the path, and the URL is then normalised as when it was stored. A URL that has an encoded `/`, `?` or `#` in it cannot be told apart this way.

The URLs of an entity are returned as a list, `urls`, in its `HeadView` and `EditView`. To change them, send `urls` in the update body (the `EditView` can be sent back changed): the list replaces the entity's URLs, so a URL left out is removed, and `[]` removes them all; if `urls` is not in the body they are left as they are. A URL that belongs to another entity (even a deleted one) is refused with 409.

The OpenAPI document (`/openapi.json`, with the interactive `/docs`) describes every route, with the schemas of the models.

## Routes from installed apps

An app in `INSTALLED_APPS` that has an `api.py` with a `router` (a FastAPI `APIRouter`) has it included in the API, as an app with a `cli.py` adds commands. An `api.py` can also have `configure_app(app, settings)`, called as the app is made, to add middleware to add an async function to `app.state.startup_hooks`, which the server calls as it starts (after the migrations are checked), or to add a `BackgroundTask` to `app.state.background_tasks` (below). (`pangloss_sdk_server` uses both: see [the SDK](sdk.md).) A model cannot be called `sdk` (it is reserved with `users`). The router gives its own prefix (`pangloss_interface` uses `/api/interface`). An error in the module is not hidden, and a `router` that is not an `APIRouter` is a `TypeError`.

## Background tasks

Something an installed app keeps running for as long as the server does (`pangloss_zotero` watches a library) is a
`BackgroundTask(name, run)` added to `app.state.background_tasks` in `configure_app`, where `run` is `async def
run(settings)` that loops until it is cancelled. The server runs each as an `asyncio` task on its own event loop, after
the migrations are checked and the startup hooks have run, and cancels them (waiting 5 s) before the database
disconnects. A task that raises is logged, with the traceback, and started again after 1 s, doubling to 60 s (back to 1 s
after a run that lasted a minute); one that returns, or is cancelled, is not started again. `app.state.supervisor.status()`
gives each task's state, number of restarts and last error. With several server workers each would run its tasks: see
[Zotero](zotero.md#background-tasks-in-pangloss-api) for how a task is run apart. Built in `pangloss_api/background.py`.

## Fields that are kept up to date by something else

A model with `_protect_meta = Protection(read_only=("title",), delete_only_if="removed")` (see [meta slots](meta-slots.md))
has those fields protected in the routes: a create that sets one, an update that changes one (leaving it out counts), and a
delete while `removed` is not true, are refused with `403` and a message saying which. Code that writes through Python,
such as a sync, is not stopped.

## Not done yet ⏳

- Limiting login attempts.
- A route to list the types.
- Per-type or per-object permissions.
