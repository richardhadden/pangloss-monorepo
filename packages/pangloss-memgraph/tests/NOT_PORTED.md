# The tests here, and not in the conformance suite

Since 2026-11-01 (phase 9 of `docs/database-abstraction-plan.md`) the tests that every backend passes are written once, in
`pangloss-testing` (`pangloss_testing/conformance/`), and run on each backend. What is left here is what is Memgraph's own:

- `test_initialise_database.py`, `test_migrations_structure_ddl.py`, `test_shipped_migrations.py`,
  `test_shipped_migrations_live.py`: the DDL (`SHOW INDEX INFO`, `CREATE CONSTRAINT ... ASSERT`, the text index on
  `label_folded`) and the migrations shipped with this package.
- `test_model_indexes_live.py`: the indexes a model asks for, and the query plans (`ScanAllByLabel`...).
- `test_bulk_load.py`, `test_bulk_load_cli.py`: the analytical storage mode, and the constraints dropped and made again.
- `test_migration_backend.py`: snapshots (`backup`, `restore`), and the rest of the migration backend.
- `test_database_binding.py`: a second Memgraph (`bulk_memgraph`) used beside the first.
- `test_memgraph_cli.py`: `pangloss memgraph ...`.
