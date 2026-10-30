<div align="center">

# Pangloss

**Prosopography and Network Graph Labyrinth Orientation System ☀︎**

Describe your research data as Python classes. Get validated models, a graph-database store and a REST API.

![Python 3.15+](https://img.shields.io/badge/python-3.15%2B-3776AB?logo=python&logoColor=white)
![Memgraph](https://img.shields.io/badge/graph-Memgraph%20%7C%20Neo4j-FB6E00)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)
![Pydantic v2](https://img.shields.io/badge/models-Pydantic%20v2-E92063)
![Status](https://img.shields.io/badge/status-in%20development-orange)

[All guides](guide/README.md) ·
[Getting started](guide/getting-started/README.md) ·
[Reference docs](docs/README.md) ·
[Migrations guide](guide/migrations/README.md) ·
[SDK guide](guide/sdk/README.md) ·
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
| 🕸️ **Graph storage** | Memgraph or Neo4j; relations are real edges, with a text index for search. [Choosing a database](guide/backends/README.md) |
| 🌐 **REST API** | FastAPI app built from your models, with optimistic locking (`If-Match`) and CORS for a frontend. [REST API](docs/api.md) |
| 🔐 **Users and auth** | JWT tokens or cookie sessions, revocation, login throttling, long-lived personal access tokens. [Users](docs/users.md) |
| 🚚 **Migrations** | `makemigrations` / `migrate` for changes to the models, with a dry run, batches, snapshots and undo. [Migrations guide](guide/migrations/README.md) |
| 📦 **Generated SDK** | `pangloss sdk build` makes an installable, type-stubbed package of your models that talks to the API: the same `Person.get(...)` code in your own scripts, over HTTP, with no database access. [SDK guide](guide/sdk/README.md) |
| 🔎 **Search** | Lists, autocomplete, and structured search by a JSON pattern across documents, entities and reverse relations. [Searching](guide/search/README.md) |
| ✅ **Review, history** | Documents unpublished until checked, with comments; every version kept, with diffs and restore. [Review](guide/review/README.md), [History](guide/history/README.md) |
| 📅 **Dates and calendar** | Uncertain dates, periods, recurrence, feasts and Easter, in the Julian or Gregorian calendar. [Dates](guide/dates/README.md), [Calendar](guide/calendar/README.md) |
| 🌳 **Typology, Zotero** | Hierarchical vocabularies; a Zotero library kept as sources. [Typology](guide/typology/README.md), [Zotero](guide/zotero/README.md) |
| 🖥️ **Interface** | A Solid 2.0 web interface: lists, search, item pages, login, a typology tree, your own components as interface modules (forms to edit items are still to come). [Guide](guide/interface/README.md) |
| 🔭 **Observability** | Structured, secret-safe logging with request ids, audit lines for logins and writes, and slow-query warnings. [Logging](docs/logging.md) |
| ⌨️ **A command line** | `pangloss new-project`, `run`, `dev`, `setup-database`, `users`, `make-stubs`, `check-data` and more. [Command line](docs/cli.md) |

## Quick start

You need **Python 3.15** (the models use lazy imports, PEP 810), [uv](https://docs.astral.sh/uv/) and a running
[Memgraph](https://memgraph.com/) (Docker is easiest). [Neo4j](guide/backends/README.md#neo4j) works too.

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

## Using your data from a script

The server builds a package of your models (`pangloss sdk build`, or as it starts, with `pangloss_sdk_server` in
`INSTALLED_APPS`). A script installs it, with only the light client library and no database driver, and writes the code it would
write on the server:

```python
import pangloss_my_project_sdk as sdk

sdk.connect("https://pangloss.example.org")      # PANGLOSS_TOKEN or a kept login supplies the credentials
from my_app.models import Person

ada = await Person.Create(label="Ada").save()    # a request to the API
found = await Person.list(search_terms="ada")
```

See [the SDK guide](guide/sdk/README.md) and the worked example in [`sdk-demo/`](sdk-demo).

## Repository layout

This is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/); each directory under `packages/` is a
separate distributable package.

| Package | |
|---|---|
| [`pangloss-core`](packages/pangloss-core) | Settings and logging shared by every package |
| [`pangloss-models`](packages/pangloss-models) | The base classes, model initialisation, export, type stubs and the migration planner |
| [`pangloss-memgraph`](packages/pangloss-memgraph) · [`-neo4j`](packages/pangloss-neo4j) | The database backends: query builders, database functions, migrations |
| [`pangloss-users`](packages/pangloss-users) | User models, passwords, access tokens |
| [`pangloss-api`](packages/pangloss-api) | The FastAPI application |
| [`pangloss-cli`](packages/pangloss-cli) | The `pangloss` command |
| [`pangloss-sdk`](packages/pangloss-sdk) · [`-sdk-server`](packages/pangloss-sdk-server) | The client of the API, and the builder and server of it |
| [`pangloss-history`](packages/pangloss-history) · [`-review`](packages/pangloss-review) | Versions of everything written, and restoring them; checking before publishing |
| [`pangloss-dates`](packages/pangloss-dates) · [`-calendar`](packages/pangloss-calendar) · [`-typology`](packages/pangloss-typology) | Uncertain dates; days, feasts and Easter; hierarchical vocabularies |
| [`pangloss-zotero`](packages/pangloss-zotero) | A Zotero library kept in the database, as sources and subjects of factoids |
| [`pangloss-interface`](packages/pangloss-interface) | The web interface (Solid 2.0) |
| [`pangloss-testing`](packages/pangloss-testing) | Live-database fixtures for the tests of add-ons, on either backend |

The guide to each is listed in [the packages guide](guide/packages.md).

```
pangloss-memgraph / -neo4j ──► pangloss-models ──► pangloss-core
pangloss-api / pangloss-cli ──► pangloss-models, pangloss-users, pangloss-core
pangloss-sdk ──► pangloss-models, pangloss-core      (no database driver, no web framework)
```

Also here: [`pangloss-demo/`](pangloss-demo) (a project made with the installer), [`sdk-demo/`](sdk-demo) (a script using
the generated SDK), [`e2e/`](e2e) (browser tests of the interface), [`docs/`](docs/README.md) (the reference) and
[`guide/`](guide/README.md) (tutorials and how-tos).

## Development

```bash
uv sync --all-packages
./run_tests.sh                    # the whole suite, in parallel
uv run ty check                   # types
uvx ruff check . && uvx ruff format .
```

The interface has Playwright tests in [`e2e/`](e2e). The add-on packages' live tests run on Memgraph and Neo4j
(`PANGLOSS_TEST_BACKEND`). The Memgraph tests need Docker, or a Memgraph on `bolt://localhost:7687` (user and password `test`); the fixtures start a
container if there is none. **The tests empty that database**, so don't point them at one you care about.
See [Development](docs/development.md) for the test layout, coverage and conventions.

## Status

Pangloss is in active development and **not yet released**: nothing is published to PyPI, and the APIs may change.
The model layer, the Memgraph and Neo4j backends, REST API, users, migrations, history, review, search, dates, calendar,
typology and the SDK work and are tested; Zotero is tested against a fake Zotero only. The interface can read and search but not
yet edit, and finer-grained permissions are still to come. Each feature in the docs is marked ✅ implemented,
🚧 partial or ⏳ planned, and [Status and roadmap](docs/status.md) has the full list.

## Licence

No licence has been chosen yet.
