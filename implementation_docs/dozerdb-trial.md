# DozerDB trial: things to test

[DozerDB](https://dozerdb.org/) is a GPL plugin for Neo4j Community that adds multi-database, property existence constraints, an open build of GDS, and hardened telemetry-off images. It is not Neo4j Enterprise: no clustering, no RBAC, no online backup. This page lists what to check before deciding whether to use it. Nothing here has been run yet.

Background: `pangloss-neo4j` is tested only on `neo4j:2026.10.1` Community (see `neo4j-implementation.md`). DozerDB's 2026.10 build is `2026.10.0.0`, and its docs say the jar must match the exact Neo4j version, so the first question is whether it loads on 2026.10.1 at all.

## 1. Does it run?

- [ ] Pull `graphstack/dozerdb` (look for a 2026.10 tag) and start it on a spare port (e.g. 7695), as the exploration containers do.
- [ ] If the image is on 2026.10.0 and not 2026.10.1, note it. Try the plugin jar on the `neo4j:2026.10.1` image (copy it into `lib/`, not `plugins/`) as a second route.
- [ ] Confirm Bolt connects with the driver version `pangloss-neo4j` pins, and that `SHOW DATABASES` works.
- [ ] Note the Java version the image needs (21) and the image size against `neo4j:2026.10.1`.

## 2. Does the existing suite pass unchanged?

The tests start their own container from `NEO4J_IMAGE` in `packages/pangloss-neo4j/tests/conftest.py:34` and `image=` in `packages/pangloss-testing/src/pangloss_testing/backends.py:65`.

- [ ] Point both at the DozerDB image (temporarily, or through an env var if adding one is easy) and run `./run_tests.sh` with Memgraph skipped: conformance on Neo4j, `pangloss-neo4j` (583 tests), and the add-on live tests.
- [ ] Compare the pass count with the 583 on stock Neo4j. Record any failure with its cause (version mismatch, constraint behaviour, full-text index, locking).
- [ ] Check start-up time against stock Neo4j, since the test containers are started per run.

## 3. Multi-database

The driver takes `database=` on sessions, so the question is how much of `Database` and the backend assume the default database.

- [ ] `CREATE DATABASE test_a` / `DROP DATABASE test_a` through the driver: how long does each take?
- [ ] Find where `pangloss-neo4j` opens sessions and see whether a database name can be passed through `Database` (and `pangloss_core.backend.current()`) without touching callers. Sketch it; don't merge it.
- [ ] Check that schema setup (indexes, full-text index, constraints) is per database and re-created cleanly in a new one.
- [ ] Test isolation: could the two test containers (:7693 main, :7694 bulk load) become two databases on one server? Does that cut start-up time, or does `CREATE DATABASE` cost more than it saves?
- [ ] Bulk load: does a fresh database give a clean "empty DB" for the bulk-load tests?
- [ ] Concurrency: two databases written from two xdist workers at once. Anything shared (locks, the `ensure_lock` node, user bootstrap) that assumes one database?
- [ ] Use case to decide: would one database per corpus or project be wanted in the product, or is this only for tests?

## 4. Property existence constraints

- [ ] List the constraints the schema code creates now (uniqueness on `uid`, etc.) and the application-level checks for required properties (`type`, `uid`, `meta.created_by`).
- [ ] Try `CREATE CONSTRAINT ... REQUIRE n.uid IS NOT NULL` on stock Community (should fail) and on DozerDB (should work).
- [ ] If it works, find which checks it could back up. Does a violation raise an error the backend turns into a sensible exception, or does it surface as a raw `ClientError`?
- [ ] Cost: does the existence constraint slow writes? Rerun the batch-write measurement from `backend-profiling.md` with and without it.
- [ ] Bulk load and migrations: do existence constraints get in the way of loading, or of migration steps that add properties in stages?
- [ ] Decide whether a backend-neutral way to declare "required" is possible. Memgraph has existence constraints too, so this might belong in the shared schema layer.

## 5. Open GDS (only if network analysis is wanted)

- [ ] Install the GDS jar on a DozerDB container and project a small graph from the demo data.
- [ ] Run one algorithm that would matter for a prosopographical corpus (e.g. weakly connected components or PageRank) and note how the projection copes with Pangloss's relation modelling (relation nodes versus edges).
- [ ] Decide if this is a feature to build or a note in the docs.

## 6. Things it should not change (sanity checks)

- [ ] Flattened `meta.*` properties and `name#json` values behave as on stock Neo4j.
- [ ] Full-text search with `standard-folding` gives the same results.
- [ ] Timeouts still surface as a `ClientError` and the conformance timeout tests pass.
- [ ] Telemetry really is off (no outgoing connections from the container).

## 7. Decision notes to record

- [ ] Version lag: how soon after a Neo4j release does DozerDB follow? Check the release history.
- [ ] Support and risk: community best-effort support, one main sponsor. Is that acceptable for something we depend on, or only as an optional extra?
- [ ] Licence: GPL plugin used as a server component. Confirm that is fine for how Pangloss is distributed (including any Docker image we publish; see `publishing.md`).
- [ ] Write the outcome in `neo4j-implementation.md` or `backend-comparison.md`, and update the Neo4j backend memory note.

## Suggested order

1 → 2 first. If the suite does not pass, stop there. Then 3 (multi-database), which is the likeliest benefit. Do 4 next. Do 5 only if there is demand.
