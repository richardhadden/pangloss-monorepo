# pangloss-memgraph

The Memgraph backend: its dialect, connection, DDL, snapshots and bulk load, and `pangloss memgraph info | bulk-load |
bulk-recover`. The storage itself (writes, reads, search, migrations) is [`pangloss-cypher`](../pangloss-cypher), which
this package and [`pangloss-neo4j`](../pangloss-neo4j) share. Set `STORAGE = "pangloss_memgraph:storage"` and add
`"pangloss_memgraph"` to `INSTALLED_APPS`.

Guide: [guide/backends](../../guide/backends/README.md). Commands: [guide/cli](../../guide/cli.md#pangloss-memgraph). Reference: [implementation_docs/memgraph.md](../../implementation_docs/memgraph.md).
