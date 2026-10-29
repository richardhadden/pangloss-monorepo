# Tests of `pangloss-memgraph` that are not in this package, or are not the same

The tests here are those of `pangloss-memgraph` run against Neo4j (see `docs/neo4j-implementation.md`). What differs, and why:

## Left out, to be ported with the add-on packages

`test_typology_live.py`, `test_calendar_live.py`, `test_calendar_characterisations_live.py`, `test_calendar_service_live.py`:
they run `pangloss-typology` and `pangloss-calendar` against the database, and those packages import `pangloss_memgraph`
directly (and write Cypher of their own). They are the same tests with the backend swapped once the add-ons find the backend
through `DATABASE_MODULE` (plan, section 7).

## Replaced, because Memgraph's feature has no Neo4j counterpart

- **Snapshots** (`backup`, `backups`, `backup_notice`, `restore`; four tests in `test_migration_backend.py`): Neo4j Community has no
  online snapshot. One test, `test_this_backend_has_no_snapshots_and_the_commands_say_so`, says so.
- **The analytical storage mode** (`test_bulk_load.py`): `bulk_ingest` here keeps the constraints and changes no mode, so the tests
  of the mode, the dropped constraints, the duplicates found when they come back, and what the lock keeps, are replaced by tests
  of what it does do (a duplicate fails its own write; the lock is released; a killed load is recovered by releasing it).
- **`SHOW INDEX INFO` / `SHOW CONSTRAINT INFO`, `CREATE INDEX ON`, `ASSERT`** (setup, structure, shipped migrations, model
  indexes, dry run): rewritten for `SHOW INDEXES`, `SHOW CONSTRAINTS` and named DDL (`schema_helpers.py`). A label index is not
  made, as every database has one; a unique constraint's index is not a second index.
- **Query plans** (`test_model_indexes_live.py`): Neo4j's operators (`NodeByLabelScan`, `NodeIndexSeek`) instead of Memgraph's
  (`ScanAllByLabel`...).

## Changed in what they assert, because the storage differs

- Tests that read a node's `meta` or an annotated value straight from the database: Neo4j keeps them as flat properties
  (`meta.created_by`...), so `helpers.run` nests the maps again and `n.meta AS meta` is translated (`helpers.memgraph_meta`).
- `test_a_node_that_fulfils_a_class_has_its_labels` no longer asserts the *order* of the labels: Neo4j keeps none.
- `test_migration_batches` strips ` NOT NULL` from `valueType()`.
- The two tests of a search that takes too long use a query Neo4j cannot count without looking (it works out a bare count of a
  cartesian product at once).

## Added

`test_properties.py` (flattening), `test_search_patterns.py`, `test_contract.py` (Memgraph's backend and this one have the same
functions with the same signatures), and in `test_initialise_database.py` the full-text index (accents, special characters,
visibility in the writing transaction).
