# Logging

Everything Pangloss logs goes to a logger under `pangloss` (`pangloss.api.auth`, `pangloss.memgraph.queries`, ...),
through Python's `logging`. The server sets up one handler (to stderr) when the app is made, from the settings:

| Setting | Default | |
|---|---|---|
| `LOG_LEVEL` | `"INFO"` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` |
| `LOG_FORMAT` | `"text"` | `"text"`: `2026-10-24 10:00:00 INFO pangloss.api.auth [3f2a…] Login: 'ann' from 10.0.0.2 (token)`; `"json"`: one object a line, with `time`, `level`, `logger`, `message`, `request_id` and `exception` |
| `SLOW_QUERY_MS` | `500` | a database transaction over this is a warning |
| `SLOW_REQUEST_MS` | `2000` | a request over this is a warning |

One area can be turned up alone: `logging.getLogger("pangloss.memgraph.queries").setLevel("DEBUG")`. The command line
(`pangloss migrate` and the rest) logs only warnings and errors, as it shows its own progress, unless `LOG_LEVEL` is
`DEBUG`. The SDK (`pangloss.sdk.client`) is a library: it logs, and leaves the handler to the program that uses it.

## Rules

- **No secrets, no content.** Never a password, a token, an `Authorization` header, or the content of a document or entity;
  ids, model names, counts and the *names* of query parameters. As a last defence the handler replaces anything that looks
  like a secret (a JWT, a `pgl_` token, `Bearer ...`, `password=...`) with `[redacted]`, including in tracebacks.
- A username from a client is logged with `%r`, so it cannot make a line of its own.
- A failure is logged once, where it is dealt with.
- A request has a **request id**: the `X-Request-ID` the client sent (if it is short and plain: letters, digits, `.`, `_`, `-`),
  or one made by the server. It is on every record made for the request, and sent back in the `X-Request-ID` header.

## What is logged

| Level | What | Logger |
|---|---|---|
| ERROR | an unhandled error in a request (with the traceback) | `pangloss.api.errors` |
| ERROR | the database cannot be reached | `pangloss.memgraph.transactions` |
| ERROR | a migration failed; the migration lock is held by another run; start-up refused for migrations (`MIGRATION_CHECK = "error"`) | `pangloss.memgraph.migrations`, `pangloss.api.app` |
| ERROR/exception | a history record dropped or lost; a listener to writes failed; the SDK could not be built or committed | `pangloss.history`, `pangloss.models.hooks`, `pangloss.sdk` |
| WARNING | login throttled (`429`); wrong password (user, address) | `pangloss.api.auth` |
| WARNING | an edit conflict (`412`); a write refused during a migration | `pangloss.api.errors` |
| WARNING | migrations pending at start-up (`MIGRATION_CHECK = "warn"`); a relation that cannot be shown; the SDK is out of date; a slow transaction or request | `pangloss.api.app`, `pangloss.memgraph.read`, `pangloss.sdk.client`, `pangloss.memgraph.transactions`, `pangloss.api.requests` |
| INFO | start-up (project, database module, models, apps), ready, stopped; connected to and disconnected from Memgraph (no credentials); database setup | `pangloss.api.app`, `pangloss.memgraph.setup` |
| INFO | login (user, address, token or session), token refresh, logout, password changes, personal access tokens made and revoked, users made, made admin or disabled | `pangloss.api.auth` |
| INFO | each write: `Write: create Person <id> v1 by 'ann'` (never what it said) | `pangloss.models.hooks` |
| INFO | migrations: lock taken and released, each applied or undone, snapshot taken | `pangloss.memgraph.migrations` |
| INFO | history recording started and stopped (written, dropped, lost: a warning if any were); an upgrade of a stored version | `pangloss.history`, `pangloss.history.upgrade` |
| DEBUG | each request when done: method, path (not the query string), status, time | `pangloss.api.requests` |
| DEBUG | each database statement (cut to 600 characters) with the *names* of its parameters, and each transaction's time. Switched on only when DEBUG is on for `pangloss.memgraph.queries`, as it wraps the transaction | `pangloss.memgraph.queries`, `pangloss.memgraph.transactions` |
| DEBUG | model initialisation; the SDK client's calls, retries, logins and token refreshes | `pangloss.models.registry`, `pangloss.sdk.client` |

The time of a statement is how long the database took to take it up; the rows are read afterwards, so the time of the
whole transaction (`... transaction X took N ms`) is the one to look at.
