# SDK: using a project's models against its API ⏳

**Status: a design, not built.** Nothing here exists yet except the stub `pangloss-sdk` package (settings, and an
`exposed_functions` module of placeholders). Statements about the existing code were checked on 2026-10-23.

The aim: someone who works with a Pangloss project's data (a script, a notebook, an analysis, a data import) gets
**the project's own model classes**, with type stubs, from the running server, and uses them as the server does:
`await Person.get(id)`, `await Person.Create(...).save()`, `await Person.list(...)`. Every one of those is a request
to the API. The user needs no database credentials, no access to Memgraph, and no copy of the project.

## What exists now

- Models are declared in Python (`demo_app/models.py`). `initialise()` generates `Create`, `Update`, `View`,
  `HeadView`, `EditView` and the rest, then **binds** `get`, `list`, `save`, `delete`, ... to the functions of the
  module named by `SETTINGS.DATABASE_MODULE` (`<module>.exposed_functions`). Sync and async both work
  ([generated models](generated-models.md#the-initialisation-pipeline)). This is the seam the SDK uses.
- `pangloss-sdk` has `ApiAsDatabaseSettings`, a `setup` module of no-ops, and an `exposed_functions` of stubs
  (`get_document` returns an invented object). The model tests use it as a database that needs no connection.
- The API has a route for each model (`GET/POST /api/NAME`, `/{id}`, `/{id}/edit`, `PUT` with `If-Match`, `DELETE`,
  `undelete`), JSON in `camelCase`, tokens and sessions ([REST API](api.md)). Errors have distinct statuses
  (404, 409, 412, 422...).
- `pangloss make-stubs` writes a `.pyi` beside each module that declares models
  ([type stubs](cli.md#type-stubs)).
- Migrations give each state of the models a `schema_hash`; a project's position is the last migration of each app
  (`pangloss_history.schema_position`).
- **Known problems** this design has to resolve:
  1. `pangloss-core` declares a dependency on `pangloss-sdk`, and the SDK's code imports `pangloss-core` and
     `pangloss-models` back (a cycle, noted in [packages](packages.md)).
  2. `BaseSettings` requires server things (`AUTHJWT_SECRET_KEY`, `BACKEND_CORS_ORIGINS`, `ENTITY_BASE_URL`,
     `DATABASE`). `pangloss-models` reads **one** setting, `DATABASE_MODULE` (`model_registry.py:386`), so a client
     should not have to give the rest.
  3. `pangloss-models` imports `neo4j` (`model_bases/from_database.py`, to convert `neo4j.time.DateTime`) without
     declaring it. A client would have to install the Bolt driver to use models.
  4. `pangloss-models` has `pydantic-meta-kit` from a git URL (`[tool.uv.sources]`), which an installed package
     cannot depend on from PyPI.

## Goals and non-goals

Goals:

- A **project-specific SDK**: a normal Python package holding the project's model classes, built by the server and
  **obtained from it** by a logged-in user (an admin, by default).
- **Installable and updatable with `git`**: `git clone` and `pip install git+https://...` work against the server,
  so keeping in step with the models is `git pull` / `pip install -U`.
- Type stubs included, so editors and type checkers see `Person.Create(...)` and the rest.
- The model functions are **requests to the API**, with the same arguments, results and exceptions as with a
  database. Code written against the SDK runs against the server's own database module too, with no change.
- The SDK knows whether it is **out of date** with the server, and says so.
- Login that is easy at a terminal or in a notebook, and workable in a script.

Non-goals (for the first version):

- Running the server's code on the client. Hooks that need the database (`to_db` on a model, anything that reads
  the graph) run on the server, when the request arrives.
- Offline use, caching, or syncing data.
- Transactions across calls. Each `save` is one request, and atomic on the server, as now.
- Other languages. (The OpenAPI document already serves them. A TypeScript SDK would be a separate generator.)
- Per-object permissions. The SDK acts as its user, with what that user may do ([users](users.md); the API's
  permissions are still "logged in" or "admin").

## The shape of it

Two packages, as `pangloss-history` is optional beside `pangloss-models`:

| | Installed by | Holds |
|---|---|---|
| **`pangloss-sdk`** (exists as a stub) | the SDK's users, as a dependency of the generated SDK | The **client**: the database module that turns model functions into HTTP requests, login, the settings, `pangloss-sdk` command |
| **`pangloss-sdk-server`** (new, optional app) | the project, in `INSTALLED_APPS` (`pangloss_sdk_server`) | The **builder** that generates a project's SDK, the routes that serve it (download, git), `pangloss sdk ...` commands |
| **The generated SDK** (one per project, named `<project>-sdk`) | the user, from the server | The project's model modules, their stubs, a manifest, a `connect()` |

Keeping the client apart from the builder means a user installs a small package (no FastAPI, no git server, no
Memgraph driver), and a project that does not want to publish an SDK installs nothing of the second.

```
 user's machine                                       server
┌────────────────────────────┐                ┌──────────────────────────┐
│ script / notebook          │                │ pangloss_sdk_server      │
│   from demo_app.models     │  git / wheel   │   builds the SDK from    │
│     import Person          │◄───────────────│   the project's models   │
│   await Person.get(id)     │                │                          │
│        │                   │                │ pangloss_api             │
│  <project>-sdk (models,    │  HTTPS + JWT   │   /api/Person/...        │
│    stubs) + pangloss-sdk   │───────────────►│        │                 │
│  (database module: httpx)  │                │  pangloss_memgraph       │
└────────────────────────────┘                └──────────────────────────┘
```

## Using it (the intended experience)

```bash
# once
pip install "git+https://pangloss.example.org/api/sdk/git"      # prompts for username and password
# later, to catch up with the models
pip install -U "git+https://pangloss.example.org/api/sdk/git"
```

```python
import demo_sdk                                   # the generated package: <project>_sdk
await demo_sdk.connect("https://pangloss.example.org")

from demo_app.models import Person                # the project's own modules, same import paths

p = await Person.get(person_id)                   # GET /api/Person/{id}   (needs no login)
p2 = await Person.Create(label="Ada", ...).save() # POST /api/Person       (login: prompts here, once)
page = await Person.list(search_terms="ada")      # GET /api/Person?q=ada
```

`connect()` imports the manifest's apps, runs `initialise()` with a client settings object (`DATABASE_MODULE =
"pangloss_sdk.databases.api"`), checks the SDK against the server (below), and returns. `PANGLOSS_URL` in the
environment can stand for the argument. A synchronous flavour is chosen in `connect(..., sync=True)` (below).

## What is in the generated SDK

A Python package, built to be installed as it is (`pyproject.toml` at the root, so `pip install .`, `uv add`,
`pip install git+...`):

```
demo-sdk/
├── pyproject.toml        name "pangloss-demo-sdk"; depends on pangloss-sdk==<server's version> and the
│                         third-party packages the models import
├── README.md             how to connect; what is in it; the fingerprint
├── demo_sdk/             the project's client entry point
│   ├── __init__.py       connect(), the manifest
│   └── manifest.json     project, apps, fingerprint, schema position, pangloss version, built at
├── demo_app/             each app that declares models, under its own import name
│   ├── __init__.py
│   ├── models.py         the declared classes, as the project wrote them
│   ├── models.pyi        the type stub (what `pangloss make-stubs` writes)
│   └── py.typed
└── ...
```

### Models under their own names

The SDK ships `demo_app.models`, not a renamed or rewritten copy, so code written for the server's modules imports
unchanged, `isinstance` and type checks work, and a stored `type` in the JSON names the same class. (The price:
the SDK and the project cannot be installed in one environment. That is not a use case.)

What is copied is the **import closure inside the project**: the modules of the selected apps that declare models,
and every module of the project those import, found by reading the source (`ast`), not by running it. Each app's
`__init__.py` is copied only if it is empty or only has imports of its own closure; otherwise the build refuses and
says which file (an `__init__.py` that connects to something should not run on a client).

### What is left out

- Settings, `.env`, migrations, the `populate` scripts, anything outside the closure.
- Apps that are not the project's: framework packages (`pangloss_*`) are dependencies, not copied.
- Apps listed in `SDK_EXCLUDE_APPS`; and, if `SDK_APPS` is set, everything not in it (default: every installed
  app that is not a framework package and declares models).

### Checked at build

An SDK that does not work on a clean client must not be published. The build:

1. Writes the package to a temporary directory.
2. Runs, in a subprocess with **no database settings and no `neo4j` connection**, `import demo_sdk;
   demo_sdk.connect_offline()`: imports every module, runs `initialise()`, and compares the generated model classes
   (their JSON schemas) with those of the server's. A difference is a build error.
3. Type-checks the stubs (`ty` is optional: skipped if not installed, with a note).
4. Only then moves it into place.

A failure says which module could not be imported and why (usually: a model module imports something server-only,
such as a database driver or a project helper that connects at import).

### Server-only code in models

A declared class may define `to_db`, `to_db_create`, `to_db_update`, validators, or helpers. These **run when
models are validated**, on the client as well as the server, if they are in the module. Rules:

- A hook that only computes from the data (a derived label) works on both, and runs twice (client, then server
  re-validates). That is harmless and expected: the server never trusts the client.
- Code that needs the database or server resources must not be at module level of a model module. A decorator,
  `pangloss_models.server_only`, marks a function or method that is left **out of the SDK** (its body replaced with
  a `raise PanglossServerOnly`), for the cases that cannot be moved. Spec'd here; built only if the demo needs it.

## The client: a database module that speaks HTTP

`pangloss_sdk.databases.api.exposed_functions` implements the same functions as `pangloss_memgraph` (the table in
[generated models](generated-models.md#the-initialisation-pipeline)). Each is one request:

| Function | Request | Result |
|---|---|---|
| `get_document(cls, id)`, `get_entity(cls, id)` | `GET /api/NAME/{id}` (an entity's URL is put in the path as it is) | `cls.HeadView` from the JSON. A 404 raises `PanglossNotFoundError` for a document; for an entity it returns `None`, as `get_entity` does now |
| `get_entity_for_edit(cls, id)` | `GET /api/NAME/{id}/edit` | `cls.EditView`; the `ETag` is kept as its version |
| `list_items(cls, search_terms, page_number, page_size, deep_search)` | `GET /api/NAME?q=&page=&page_size=&deep=` | `_ListItems` of `ReferenceView` |
| `create_head_node(self, detail)` | `POST /api/NAME`, body `self` (the **`Create`**, by alias, JSON mode), `?detail=` | `ReferenceView`, or `HeadView` with `detail` |
| `update_head_node(self, detail, expected_version)` | `PUT /api/NAME/{id}`, `If-Match: "<v>"` (or `*` if none is given... see below) | as above |
| `delete_*`, `undelete_*` | `DELETE /api/NAME/{id}`, `POST .../undelete` | `None` |

Points that need deciding or care:

- **Bodies are `Create` / `Update`, not `CreateDB`.** Ids, labels, semantic spaces and context labels are the
  server's to fill in. The client only has to produce a valid `Create`.
- **The API's `PUT` needs `If-Match`** (428 without it). A bare `.save()` on an `Update` has no `expected_version`.
  Decision: **an `Update` made from an `EditView` read through the SDK carries the version it was read at** (so
  `save()` is a checked update by default, and a concurrent edit gives `PanglossVersionConflictError`, with
  `current_version`). An `Update` built by hand without one sends `If-Match: *` **only** if the caller passes
  `expected_version="*"`; otherwise the SDK raises before sending (`PanglossVersionRequired`), so a blind overwrite
  is always chosen, never fallen into.
- **Errors map back to the exceptions the database module raises**, so the same `except` clauses work:

  | Status | Raised |
  |---|---|
  | 404 | `PanglossNotFoundError` |
  | 409 | `PanglossConflictError` (for a delete of a referred-to entity, with `referenced_by`); `PanglossNotDeletableError` where the body says so |
  | 412 | `PanglossVersionConflictError(current_version=...)` |
  | 422 | `pydantic.ValidationError`-like `PanglossReferenceError` for a bad reference; other 422 as `PanglossWriteError` carrying the server's detail |
  | 400 | `PanglossWriteError` |
  | 401 / 403 | `PanglossAuthenticationError` / `PanglossPermissionError` (new, in `pangloss_sdk`) |
  | 5xx, network | `PanglossServerError`, `PanglossConnectionError` (new). A network error on a **write** is never retried (the write may have happened); on a read it is retried twice with backoff |

  (The exact mapping has to be checked against `pangloss_api/errors.py` when this is built. A server error response
  has the exception name, so the client can use it rather than guess from the status.)
- **Async by default, sync on request.** The server functions are async; the models bind whatever is given. So
  `pangloss_sdk.databases.api` is async (`httpx.AsyncClient`) and `pangloss_sdk.databases.api_sync` has the same
  functions, blocking (`httpx.Client`), for scripts and notebooks that do not want an event loop. Which one is bound
  is the `DATABASE_MODULE` that `connect(sync=...)` puts in the settings. One mode per process: the bindings are on
  the classes.
- **Users acting for others.** The server records the logged-in user. The SDK has no way to say "as another user".
- **One client per process**, with a connection pool, closed at exit (and by `await demo_sdk.disconnect()`).
- **Iterating.** `Person.list` returns a page. A helper, `pangloss_sdk.iterate(Person.list, ...)` (an async
  generator, or a generator in sync mode), follows `next_page`. Small, but every data script wants it.
- **Concurrency.** Requests may be made concurrently (`asyncio.gather`); the client limits the number in flight
  (`max_connections`, default 10) so a loop of a thousand `save()` calls does not open a thousand connections.

### Settings on a client

`BaseSettings` is the server's (it needs a JWT secret and a database). Resolving the known problems:

- Add `pangloss_core.settings.ClientSettings`, with `DATABASE_MODULE` and `INSTALLED_APPS` only. `BaseSettings`
  extends it. `pangloss-models` is happy with that, as it reads nothing else.
- `pangloss_sdk` has its own `SdkSettings(ClientSettings)`: `URL`, `USERNAME`, `PASSWORD`/`TOKEN` (optional),
  `TIMEOUT`, `MAX_CONNECTIONS`, `VERIFY_TLS`, `CACHE_CREDENTIALS`. Environment variables use the prefix `PANGLOSS_`
  (`PANGLOSS_URL`, `PANGLOSS_USERNAME`, `PANGLOSS_PASSWORD`, `PANGLOSS_TOKEN`); a `.env` in the working directory is
  read, as for the server. The old `ApiAsDatabaseSettings` is removed (it was only a stub).

## Logging in

Reads need no login. The first **request that needs one** (a write, `get_entity_for_edit`) gets a 401 from the
server, or the client knows beforehand that the route needs login (it has the list). Then, in order:

1. A **token** that is already held: in memory, from `PANGLOSS_TOKEN`, or from the credential cache (below).
   On a 401 the **refresh token** gets a new access token (`POST /api/users/token/refresh`), once.
2. `PANGLOSS_USERNAME` and `PANGLOSS_PASSWORD`, or `username=` / `password=` to `connect()`: `POST /api/users/token`.
3. **If there is a terminal** (`sys.stdin.isatty()`, or a Jupyter kernel that can ask for input): **prompt**, with
   `getpass` for the password, once, saying which server and which user:
   ```
   Pangloss login for https://pangloss.example.org
   Username: ada
   Password:
   ```
   A wrong password asks again, three times.
4. **Otherwise** raise `PanglossAuthenticationRequired` ("no credentials: set PANGLOSS_USERNAME and
   PANGLOSS_PASSWORD, or PANGLOSS_TOKEN, or run `pangloss-sdk login`"). A script that runs unattended must fail,
   not hang at a prompt.

**Where credentials are kept** (the question was "a temp variable somewhere"). The recommendation:

| What | Where | Why |
|---|---|---|
| The **password** | **Never stored.** It is used for the token request and dropped | A stored password is the most valuable thing an attacker could take from a laptop |
| The **access token** | The process's memory only | Lasts 30 minutes |
| The **refresh token** (14 days) | By default the process's memory. Optionally, `pangloss-sdk login` saves it to the OS keyring (`keyring`, if installed) or, without one, to `~/.config/pangloss/credentials.json` with mode `0600`, keyed by server URL | So a second script, or a restarted kernel, does not ask again. Off by default for a library; `pangloss-sdk login` is the explicit act of saying "keep me logged in here". `pangloss-sdk logout` removes it, and revokes it if the server can (see below) |

Two extra points:

- **Revocation does not exist yet** ([API: not done yet](api.md#not-done-yet-)). A stolen refresh token lasts its
  14 days. Before the SDK keeps tokens on disk, the server should have *token revocation on logout* and *change of
  password ends sessions*, both already on the not-done list. This design **depends on that** for the stored
  refresh token; the in-memory flow does not.
- **Personal access tokens** (a new server feature, small): `POST /api/users/me/tokens` makes a long-lived,
  named, revocable, **read-only-or-read-write** token for scripts and for `git` (below). Listed and revoked at
  `GET/DELETE /api/users/me/tokens`. Stored hashed, as passwords are. This is better for unattended jobs than a
  password in an environment variable, and better for git than a password in a credential helper. Recommended as
  part of this work, but separable (phase 5).

## How the SDK is served

All under `/api/sdk` (a router of `pangloss_sdk_server`, found as any app's `api.py` is). It needs a login with the
level in `SDK_ACCESS`: `"admin"` (default), `"user"` (any logged-in user) or `"public"`. (What it reveals is the
shape of the data model, not data. A project that shares its data openly can make it public.)

| Endpoint | | |
|---|---|---|
| `GET /api/sdk` | | The manifest: project, fingerprint, schema position, pangloss version, build time, and the ways to get it, with URLs. Used by `connect()` to check for staleness |
| `GET /api/sdk/package.tar.gz`, `/package.whl` | | The SDK as an sdist and a wheel. `pip install https://.../package.whl` works, with credentials in the URL or `~/.netrc` |
| `GET /api/sdk/git/...` | | A **read-only git repository** (smart HTTP): `git clone`, `git fetch`, `git pull`, and what `pip install git+...` uses |

### `git clone`

Yes, this is possible, and worth doing, because it makes "keep in sync" a standard action (`git pull`; `pip
install -U`), and the **history of the models comes for free**: each rebuild is a commit, so `git log -p` is the
history of the schema, as the server saw it, with who built it and when.

Mechanism:

- A **bare git repository** under the project's `.pangloss/sdk.git`, which the builder writes with
  [dulwich](https://www.dulwich.io) (pure Python; no `git` binary needed on the server).
- On a build, the package tree is written as one commit on `main` **only if its content changed** (the
  fingerprint is the hash of the tree). The commit message says the schema position, the fingerprint and the
  pangloss version; the commit is tagged `schema-<position>` where the project has migrations, so a client can pin
  to the SDK for a given schema. Author and date are the build's (fixed `Pangloss <sdk@project>`), so two builds
  of the same models give the same commit.
- The router speaks the **smart HTTP protocol** for **upload-pack only** (clone, fetch). `dulwich.web` implements
  it as a WSGI application, mounted with Starlette's `WSGIMiddleware`; the handlers are limited to `upload-pack`, so
  **push is not possible** (no `receive-pack`). The repository is also never changed by a request.
- **Authentication** is HTTP Basic, as git does it. The username is the Pangloss username and the password is the
  user's **password or a personal access token**. (Git asks the terminal for these, and a credential helper keeps
  them. So the "prompt for username and password" for git is git's own.) A bad one is a 401 with
  `WWW-Authenticate: Basic`. The check goes through the same `authenticate` and the `SDK_ACCESS` level.
- Cloning is **only of the generated SDK**. The project's own source is never in it.

So the three ways to get it, from simplest to most flexible:

```bash
pip install "git+https://pangloss.example.org/api/sdk/git"                # install
git clone https://pangloss.example.org/api/sdk/git demo-sdk               # keep a checkout
pip install https://pangloss.example.org/api/sdk/package.whl               # no git
```

(With `pip`, credentials in the URL end up in the shell history and in the pip log. Prefer a credential helper or
`~/.netrc`; `pangloss-sdk` prints this when a URL with a password is used.)

### When to build

- **`pangloss sdk build`**: builds now (and prints the fingerprint and what changed).
- **At server start** (`SDK_BUILD = "start"`, the default): builds, and commits only if the content differs.
  Cheap if nothing has changed (reads the sources of the closure and hashes them).
- **On the first request** if no build exists.
- **Not on every model reload** in `--reload` development; `pangloss sdk build` is the way, or `SDK_BUILD = "off"`.

The build uses the server's **already-initialised** models for the stubs and the check, so it describes what the
server really runs.

## Staying in step

The SDK's `manifest.json` has the **fingerprint** (a hash of the shipped files) and the **schema position** (as in
`pangloss_history`, `{app: last migration}`). The client sends them on every request:

- Headers `X-Pangloss-SDK: <fingerprint>`, and `X-Pangloss-Schema: <position hash>`.
- The server compares with its own and **adds a response header**, `X-Pangloss-SDK-Status: current | stale`, and,
  for the second kind of mismatch below, refuses.

| Situation | Behaviour |
|---|---|
| The client's SDK is the server's | Nothing |
| Different fingerprint, same schema (a docstring, a label) | Allowed. A **one-time warning** per process: "the SDK is out of date; `pip install -U ...`" |
| The server's schema has **moved on by a migration** the SDK does not have | A **warning at `connect()`** (it asks `GET /api/sdk`, which is cheap), and on **writes**, a **409 `PanglossSdkOutOfDate`** is the server's choice (setting `SDK_STALE_WRITES = "refuse"` (default) \| `"warn"`): a stale `Create` may lack a required field, or have an enum value that no longer exists, and would be rejected anyway, or worse, accepted wrongly. Reads are never refused |
| The server has **no SDK** built, or the client is of a different project | `connect()` raises `PanglossSdkMismatch` |

`pangloss-sdk status` (and `demo_sdk.status()`) says: connected to, logged in as, SDK fingerprint, server
fingerprint, whether stale.

## Commands

| Command | Where | |
|---|---|---|
| `pangloss sdk build [--force]` | server | Build and commit. Prints the fingerprint, whether it changed, the apps included, the files |
| `pangloss sdk status` | server | What is built, when, from which schema position, whether it differs from the models now |
| `pangloss sdk show` | server | Lists the files in the SDK; `--diff` shows the change since the last build |
| `pangloss-sdk login [URL]` | client | Logs in and (if the user says so) keeps the refresh token |
| `pangloss-sdk logout` | client | Forgets the stored token; revokes it when the server supports that |
| `pangloss-sdk status` | client | As above |
| `pangloss-sdk update` | client | Runs the right `pip`/`uv` command for how the SDK was installed (from `direct_url.json`) |

`pangloss-sdk` is a small `argparse` program (no typer, to keep the client light). `pangloss` is the existing CLI.

## Settings (server)

| Setting | Default | |
|---|---|---|
| `SDK_ACCESS` | `"admin"` | Who may get the SDK: `"admin"`, `"user"`, `"public"` |
| `SDK_BUILD` | `"start"` | `"start"`, `"off"` (only `pangloss sdk build`) |
| `SDK_APPS` | `None` | If set, only these apps |
| `SDK_EXCLUDE_APPS` | `[]` | Apps never shipped |
| `SDK_NAME` | `"<project>-sdk"` | The distribution name (import name `<project>_sdk`) |
| `SDK_STALE_WRITES` | `"refuse"` | `"refuse"` or `"warn"` |
| `SDK_REQUIREMENT` | `pangloss-sdk==<version>` | The requirement string put in the SDK's `pyproject.toml`: for a project that installs Pangloss from its own index or git URL |
| `SDK_EXTRA_REQUIREMENTS` | `[]` | Extra dependencies, if the import analysis cannot find them |

## Packaging prerequisites (work this design needs first)

These are the **known problems** above; none is large, and phase 0 does them. **Phase 0 is done**: the cycle is broken, `ClientSettings` exists, `pydantic-meta-kit` is vendored as
`pangloss_models.meta_kit`, and the models no longer know of `neo4j`: `pangloss_models.hooks.from_database` takes
converters, and `pangloss-memgraph` registers its datetime one when its database module is imported.
`pangloss-sdk`'s `test_clean_client.py` checks the dependency closure and a run with `neo4j` blocked.

1. **Break the cycle.** `pangloss-core` stops depending on `pangloss-sdk`. `pangloss-sdk` depends on `pangloss-core`
   and `pangloss-models` (declared). The dependency is then `sdk → models → core`.
2. **`ClientSettings`** in `pangloss-core`, as above.
3. **`neo4j` out of the models.** `convert_neo4j_datetimes` becomes a hook that is a no-op unless `neo4j` is
   importable (`importlib` check), or moves to `pangloss-memgraph` and is registered as a *pre-validator* by the
   database module (preferable: the models should not know the driver). The SDK's `HeadView` gets ISO strings from
   JSON, so needs nothing.
4. **`pydantic-meta-kit`** from a git URL cannot be a dependency of a published package. Either publish it to PyPI
   (it is the author's), or vendor it into `pangloss-models`. Until then the SDK is installed from a project's own
   index or with `SDK_REQUIREMENT` pointing at git URLs (so it works for now, privately).
5. **Python.** The packages need Python 3.14 (`uuid7`, template strings). The client has the same requirement, so
   the SDK's `requires-python` says so. (See the Python versions item of [TODO](../TODO.md).)

## Tests

- **Unit** (client, no network): `exposed_functions` against `httpx.MockTransport`: each function's request (path,
  method, body by alias, headers) and each status → exception; the `If-Match` rules; login order and the prompt
  (with a faked TTY); the `ETag`-carrying `EditView`.
- **Contract** (the important ones): start the real API (`pangloss-api` with Memgraph, as the memgraph package's
  tests do) in-process with `httpx.ASGITransport`, install the SDK client against it, and run **the same scenarios
  twice**: through the SDK, and through the Memgraph database module directly, asserting equal results. This is how
  "code is the same against the server's database" is held to.
- **Builder**: the import closure on a sample project (a module imported through another; a relative import; an
  `__init__` that is refused); the content hash is stable; the commit is made only on change; the build fails with a
  useful message when a module is server-only.
- **Git**: build, then `git clone` the served repository with the real `git` binary (skipped if absent) through the
  ASGI app run by `uvicorn` on a random port; a bad password is refused; `git push` is refused; a second build
  with no change leaves the head where it was; a changed model gives a new commit and `git pull` brings it.
- **Clean-client check**: in a fresh virtualenv (the build step 2 above, as a test), install the SDK with only
  `pangloss-sdk` and its dependencies, with `neo4j` absent, and run the import and the `Create`/`HeadView` round
  trip against a mock.
- **Staleness**: header handling for each row of the table above.

## Phases

0. **Prerequisites** (done): break the cycle, `ClientSettings`, `neo4j` out of the models, a decision on
   `pydantic-meta-kit`. (Each has its own tests; the clean-client check starts here.)
1. **The client**: `databases/api` and `api_sync` with the error mapping, `SdkSettings`, login (memory, environment
   variables, prompt), iterating helper. Tests: unit and the **contract tests** against the real API, using models
   copied by hand (the demo's), before any builder exists.
2. **The builder**: the import closure, the package, the manifest, the build-time check, `pangloss sdk build/status/show`,
   the stubs inside it. Tests: builder and clean-client check.
3. **Serving**: `/api/sdk` (manifest, tarball and wheel), `SDK_ACCESS`, staleness headers and the `connect()` check.
4. **Git**: dulwich repository, smart HTTP read-only, Basic auth, tags, `pangloss sdk` commit handling. Tests: the
   real-`git` round trip.
5. **Tokens**: the server's revocation and personal access tokens, and the client's `pangloss-sdk login/logout` with
   stored refresh token. (Separable: phases 1 to 4 work with passwords at the prompt and in memory.)
6. **The demo**: `pangloss-demo` builds its SDK; a notebook-style script outside the project clones it, installs it,
   and populates and reads the demo data through the API. Docs updated (`packages.md`, `status.md`, `api.md`,
   `settings.md`, `cli.md`, `overview.md`).

## Decisions to make

These are the points where I have a recommendation, but they change what is built:

1. **Models under their own import names, or a rewritten namespace** (`demo_sdk.models.Person`). Recommended: own
   names (above): code is portable between server and client, and nothing has to be rewritten. The cost is that the
   SDK cannot share an environment with the project, and an `__init__.py` with side effects is refused.
2. **Ship source (declared classes) or generate fresh Pydantic models from OpenAPI.** Recommended: ship the
   source. Only that gives `Person.get`, `.list`, `.save()` and the generated families (`Create`, `EditView`,
   ...), the same `initialise()`, and the same validation, which is what the SDK is for. A generated-from-OpenAPI
   client would be a different product (and the right one for other languages).
3. **Where the builder lives.** Recommended: a new optional package `pangloss-sdk-server`, so the client stays
   small and a project opts in. The alternative is to put it in `pangloss-api`, which makes FastAPI-side code
   available with no extra step but puts dulwich in every deployment.
4. **Git (dulwich, pure Python) or `git http-backend`.** Recommended: dulwich, no `git` on the server; an
   `http-backend` subprocess is an option behind a setting if dulwich's smart HTTP proves too slow for a large SDK
   (it will not: the SDK is a few files).
5. **Default access.** Recommended: `"admin"`, as the question assumed. A research project that wants every
   collaborator to use the SDK sets `"user"`.
6. **Stale writes refused by default.** Recommended yes (a stale `Create` fails server-side anyway, or is
   accepted wrongly); the setting allows a warning instead.
7. **Credential storage.** Recommended: password never stored; refresh token only on explicit `pangloss-sdk login`,
   and only once the server can revoke it (phase 5). Until then, memory only, plus environment variables.
8. **Sync and async.** Recommended: both modules, chosen at `connect()`; async is the default because it is what
   the models' functions are, and what the server uses.

## Not done, and not planned here ⏳

- Server-push of changes ("the models changed") to connected clients.
- Per-user SDKs, or SDKs that only include some models (`SDK_APPS` is by app, not by class).
- Publishing to PyPI (a project can put the wheel on its own index; the builder only produces files).
- Access to history through the SDK (`pangloss-history`'s `/history` routes): the same pattern would carry it
  (`Person.history(id)`), as another module of the client. Later.
- Realtime and bulk endpoints: `create_inline` is the batch-upload convenience today; a bulk route would be a
  server feature first.
