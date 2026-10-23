# Packages

This is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/); each directory under `packages/` is a separate distributable package. Python 3.14 or newer is required.

```
pangloss-memgraph ──► pangloss-models ──► pangloss-core
        └──► pangloss-users ──► pangloss-core

pangloss-sdk ──► pangloss-models, pangloss-core

pangloss-cli ──► pangloss-core, pangloss-models, pangloss-users
pangloss-api ──► pangloss-core, pangloss-models, pangloss-users
```

Arrows show declared dependencies. (`pangloss-models` uses `pangloss-sdk` only in its tests, as a database module that needs no connection: a dev dependency.) A client of the API needs only the SDK's side of this: it needs no `neo4j`, FastAPI or Memgraph package.

## pangloss-core ✅ / 🚧

Settings shared by every module: `DatabaseSettings`, `ClientSettings` (only `INSTALLED_APPS` and `DATABASE_MODULE`, which is all the models read; what a client of the API uses) and the generic `BaseSettings[TDatabaseSettings]` (the server's, which extends it). Constructing a `BaseSettings` stores it in the module global `pangloss_core.settings.SETTINGS`. See [Settings](settings.md).

The package `__init__` only contains a placeholder `hello()`.

## pangloss-models ✅ (the main package)

Everything about *declaring* and *initialising* models:

| Path | Purpose |
|------|---------|
| `model_bases/` | The declarable base classes (`Document`, `Entity`, `Embedded`, `Trait`, ...) and the generated-model base classes in `base_models.py` (Create / Update / the `...DB` models / the views), with what they use in `labels.py`, `fulfilment.py`, `binding.py`, `instance_context.py`, `from_database.py` and `model_tools.py` |
| `field_definitions.py` | Dataclasses describing each field after analysis (`LiteralFieldDefinition`, `RelationFieldDefinition`, `FieldBinding`, ...) |
| `initialise_models/` | Field-definition and incoming-relation analysis, and the builder of the generated models (`kinds.py` describes `Create`, `CreateDB`, `Update`, `UpdateDB` and `View`; `builder.py` makes them); see [the pipeline](generated-models.md#the-initialisation-pipeline) |
| `model_registry.py` | `ModelRegistry`: registration, dependency ordering, and the `finalise()` entry point |
| `utils.py` | Type-introspection helpers (parent classes, traits, concrete subclasses, relation detection) |
| `exceptions.py` | `PanglossInitialisationError`, `PanglossModelError`, `PanglossMetaError`, `PanglossImportError`, ... |

Public entry point: `pangloss_models.initialise`, an alias for `ModelRegistry.finalise`.

It contains `pangloss_models.meta_kit`, the `WithMeta[...]` / `BaseMeta` machinery behind `_meta` and `Meta(...)`, vendored from [pydantic-meta-kit](https://github.com/richardhadden/pydantic-meta-kit) (commit `6f8ea9c`; changes are made in `pangloss-models` now). It knows nothing of any database: what a database returns that the models cannot read (Memgraph's date types) is converted by a function the database module adds to `pangloss_models.hooks.from_database`.

## pangloss-memgraph ✅ / 🚧

A database backend for [Memgraph](https://memgraph.com/) (using the `neo4j` async driver). It supplies the `exposed_functions` module that `ModelRegistry` binds to `Document.get`, `Document.list`, `Entity.list` and `.save()`. See [Memgraph backend](memgraph.md).

`cli.py` adds `pangloss memgraph <command>`; `databases/memgraph/setup.py` is what the core `pangloss setup-database` calls. `indexes.py` and `tooling/__init__.py` are empty placeholders.

## pangloss-cli ✅

The `pangloss` command (`pangloss_cli.main`), built with [Typer](https://typer.tiangolo.com/). It finds the project's settings, adds the commands of installed apps, and has the core commands `new-project`, `new-app`, `run`, `dev`, `setup-database` and `users ...`. The templates for new projects and apps are in `pangloss_cli/templates`. It knows nothing about a particular database: it uses the `setup` module of `DATABASE_MODULE`. See [Command line](cli.md).

## pangloss-api 🚧

The FastAPI application (`pangloss_api.app.create_app`). Done: token and session login (JWT with PyJWT), the user endpoints, and CRUD routes for every Document and Entity. Not done: routes from installed apps, and finer permissions. See [REST API](api.md).

## pangloss-interface 🚧 (scaffolding)

A Python package that holds the JavaScript of the web interface: `interface-core` (a Solid 2.0 component library) and `interface-app` (a server-rendered Solid 2.0 application), with `pangloss interface` commands that wrap Node or Bun and endpoints under `/api/interface`. See [The interface](interface.md).

## pangloss-sdk-server 🚧

Optional: `"pangloss_sdk_server"` in `INSTALLED_APPS`. Builds the SDK of the project: `pangloss sdk build|status|show`. It also serves it: `/api/sdk` (manifest, wheel, sdist; `SDK_ACCESS`) and tells a client whether its SDK is current; git is not built yet. See [the SDK](sdk.md).

## pangloss-sdk 🚧

Lets Pangloss models be used locally and read and write a remote Pangloss instance through its API ("API as database"). The client is built; the generated per-project SDK is not (see [the SDK](sdk.md)).

- `databases/api` (async) and `databases/api_sync` (blocking) are database modules whose functions are requests: set `DATABASE_MODULE` to one, or call `pangloss_sdk.connect(url, apps=[...])`.
- `SdkSettings`, login (settings, prompt, tokens kept in memory), the errors the server's database module raises, and `iterate`.
- The model tests use `databases/api` as a database module because it needs no live connection.

## pangloss-users 🚧

Users and their passwords. See [Users](users.md).

- `current_request_username`: a `ContextVar` (default `"pangloss_default_user"`) naming the acting user. The Memgraph backend uses it to record who created, updated or deleted a node, and refuses writes by a user who does not exist or is disabled.
- `models.py`: `User` (what can be shown: no password or hash), `UserCreate`, `UserUpdate` and `UserInDB` (with `hashed_password`).
- `passwords.py`: Argon2id hashing and checking.
- `service.py`: `create_user`, `get_user`, `get_user_by_email`, `list_users`, `authenticate`, `update_user`, `set_password`, `change_password`, `set_admin` and `set_disabled`. They call the database backend's `exposed_functions`.

Tokens, sessions and the user routes are in [`pangloss-api`](#pangloss-api-🚧), not here; permissions are not written yet ⏳.
