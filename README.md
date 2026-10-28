<div align="center">

# Pangloss

**Prosopography and Network Graph Labyrinth Orientation System ☀︎**

Describe your research data as Python classes. Get validated models, a graph-database store and a REST API.

![Python 3.15+](https://img.shields.io/badge/python-3.15%2B-3776AB?logo=python&logoColor=white)
![Memgraph](https://img.shields.io/badge/graph-Memgraph-FB6E00)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)
![Pydantic v2](https://img.shields.io/badge/models-Pydantic%20v2-E92063)
![Status](https://img.shields.io/badge/status-in%20development-orange)

[Getting started](guide/getting-started/README.md) ·
[Reference docs](docs/README.md) ·
[Migrations guide](guide/migrations/README.md) ·
[Status and roadmap](docs/status.md)

</div>

---

Pangloss v3 is a modular rewrite of the original Pangloss. It is for projects that model people, sources, statements,
events and places, and the many ways they relate: the kind of data that fits a graph better than a table.

## What it does

You declare the model once:

```python
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity


class Person(Entity):
    pass


class Statement(Document):
    text: str
    was_carried_out_by: Person


initialise()
```

and Pangloss generates, for every class:

- **Pydantic models** for each job: `Statement.Create`, `Statement.Update`, `Statement.HeadView`, `Statement.EditView`, and the reference
  models used when something points at it.
- **Storage** in a graph database, written and read with single Cypher statements, with ids, labels, versions
  and the reverse edge of every relation handled for you.
- **A REST API**: CRUD routes for every document and entity, token and session login, personal access tokens, users and admins.

```python
statement = await Statement.Create(
    label="A statement",
    text="…",
    was_carried_out_by={"type": "Person", "id": some_uuid},
).save()

loaded = await Statement.get(statement.id)        # a Statement.HeadView
```

## Features

| | |
|---|---|
| 🧬 **Rich modelling** | Documents, entities, embedded objects, traits, reified relations, edge models, semantic spaces and context labels. [Defining models](docs/models.md) |
| 🕸️ **Graph storage** | Memgraph backend; relations are real edges, with a text index for search. [Memgraph backend](docs/memgraph.md) |
| 🌐 **REST API** | FastAPI app built from your models, with optimistic locking (`If-Match`) and CORS for a frontend. [REST API](docs/api.md) |
| 🔐 **Users and auth** | JWT tokens or cookie sessions, revocation, login throttling, long-lived personal access tokens. [Users](docs/users.md) |
| 🚚 **Migrations** | `makemigrations` / `migrate` for changes to the models, with a dry run, batches, snapshots and undo. [Migrations guide](guide/migrations/README.md) |
| 📦 **Generated SDK** | `pangloss sdk build` makes an installable, type-stubbed package of your models that talks to the API: the same `Person.get(...)` code, over HTTP. [The SDK](docs/sdk.md) |
| 🕰️ **History** | Every version of a document or entity recorded, with diffs and restore, even after the models have changed. [History](docs/history.md) |
| 🖥️ **Interface** | A Solid 2.0 web interface, with `pangloss interface` commands (scaffolding so far). [The interface](docs/interface.md) |
| 🔭 **Observability** | Structured, secret-safe logging with request ids, audit lines for logins and writes, and slow-query warnings. [Logging](docs/logging.md) |
| ⌨️ **A command line** | `pangloss new-project`, `run`, `dev`, `setup-database`, `users`, `make-stubs`, `check-data` and more. [Command line](docs/cli.md) |

## Quick start

You need **Python 3.15** (the models use lazy imports, PEP 810), [uv](https://docs.astral.sh/uv/) and a running
[Memgraph](https://memgraph.com/) (Docker is easiest).

```bash
git clone https://github.com/richardhadden/pangloss-monorepo
cd pangloss-monorepo
uv sync --all-packages

# a graph database to talk to
docker run -d --name pangloss-memgraph -p 7687:7687 memgraph/memgraph-mage:3.14.0

# a project with one app
mkdir my-project && cd my-project
source ../.venv/bin/activate
pangloss new-project my_project
pangloss new-app my_app          # edit my_app/models.py to declare your models

pangloss setup-database          # indexes, constraints, the text index
pangloss users create --admin
pangloss dev                     # the API on http://127.0.0.1:8000, reloading as you edit
```

The [getting started guide](guide/getting-started/README.md) goes through this step by step, and
[`pangloss-demo/`](docs/demo-setup.md) is a finished project (factoids about people, groups and places) you can run.

## Repository layout

This is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/); each directory under `packages/` is a
separate distributable package.

| Package | |
|---|---|
| [`pangloss-core`](packages/pangloss-core) | Settings and logging shared by every package |
| [`pangloss-models`](packages/pangloss-models) | The base classes, model initialisation, export, type stubs and the migration planner |
| [`pangloss-memgraph`](packages/pangloss-memgraph) | The Memgraph backend: query builders, database functions, migrations |
| [`pangloss-users`](packages/pangloss-users) | User models, passwords, access tokens |
| [`pangloss-api`](packages/pangloss-api) | The FastAPI application |
| [`pangloss-cli`](packages/pangloss-cli) | The `pangloss` command |
| [`pangloss-sdk`](packages/pangloss-sdk) · [`-sdk-server`](packages/pangloss-sdk-server) | The client of the API, and the builder and server of it |
| [`pangloss-history`](packages/pangloss-history) | Versions of everything written, and restoring them |
| [`pangloss-zotero`](packages/pangloss-zotero) | A Zotero library kept in the database, as sources and subjects of factoids |
| [`pangloss-interface`](packages/pangloss-interface) | The web interface (Solid 2.0) |

```
pangloss-memgraph ──► pangloss-models ──► pangloss-core
pangloss-api / pangloss-cli ──► pangloss-models, pangloss-users, pangloss-core
pangloss-sdk ──► pangloss-models, pangloss-core      (no database driver, no web framework)
```

Also here: [`pangloss-demo/`](pangloss-demo) (a project made with the installer), [`sdk-demo/`](sdk-demo) (a script using
the generated SDK), [`docs/`](docs/README.md) (the reference) and [`guide/`](guide/README.md) (tutorials).

## Development

```bash
uv sync --all-packages
./run_tests.sh                    # the whole suite, in parallel
uv run ty check                   # types
uvx ruff check . && uvx ruff format .
```

The Memgraph tests need Docker, or a Memgraph on `bolt://localhost:7687` (user and password `test`); the fixtures start a
container if there is none. **The tests empty that database**, so don't point them at one you care about.
See [Development](docs/development.md) for the test layout, coverage and conventions.

## Status

Pangloss is in active development and **not yet released**: nothing is published to PyPI, and the APIs may change.
The model layer, Memgraph backend, REST API, users, migrations, history and the SDK work and are tested; the
interface and some finer-grained permissions are still to come. Each feature in the docs is marked ✅ implemented,
🚧 partial or ⏳ planned, and [Status and roadmap](docs/status.md) has the full list.

## Licence

No licence has been chosen yet.
