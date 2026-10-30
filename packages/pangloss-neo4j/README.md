# Pangloss Neo4j

The Neo4j database module for Pangloss: the same layer as `pangloss-memgraph`, for Neo4j.

```python
class Settings(BaseSettings[Neo4jDatabaseSettings]):
    INSTALLED_APPS = ["pangloss_neo4j", ...]
    DATABASE_MODULE = "pangloss_neo4j.databases.neo4j"
    DATABASE = Neo4jDatabaseSettings(
        DB_URL="bolt://localhost:7687",
        DB_USERNAME="neo4j",
        DB_PASSWORD="...",
        DATABASE_NAME="neo4j",
    )
```

Tested against Neo4j 2026.10 Community only. See [`docs/neo4j-implementation.md`](../../docs/neo4j-implementation.md) for how it
differs from the Memgraph module and why (properties cannot be maps, so they are flattened; the text search is Neo4j's full-text
index; no online snapshots).

Guide: [guide/backends](../../guide/backends/README.md).
