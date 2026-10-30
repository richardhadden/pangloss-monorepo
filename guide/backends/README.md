# Choosing and running a database

Pangloss stores a project in a graph database through a **database module**: `DATABASE_MODULE` in the settings names a
Python module with the functions the models call (`get_document`, `create_head_node`, `list_items`, `search` ...). There
are three.

| `DATABASE_MODULE` | Package | |
|---|---|---|
| `pangloss_memgraph.databases.memgraph` | `pangloss-memgraph` | The first and best-tested backend. Memgraph, with online snapshots for `migrate --backup` |
| `pangloss_neo4j.databases.neo4j` | `pangloss-neo4j` | The same layer for Neo4j (tested against 2026.10 Community) |
| `pangloss_sdk.databases.api` / `api_sync` | `pangloss-sdk` | Not a database: requests to another Pangloss server ([the SDK](../sdk/README.md)) |

The models, the REST API, the interface, the SDK and the add-on packages (history, review, typology, calendar, dates,
zotero) do not care which of the first two is used. Add the package to `INSTALLED_APPS` as well as naming the module,
because it adds its own commands.

## Memgraph

```python
from pangloss_core.settings import BaseSettings
from pangloss_memgraph.databases.memgraph.settings import MemgraphDatabaseSettings


class Settings(BaseSettings[MemgraphDatabaseSettings]):
    INSTALLED_APPS: list[str] = ["pangloss_memgraph", "my_app"]
    DATABASE_MODULE: str = "pangloss_memgraph.databases.memgraph"
    DATABASE: MemgraphDatabaseSettings = MemgraphDatabaseSettings(
        DB_URL="bolt://localhost:7687", DB_USERNAME="…", DB_PASSWORD="…", DATABASE_NAME="memgraph",
    )
```

```bash
docker run -d --name pangloss-memgraph -p 7687:7687 memgraph/memgraph-mage:3.14.0
pangloss setup-database            # indexes, uniqueness constraints, the text index (safe to repeat)
pangloss memgraph info             # what is there
pangloss memgraph bulk-load FILE   # a JSON Lines file into an EMPTY database, in analytical mode: much faster than writing one at a time
```

## Neo4j

```python
from pangloss_neo4j.databases.neo4j.settings import Neo4jDatabaseSettings

class Settings(BaseSettings[Neo4jDatabaseSettings]):
    INSTALLED_APPS: list[str] = ["pangloss_neo4j", "my_app"]
    DATABASE_MODULE: str = "pangloss_neo4j.databases.neo4j"
    DATABASE: Neo4jDatabaseSettings = Neo4jDatabaseSettings(
        DB_URL="bolt://localhost:7687", DB_USERNAME="neo4j", DB_PASSWORD="…", DATABASE_NAME="neo4j",
    )
```

What differs, that you may notice:

- **No online snapshot in Community**, so `pangloss migrate --backup` says the backend has none (use `neo4j-admin database
  dump`, offline).
- A property cannot be a map, so Pangloss flattens `meta` and annotated values on writing and rebuilds them on reading.
  You do not see this, but a hand-written Cypher query does.
- Text search on Neo4j is a full-text (Lucene) index that folds accents: `zurich` finds "Zürich". On Memgraph it does
  not. The two answer the same search differently until one is changed (on the [TODO](../../TODO.md)).

## Which one?

Both were timed on the demo's models at 8,500 and at 600,000 nodes: [Memgraph and Neo4j compared](../../docs/backend-comparison.md).
In short: Memgraph is faster at reading a single record and needs no tuning; Neo4j loads and writes faster at size and
searches faster, but needs its memory set. For a database loaded once and read (a published edition), Memgraph; for
one edited all the time or loaded in large batches, Neo4j. Read the caveats there before deciding. The
Cypher of each request was profiled on both and the slow plans fixed: [Profiling the backends](../../docs/backend-profiling.md).
How loads and migrations behave at 600,000 nodes: [Large data](../../docs/large-data.md).

## Moving between them

There is no tool for moving data between backends. The models are the same, so a script that reads through one
project's SDK and writes through another's does it, a record at a time. Do not point two projects at one database.

## Tests of add-on packages

An add-on package that needs a live database tests it on either backend with `pangloss-testing`:

```python
# tests/live/conftest.py
from pangloss_testing.live import *  # noqa: F403
```

`PANGLOSS_TEST_BACKEND=memgraph|neo4j` chooses (default Memgraph on `localhost:7687`, Neo4j on `localhost:7693`), either
started in Docker if it is not there. **The tests empty that database.** `./run_tests.sh` runs the add-ons' live tests on
both. The fixtures are `db_driver`, `clear_database`, `ensure_user`, `initialise_settings` and `reset_model_registry`.

An add-on that needs its own Cypher puts it in one `graph.py` and reaches the database through
`pangloss_core.backend`, never `pangloss_memgraph` directly: [Backend-neutral add-ons](../../docs/backend-neutral-addons.md).
