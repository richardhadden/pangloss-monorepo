# Packages

This is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/); each directory under `packages/` is a separate distributable package. Python 3.14 or newer is required.

```
pangloss-memgraph ──► pangloss-models ──► pangloss-core ──► pangloss-sdk
        │──────────────────────────────────────────────────────►│
        └──► pangloss-users
```

Arrows show declared dependencies. The SDK's code also imports `pangloss_core` and `pangloss_models`, which `pangloss-sdk/pyproject.toml` does not declare (a cycle with `pangloss-core`'s declared dependency on the SDK).

## pangloss-core ✅ / 🚧

Settings shared by every module: `DatabaseSettings` and the generic `BaseSettings[TDatabaseSettings]`. Constructing a `BaseSettings` stores it in the module global `pangloss_core.settings.SETTINGS`. See [Settings](settings.md).

The package `__init__` only contains a placeholder `hello()`.

## pangloss-models ✅ (the main package)

Everything about *declaring* and *initialising* models:

| Path | Purpose |
|------|---------|
| `model_bases/` | The declarable base classes (`Document`, `Entity`, `Embedded`, `Trait`, ...) and the generated-model base classes in `base_models.py` |
| `field_definitions.py` | Dataclasses describing each field after analysis (`LiteralFieldDefinition`, `RelationFieldDefinition`, `FieldBinding`, ...) |
| `initialise_models/` | One module per generated model kind, plus field-definition and incoming-relation analysis |
| `model_registry.py` | `ModelRegistry`: registration, dependency ordering, and the `finalise()` entry point |
| `utils.py` | Type-introspection helpers (parent classes, traits, concrete subclasses, relation detection) |
| `exceptions.py` | `PanglossInitialisationError`, `PanglossModelError`, `PanglossMetaError`, `PanglossImportError`, ... |

Public entry point: `pangloss_models.initialise`, an alias for `ModelRegistry.finalise`.

It depends on [`pydantic-meta-kit`](https://github.com/richardhadden/pydantic-meta-kit) (a separate repository), which provides the `WithMeta[...]` / `BaseMeta` machinery behind `_meta` and `Meta(...)`.

## pangloss-memgraph ✅ / 🚧

A database backend for [Memgraph](https://memgraph.com/) (using the `neo4j` async driver). It supplies the `exposed_functions` module that `ModelRegistry` binds to `Document.get`, `Document.list`, `Entity.list` and `.save()`. See [Memgraph backend](memgraph.md).

`indexes.py` and `tooling/__init__.py` are empty placeholders.

## pangloss-sdk 🚧

Intended to let Pangloss models be used locally and read/write a remote Pangloss instance through its standard API ("API as database"). Currently:

- `ApiAsDatabaseSettings` (URL, username, password) exists.
- `databases/api/exposed_functions.py` is a **stub**: `get_document` returns a fabricated placeholder object, `create_head_node` and `list_items` do nothing.
- The model tests use it as a database module because it needs no live connection.

## pangloss-users 🚧

Only provides the `current_request_username` `ContextVar` (default `"pangloss_default_user"`). The Memgraph backend uses it to record who created a node. There is no user model, authentication or permissions code yet; `BaseSettings` requires `AUTHJWT_SECRET_KEY`, but nothing consumes it.
