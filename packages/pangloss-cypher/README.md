# pangloss-cypher

What the Cypher backends of Pangloss (`pangloss-memgraph`, `pangloss-neo4j`) share: one copy of the code that is the
same on both. A backend imports it from here; where the two databases differ, the backend keeps its own.

See `docs/database-abstraction.md` and `docs/database-abstraction-plan.md`.
