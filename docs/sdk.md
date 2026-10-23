# SDK: using a project's models against its API ⏳

**Status: built (phases 0 to 6; see the end).** What follows begins as the design, and each phase has an "As built" section. (The first line of the design said: nothing here exists yet except the stub `pangloss-sdk` package (settings, and an
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
| `get_document(cls, id)`, `get_entity(cls, id)` | `GET /api/NAME/{id}` (an entity's URL is put in the path as it is) | `cls.HeadView` from the JSON. A 404 returns `None`, for a document and an entity, as the Memgraph functions do |
| `get_entity_for_edit(cls, id)` | `GET /api/NAME/{id}/edit` | `cls.EditView`; the `ETag` is kept as its version |
| `list_items(cls, search_terms, page_number, page_size, deep_search)` | `GET /api/NAME?q=&page=&page_size=&deep=` | `_ListItems` of `ReferenceView` |
| `create_head_node(self, detail)` | `POST /api/NAME`, body `self` (the **`Create`**, by alias, JSON mode), `?detail=` | `ReferenceView`, or `HeadView` with `detail` |
| `update_head_node(self, detail, expected_version)` | `PUT /api/NAME/{id}`, `If-Match: "<v>"` (or `*` if none is given... see below) | as above |
| `delete_*`, `undelete_*` | `DELETE /api/NAME/{id}`, `POST .../undelete` | `None` |

Points that need deciding or care:

- **Bodies are `Create` / `Update`, not `CreateDB`.** Ids, labels, semantic spaces and context labels are the
  server's to fill in. The client only has to produce a valid `Create`.
- **The API's `PUT` needs `If-Match`** (428 without it). The SDK follows the database module: `expected_version=3`
  sends `If-Match: "3"`; without one, **`If-Match: *`**, an update whatever the version is, as `update_head_node`
  does with no `expected_version`. (The first design refused a bare update. That would make code written for the
  server's database module behave differently on the client, which is what the SDK must not do. A checked update is
  asked for the same way in both: `save(expected_version=edit.meta.version)`.)
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
| `GET /api/sdk/version` | anyone | Project, distribution, version, fingerprint, schema position and its hash: what a client compares itself with (it is not gated, so a user who is not an admin can check; it shows nothing but these) |
| `GET /api/sdk` | `SDK_ACCESS` | The manifest, the build time, and the download URLs |
| `GET /api/sdk/download/{file}` | `SDK_ACCESS` | The wheel (`shop_sdk-0.3-py3-none-any.whl`) and the sdist (`shop-sdk-0.3.tar.gz`). The file name is real, as `pip` wants one: the names are in the manifest |
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
| `pangloss-sdk update` | client | Runs the right `pip`/`uv` command for how the SDK was installed (from `direct_url.json`); built in phase 6 |

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
1. ✅ **The client**: `databases/api` and `api_sync` with the error mapping, `SdkSettings`, login (memory, environment
   variables, prompt), iterating helper. Tests: unit and the **contract tests** against the real API, using models
   copied by hand (the demo's), before any builder exists.
2. ✅ **The builder**: the import closure, the package, the manifest, the build-time check, `pangloss sdk build/status/show`,
   the stubs inside it. Tests: builder and clean-client check.
3. ✅ **Serving**: `/api/sdk` (manifest, tarball and wheel), `SDK_ACCESS`, staleness headers and the `connect()` check.
4. ✅ **Git**: dulwich repository, smart HTTP read-only, Basic auth, tags, `pangloss sdk` commit handling. Tests: the
   real-`git` round trip.
5. ✅ **Tokens**: the server's revocation and personal access tokens, and the client's `pangloss-sdk login/logout` with
   stored refresh token. (Separable: phases 1 to 4 work with passwords at the prompt and in memory.)
6. ✅ **The demo and the rest**: `pangloss-demo` builds its SDK; a notebook-style script outside the project clones it, installs it,
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
   and only once the server can revoke it (done: phase 5).
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


## As built: phase 1 (the client) ✅

`pangloss-sdk` is now the client. It depends on `pangloss-core`, `pangloss-models` and `httpx2` (the HTTP library the
rest of the project already uses), and on nothing of the server.

| Module | |
|---|---|
| `settings.py` | `SdkSettings(ClientSettings)`: `URL`, `USERNAME`, `PASSWORD`, `TOKEN`, `TIMEOUT` (30), `MAX_CONNECTIONS` (10), `VERIFY_TLS`, `READ_RETRIES` (2); environment prefix `PANGLOSS_`, `.env` read, other keys ignored |
| `protocol.py` | No input or output: each operation is a `Call` (method, path, params, body, headers, `needs_login`) and a function that turns the response into the result, or raises. The error table is here |
| `auth.py` | `Session`: the tokens, and where credentials come from (the settings, once; then the prompt, three tries; else `PanglossAuthenticationRequired`, or `PanglossAuthenticationError` if the settings' were refused). The prompt is `getpass` at a terminal or in a notebook (`ipykernel`); `connect(prompt=...)` replaces it |
| `client.py` | `AsyncClient` and `Client` (blocking), the same logic: log in before a request known to need it (writes, `get_for_edit`); on a 401 renew the token with the refresh token (once, if several requests were refused together: a lock), else log in again; a **read** with a dead token that cannot be renewed is sent again without one. A connection pool per event loop (so `asyncio.run` twice is fine). A read is tried again after a network error (2 times, backing off), a write **never** |
| `databases/api`, `databases/api_sync` | The `exposed_functions` of the table above, async and blocking; `setup` as the stub had |
| `iterate.py` | `iterate` (async generator) and `iterate_sync`, following `next_page` |
| `__init__.py` | `connect(url, apps=, sync=, transport=, prompt=, **settings)`: makes the settings (or reads the environment), the client, imports `<app>.models` for each app, `initialise()`s. `disconnect()` and `disconnect_sync()` |
| `exceptions.py` | `PanglossSdkError` and `PanglossConnectionError`, `PanglossServerError`, `PanglossAuthenticationError` (and `...Required`), `PanglossPermissionError`, `PanglossRequestError` (400 or 422 that is not a write's error: usually an SDK out of date), `PanglossNotConnected` |

**A server change.** Every error answer of the API now has `error`, the name of the exception class, next to `detail`
(`{"detail": "...", "error": "PanglossNotFoundError"}`), so the client raises the same class rather than guessing from
the status. Without `error` (an older server, a proxy) the status decides: 404, 409, 412 and 503 as in the table,
403 `PanglossPermissionError`, 5xx `PanglossServerError`.

**Differences from the spec above:**

- `ApiAsDatabaseSettings` and the stub user functions are gone.
- A password is never kept on the session; the token is held in memory only. Nothing is written to disk (phase 5).
- The password at a prompt is not asked for again after a *success*; a later re-login (the refresh token ran out) uses
  the settings' credentials again, or asks again.

**Tests.** `pangloss-sdk/tests` (50): each operation's request and result, the error table, the login order and the
prompt, renewing once, retries, the blocking client, `connect`, `iterate`, and the clean-client checks, all against a
fake server (`httpx2.MockTransport`). `pangloss-memgraph/tests/test_sdk_contract.py` is the **contract test**: the
client's functions are called by hand, over an in-process connection to the real app with the data in Memgraph (the
models stay bound to Memgraph), and for **every kind of model of the kitchen sink** (four samples each) what is
created through the API reads, through the API, **exactly as the database module reads it directly**, in the normal
view and in the edit view, and an edit saved through the API changes nothing; a second test covers lists, versions
(`PanglossVersionConflictError` with its `current_version`, as raised directly), not found, a bad reference, an
entity in use (with `referenced_by`), and delete and undelete.


## As built: phase 2 (the builder) ✅

The package `pangloss-sdk-server` (`pangloss_sdk_server`), an optional app (`cli.py`, no routes yet).

| Module | |
|---|---|
| `closure.py` | Which files ship: starting from `<app>.models` of each shipped app, every module **of the project** (a file under the project root, not in a virtual environment) that is imported, anywhere in the file (inside functions and `if TYPE_CHECKING` too), found with `ast`, never by running it; and the `__init__.py` of every package above. A package's `__init__.py` may hold only a docstring, imports and `__all__`. A module that imports what a client does not have (`SERVER_ONLY`: `neo4j`, FastAPI, `pangloss_api`, `pangloss_memgraph`, `pangloss_users`, `pangloss_history`, ...) is a build error naming the module |
| `builder.py` | `build_package(root, settings, build_number)`: the files in memory: the modules as written, `.pyi` for each that declares models (`typestubs.stub_for_module`, from the server's initialised models), `py.typed`, `<project>_sdk/__init__.py` (`connect()`, `connect_offline()`, `MANIFEST`, `APPS`), `manifest.json`, `pyproject.toml` (hatchling; `requires-python` is the Python it was built with), `README.md`. Requirements: `SDK_REQUIREMENT` (default `pangloss-sdk==<this version>`), the distribution of each third-party import (from `importlib.metadata.packages_distributions`; an import with no known distribution is an error), and `SDK_EXTRA_REQUIREMENTS` |
| `check.py` | The build-time check: a subprocess (`python -I -B`) puts the package first on the path, **forbids the server-only modules**, imports it, `connect_offline()`s, and prints the JSON schema of the `Create`, `Update`, `HeadView`, `EditView`, `ReferenceView` and `ReferenceSet` of every Document and Entity; they must equal the server's (`pangloss_sdk.schemas`). The order of the members of a union and of `required` is normalised: it differs from one process to the next |
| `publish.py` | `build`: the fingerprint is the hash of the shipped files (and the requirements, apps and name), not of the manifest or the version, so it changes only with the content. Unchanged: nothing is done (`--force` builds again). Changed: the version is `0.<n>` (n counts builds that changed something), the package is written to `.pangloss/sdk/.building`, **checked**, and only then replaces `.pangloss/sdk/package`; a failure leaves the last build. `state.json` has the fingerprint, number, time and schema position |
| `cli.py` | `pangloss sdk build [--force]`, `status` (exit 2 if the models changed since), `show [--diff]` |

Settings (all optional, on the project's settings class): `SDK_APPS`, `SDK_EXCLUDE_APPS`, `SDK_NAME`, `SDK_REQUIREMENT`, `SDK_EXTRA_REQUIREMENTS`, `SDK_OUTPUT` (default `.pangloss/sdk`). Framework packages (`pangloss_*`) are never shipped.

**Run against the demo project.** `pangloss sdk build` gives `pangloss-demo-sdk` with `demo_app` (models and stub). The package was installed with `uv pip` into a **new Python 3.15 environment with only** `pangloss-core`, `pangloss-models` and `pangloss-sdk` (and their dependencies: no `neo4j`, no FastAPI), where `import pangloss_demo_sdk; connect(...)` initialised the models and `Person.get(...)` made a request and validated the answer.

**Found on the way** (also in `TODO.md`):

- The members of a union in the generated models differ between processes (they come from sets). It made the JSON schemas and the `.pyi` files differ from run to run, so the stub writer (`make-stubs` too: the demo's committed stub was reordered) and the schema comparison now use a fixed order. The models themselves are not changed.
- `pangloss-models` uses `lazy from ... import`, which is **Python 3.15** syntax, though `requires-python` says 3.14: so a client needs 3.15, and the generated `requires-python` says the Python it was built with.

**Not built** (from the spec): type-checking the stubs of the package (`ty`), `SDK_BUILD = "start"` (building at server start: phase 3), the `@server_only` decorator, a test that installs the built package into a fresh virtual environment (done by hand above; it needs network access for the build backend).

**Tests** (`pangloss-sdk-server/tests`, 26): the closure (relative imports, imports in functions, `__init__` rules, server-only imports, a virtual environment inside the project), the package (files, manifest, stable fingerprint, requirements, app selection), and publishing (unchanged builds, new versions, a package that fails to import on a client leaves the last build, models that differ fail the check, the diff, the commands).


## As built: phase 3 (serving) ✅

**`pangloss-api`** gained two things for apps: `configure_app(app, settings)` in an app's `api.py` (to add middleware, and to add to `app.state.startup_hooks`, which the lifespan runs after the migration check), and `sdk` as a reserved model name.

**`pangloss_sdk_server`**:

| Module | |
|---|---|
| `api.py` | The routes above, and `configure_app`, which adds the version middleware and a start-up hook that builds. `/api/sdk/version` is 503 (with the reason) if nothing is built or the build failed: the server still starts |
| `access.py` | `SDK_ACCESS` (`"admin"` default, `"user"`, `"public"`). A login is `Authorization: Bearer`, the session cookie, or **HTTP Basic**, which is what `pip` and `git` send: the username and a password, **or an access token as the password**. With nothing, the answer is `401` with `WWW-Authenticate: Basic`, so `pip` and a browser ask |
| `current.py` | What is served: set by a build at start (`SDK_BUILD = "start"`, which only builds if the content changed, in a thread), else the last build on disk, else (unless `SDK_BUILD = "off"`) a build on the first request. The project directory is `SDK_ROOT`, or the nearest directory up from the working directory with `[tool.pangloss]` |
| `archives.py` | A **wheel** and an **sdist** made in memory, the same bytes for the same content (no times; sorted). The wheel is written here, not by a build backend, so installing it needs nothing but its dependencies (`RECORD` has the hash and size of every file); the sdist has `pyproject.toml` and `PKG-INFO` |
| `version_check.py` | Middleware for `/api/...`: reads `X-Pangloss-SDK` (the client package's fingerprint) and `X-Pangloss-Schema` (a hash of its migration position), and answers with `X-Pangloss-SDK-Status`: `current`, `stale` (another package, the same schema: allowed) or `schema-changed`. With `SDK_STALE_WRITES = "refuse"` (default) a **write** from a `schema-changed` client is answered with **409** `PanglossSdkOutOfDate` before any route; `"warn"` lets it through. Reads, logins (`/api/users`) and the SDK routes are never refused. A request without the headers is not touched |

**The client** (`pangloss-sdk`) sends the two headers when it was given the manifest (`connect(..., sdk=MANIFEST)`, which the generated `connect()` does), warns **once** (`PanglossSdkOutOfDateWarning`) when the status is not `current`, raises `PanglossSdkOutOfDate` for the 409, and has `check()` / `check_sync()` (`GET /api/sdk/version`, set against its manifest: raises `PanglossSdkMismatch` for another project or no SDK, warns if it is out of date; returns `current`, `same_schema`, the server's and its own details). The generated module has `check`, `check_sync`, `connect`, `connect_offline`.

**Differences from the spec above:** the downloads are `/api/sdk/download/<real file name>` (not `package.whl`); `/api/sdk/version` is open and `/api/sdk` is gated (the spec had one gated endpoint, which would stop a non-admin from checking); the server's current schema is that of the build it serves (made as it started), not recomputed per request. Not built: `status()` on the generated module (`check()` returns the same). (A PEP 503 index and personal access tokens came later: phases 5 and 6.)

**Run against the demo project, with the real server and Memgraph** (a temporary admin user, since removed): the server built `pangloss-demo-sdk` as it started; `/api/sdk` was 401 without a login and 200 with one; the wheel was installed with `uv pip install "http://user:password@127.0.0.1:8765/api/sdk/download/pangloss_demo_sdk-0.4-py3-none-any.whl"` into a **new environment with only `pangloss-core`, `pangloss-models` and `pangloss-sdk`**; and a script there connected (`check()` said current, with warnings turned into errors), created a `Person` (with detail), listed, read it for edit, updated it with `expected_version`, got `PanglossVersionConflictError` (`current_version` 2) for a stale update, deleted it, and read `None`. The test data was removed.

**Tests** (`pangloss-sdk-server`, now 41; `pangloss-sdk`, now 58): building as the server starts, building off, a failing build that leaves the server up; access (admin, user, public, Basic, token as password, 401 challenge); the manifest; the wheel (a valid zip, `RECORD` hashes right, **imports on a clean client and makes the server's models**) and the sdist; the same bytes twice; the status header for each case; the refusal of a stale write, and `warn`; a client with the real manifest is `current` against the app; and, in the client, the headers, the warning once, the 409, and `check()`.


## As built: phase 4 (git) ✅

`git clone http://host/api/sdk/git` works, with the real `git` (and `pip install "git+http://user:password@host/api/sdk/git"` into a clean environment, which builds the package with its `pyproject.toml`).

| Module | |
|---|---|
| `gitrepo.py` | A **bare repository** `.pangloss/sdk/sdk.git`, written with dulwich (no `git` on the server). `commit_package` puts the package's files in a tree and commits it on `main` **only if the tree differs** from the last commit's (so a build with no change, and `--force` of the same content, leave the head where it was). The message has the distribution and version, the fingerprint and the schema position; the commit is tagged `v<version>`, and `schema-<hash>` if no commit has that tag yet (the first SDK at a schema). Called by `publish.build` after a build, and also for an unchanged one (a repository made after the build, or lost); a failure is logged and does not fail the build |
| `git_endpoint.py` | An ASGI app mounted at `/api/sdk/git` (by `configure_app`): the **same access** as the rest of the SDK (`authorise`: Basic, Bearer or cookie; 401 with `WWW-Authenticate: Basic` so that git asks for a username and password, and a credential helper keeps them), then dulwich's smart HTTP application, behind `a2wsgi`, with **upload-pack only**. dulwich *adds* the handlers given to its defaults, which have `receive-pack`: the first test of a push **succeeded**, so the handler is taken out, and a push (`git-receive-pack` in the path, or `service=git-receive-pack`) is also answered `403` before dulwich |

`access.py` now has `authorise(request)` (a plain function: git's endpoint is not a FastAPI route) and the Basic password can be a personal access token.

Differences from the spec above: the **commit time is the build's**, not fixed (the history says when each version was made; a repository made again from nothing would have other ids either way); the schema tag is on the first commit at a schema only (a tag that moves would not reach clients that fetched it).

**Tests** (`test_git.py`, 8, skipped without `git`): a real uvicorn server on a free port; clone (files, no unrelated modules, the log, branch, tags); refused for a wrong password, an unknown user and an ordinary user; a personal access token as the password; **a push is refused and changes nothing**; a changed model is a new commit that `git pull` brings; an unchanged build leaves the head; `SDK_ACCESS = "public"` needs no login.

## As built: phase 5 (tokens and the kept login) ✅

**Server** (see [the API](api.md#sessions-ending-and-personal-access-tokens)): tokens have an id and the user's `token_generation`; logout (`POST /api/users/token/revoke`, `DELETE /session`) revokes; a password change and `POST /me/logout-all` end every session; **personal access tokens** (`pgl_...`, hashed, named, optionally expiring, scope `read` or `write`) at `/api/users/me/tokens`, usable as a Bearer token or the Basic password, and so for `pip` and `git`. This is what made it safe to let the client keep a refresh token. Memgraph and the API tests' in-memory backend both implement the six new storage functions.

**Client** (`pangloss-sdk`):

| | |
|---|---|
| `credentials.py` | What `pangloss-sdk login` keeps, for one server URL: **a refresh token, never the password** (or a personal access token). In the OS **keyring** if `keyring` is installed (`pip install pangloss-sdk[keyring]`) and has a backend, else a **file** `~/.config/pangloss/credentials.json` (`PANGLOSS_CREDENTIALS_FILE` for another) of mode `600` in a directory of `700`; a file others can read is **not used** (a warning) |
| `Session` | With no `TOKEN`, no `USERNAME` and `PASSWORD` in the settings, and `USE_STORED_LOGIN` (default true), the kept login is used: a refresh token gets an access token **before** any password is asked for (`_refresh` first, then `_login`); a personal access token is used as it is. Settings credentials win over the kept login. A kept refresh token that is no good falls back to the settings or the prompt. Nothing is ever written by a running program: only `login` writes |
| `pangloss-sdk` (`cli.py`, `python -m pangloss_sdk`; `argparse`, so the client stays light) | `login [URL] [--username] [--token]` (prompts; three tries; `--token` checks a personal access token with `GET /api/users/me` and keeps it), `logout [URL]` (revokes the refresh token on the server, then forgets it; says so if the server could not be reached), `status [URL]` (the kept login and whether it is still good, the SDK on the server). The URL can be `PANGLOSS_URL` |

**Not built then, built in phase 6** (below): `pangloss-sdk update`, `pangloss users tokens ...`, `last_used` on a token, indexes, and limiting login attempts.

**Run against the demo, with the real server and Memgraph** (a temporary admin user, since removed): `pangloss-sdk login` kept a refresh token in a file of mode `600`; a script with **no credentials** connected, created a `Person` with the kept login (no prompt) and made a **read-only personal access token**; with that token it read, and a delete raised `PanglossPermissionError` ("This token can only read"); `logout` revoked the refresh token (200 before, **401 after**) and emptied the file; a password change ended the session of the token used to make it (200, then 401). `git clone` of the real server worked, a wrong password and a push were refused, and `pip install "git+http://..."` installed the SDK into a new environment with no `neo4j`.

**Tests**: `pangloss-api` `test_revocation_and_access_tokens.py` (13: revoke, cookies, logout everywhere, a password change by the user and by an admin, personal tokens: shown once, scope, revoked, expired, disabled, owner, not made with a token), `pangloss-memgraph` `test_users.py` (+4, in Memgraph), `pangloss-sdk` `test_stored_login.py` (19: the store, the keyring, using it, the command).


## As built: phase 6 (what was left, and the demo) ✅

**What was left over from phases 3 to 5, now built:**

| | |
|---|---|
| `pangloss-sdk update [PACKAGE] [--dry-run]` (`pangloss_sdk/update.py`) | Finds the installed SDK (a distribution that needs `pangloss-sdk`) and runs the command that matches how it was installed (`direct_url.json`): **from the server's wheel**, it asks `/api/sdk/version`, says so if the version is the same, else gets the manifest (with the kept login, a refresh token turned into an access token for the Basic password, or a prompt) and installs the new wheel; **from git**, the install again from the repository (a pinned revision stays pinned, and says so); **from an index**, an upgrade by name; **from a directory**, nothing (it says to update the directory). `uv pip` if `uv` is there, else `pip`. What is printed has the password hidden; the real command has it in the URL for as long as it runs (so use a personal access token, or the short-lived access token a refresh gives). It refuses an SDK of another name on the server |
| `pangloss users tokens create|list|revoke USERNAME` | Personal access tokens from the command line, for the user the command names (it is the administrator's tool, as the rest of `pangloss users`). `create` prints the token once |
| `last_used_when` on a token | Set when the token is used, **at most once in 10 minutes** (`LAST_USED_RESOLUTION`), so a busy script does not write on every request. `touch_access_token_in_db(id, when)` is optional for a backend |
| Indexes | `PGAccessToken.token_hash` and `PGRevokedSession.jti` are **unique** (so indexed too), in `UNIQUE_CONSTRAINTS`. **This is a migration of `pangloss_memgraph`** (`0002_addindex_addindex_addconstraint`): an existing database needs `pangloss migrate` before the server starts (the migration check says so otherwise) |
| Login attempts (`pangloss_api/throttle.py`) | After `LOGIN_MAX_FAILURES` (10) wrong passwords for a username within `LOGIN_FAILURE_WINDOW_SECONDS` (300), that username gets **429** with `Retry-After`, even for the right password, until the oldest failure leaves the window; a right password clears the count; 0 turns it off. Applies to `/token`, `/session` and the Basic login for the SDK and git. **In memory, per server process**: several workers each count (the limit is that many times as high) and a restart forgets: it slows guessing, and is not a replacement for a proxy's limit. (A locked-out username can also be locked out by someone else: the usual price) |
| A package index (PEP 503) | `/api/sdk/simple/` and `/api/sdk/simple/<project>/` (`SDK_ACCESS`): the one project, with its wheel and sdist, `#sha256=` and `data-requires-python`. `uv pip install --extra-index-url http://user:password@host/api/sdk/simple/ pangloss-demo-sdk` works (tried against the demo with `uv`); the credentials in the URL are not kept in the installed package's metadata |

Still **not built**: type-checking the built stubs with `ty` (a build-time dependency we do not want), the `@server_only` decorator (nothing needed it), a test that installs into a fresh environment from the network, `status()` on the generated module, and the union-member order at its source (the models' unions come from sets; the schemas and the stubs are written in a fixed order, so nothing in the SDK depends on it). The Python 3.15 requirement is as before.

**The demo** is `sdk-demo/` (in the root of the repository, outside `pangloss-demo`): `sdk_demo.py`, a script in `# %%` cells (an editor or Jupytext opens it as a notebook), and `run.sh`, which makes a **new environment with only `pangloss-core`, `pangloss-models` and `pangloss-sdk`**, **`git clone`s the SDK from the server** (git is given the username and password by an `GIT_ASKPASS` helper, so they are neither in the URL nor in the process list, and `credential.helper=` is turned off so that a stale one in the keychain is not used), installs the clone, lists what is installed (no `neo4j`, no FastAPI), and runs the script. The script connects, checks the SDK against the server, lists people (no login), then **creates** a person, a place and a source, **a factoid** that refers to them with a statement in it, reads back, **updates** with `expected_version` and gets `PanglossVersionConflictError` for the stale one, goes through the list with `iterate`, and removes what it made (a delete only marks: the data is removed with Cypher if it is to be as it was; `--keep` leaves it).

Run against the real demo server and Memgraph: it did all of that. The clone had two commits and the tags; the environment had `pangloss-demo-sdk 0.4` and no database or web packages; `pangloss-sdk update --dry-run` said it was the latest.

**Tests** this phase: `pangloss-sdk` `test_update.py` (17), `pangloss-api` (+5: last used, the three of the throttle), `pangloss-cli` (+2: tokens), `pangloss-sdk-server` (+1: the index), `pangloss-memgraph` (last used and the migrations).
