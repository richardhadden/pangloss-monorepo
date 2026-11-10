# Pangloss Neo4j

The Neo4j backend for Pangloss: the same layer as `pangloss-memgraph`, for Neo4j. The storage itself is
[`pangloss-cypher`](../pangloss-cypher), which the two share; this package is the dialect, the connection, the DDL and
the bulk load.

```python
class Settings(BaseSettings[Neo4jDatabaseSettings]):
    INSTALLED_APPS = ["pangloss_neo4j", ...]
    STORAGE = "pangloss_neo4j:storage"
    DATABASE = Neo4jDatabaseSettings(
        DB_URL="bolt://localhost:7687",
        DB_USERNAME="neo4j",
        DB_PASSWORD="...",
        DATABASE_NAME="neo4j",
    )
```

Tested against Neo4j 2026.10 Community only. See [`implementation_docs/neo4j-implementation.md`](../../implementation_docs/neo4j-implementation.md) for how it
differs from the Memgraph module and why (properties cannot be maps, so they are flattened; the text search is Neo4j's full-text
index; no online snapshots).

Guide: [guide/backends](../../guide/backends/README.md). Commands: [guide/cli](../../guide/cli.md#pangloss-neo4j).
