# The database abstraction ✅

How Pangloss is kept apart from the database that stores its data: what was chosen, why, and what was built
(2026-10-31 to 2026-11-01, branch `refactor-db-layer`, in eleven phases). This page is condensed from the proposal
and its implementation plan; both are in the history of the repository (`implementation_docs/database-abstraction.md` and
`docs/database-abstraction-plan.md`, before 2026-11-10), with the detail of each phase. How the code is laid out now
is in [Packages](packages.md), [Memgraph](memgraph.md) and [Neo4j](neo4j-implementation.md).

## Why

`pangloss-neo4j` was made as a copy of `pangloss-memgraph`. By the [review of 2026-10-31](code-reviews.md) the two
were about 3,000 identical lines, with about 20,000 lines of copied tests each, and nearly every fix had to be made
twice. The only description of what a backend must do was the other backend's tests.

## The level of abstraction

| Level | What it means | Verdict |
|---|---|---|
| Driver ("any Bolt database") | share everything, change the URL | False: the backends differ in DDL, text search, property types and isolation |
| Query (a Cypher AST or builder) | build queries as objects, render them for each database | **No.** A large framework for about a dozen differences. It hides the query text, which the performance work depends on (the plan cache keys on the text; queries are shaped for each planner). No use for a store that is not Cypher |
| Operation | domain operations ("create this head document", "list this class"); a backend does them as it likes | **Yes, as the outer layer.** It is what callers use, and the only level that admits a backend that is not Cypher |
| Difference point | one Cypher implementation that asks a `Dialect` at the named points where the backends differ | **Yes, as the inner layer**, for Cypher backends |

So there is **no Cypher query builder**, and a method is added to the `Dialect` only when a diff shows a difference.
If a dialect starts to hold whole query modules, that part was not shared after all and belongs to the backend.

## What differs between Memgraph and Neo4j

Measured by diffing the two packages with the names normalised. This is what the `Dialect` covers.

| Difference | Memgraph | Neo4j |
|---|---|---|
| Walking a tree | `-[*BFS (e, n \| …)]->` | a quantified path pattern |
| Properties | maps are stored as maps | maps flattened to `meta.created_by`; lists of maps as JSON; results decoded |
| A label as a parameter | `MATCH (n:$t)` | `MATCH (n:$($t))` |
| Text search | `text_search.regex_search` on a folded label | `db.index.fulltext.queryNodes`, words folded and escaped |
| Facets, tie-break order | `collect(k, v)`; `id(n)` | a list made into a map in Python; `n.id` |
| Which error is a timeout, which a unique violation | `TransientError` with "timeout"; `ClientError` with "unique constraint" | `TransactionTimedOut`; `ConstraintError` |
| Isolation | snapshot: concurrent writes conflict at commit and are retried | read committed: an update takes a lock on the node first, and a conflict found by a check is retried |
| DDL and reading the schema | `CREATE INDEX ON :L(p)`, `SHOW INDEX INFO` | named `CREATE … IF NOT EXISTS`, constraints before indexes |
| Bulk load | analytical storage mode, constraints dropped and restored | batches in ordinary transactions |
| Snapshots | `CREATE SNAPSHOT` | none in Community |

They are of three kinds: **fragments** of a shared query (dialect methods that return Cypher text), **codecs** round
a query (methods that wrap parameters, results or exceptions), and **whole subsystems** (DDL, bulk load, snapshots),
which stay in each backend's package.

## Decisions (2026-10-31)

1. **A backend that is not Cypher (RDF) is not a goal now.** The typed `Storage` port with every operation as a
   method is deferred; the seams it needs are kept (below).
2. The shared package is **`pangloss-cypher`**.
3. **`STORAGE = "pangloss_memgraph:storage"`** replaces `DATABASE_MODULE` (still read, with a
   `DeprecationWarning`). It names a typed `pangloss_core.storage.Storage`: a name, capabilities, and the parts.
4. **Accents are folded on both backends**: `zurich` finds "Zürich" on either.

## What was built

| Phase | What |
|---|---|
| 0 | The review's fixes, in both backends, each with a test seen to fail first |
| 1 | The database is found when a function is called, not when a module is imported: `Database(settings)` has no side effects; `install`, `current`, `using`; `STORAGE` |
| 2 | `packages/pangloss-cypher`, with the files that were identical moved into it |
| 3 | `pangloss_cypher/dialect.py`, the `Dialect` protocol; transactions and the write path in the kit |
| 4 | One visibility rule, `pangloss_cypher/fragments.py` (`visible`, `hidden`), used by the add-ons too; an add-on that runs its own Cypher says `requires = {"cypher"}` |
| 5 | `pangloss_models.text.fold`; `label_folded` on Memgraph, which its text index is on |
| 6 | The write plan apart from its Cypher: `plan_create` and `plan_update` give a `WritePlan` (a tree of `PlannedNode`s and their `Relation`s) that knows no database |
| 7 | Read, list, search and autocomplete in the kit. Each backend's `exposed_functions.py` is a re-export of `pangloss_cypher.operations` |
| 8 | Typology's writes go through the models (a `before_write(tx)` hook on the update path), not round them |
| 9 | One conformance suite, `pangloss_testing/conformance/`, in place of the two copied suites. Where the copies differed, Neo4j's was taken: its changes were the neutral ones |
| 10 | Migration operations in the kit, asking a `MigrationDialect` where the backends differ (about 30 places, mostly how `meta` is stored) |

Since then (2026-11-10) the record of migrations is the kit's too: see [code reviews](code-reviews.md).

A backend's package is now its dialect, its connection, its DDL, its bulk load and its commands.

## Kept for a `Storage` port

Not built. What the phases left for it: a write plan (6) and a read shape (7) that know no database; a conformance
suite that goes through the models, not Cypher (9); `Capabilities`, and `cypher` declared by the add-ons that need
it (3, 4); no exception of a driver leaving the kit. See also the report on an
[RDF backend](rdf-oxigraph-feasibility.md).

## Rules that came out of it

- **One query text has to suit two planners.** A shared query may be replaced whole by a dialect where the planners
  want different shapes. Measure on the large database ([large data](large-data.md)) before and after changing one.
- **The same shape of query must be the same text**, so that the plan cache is used: a fragment must not hold
  anything that varies (no random names).
- **The difference in isolation is one of meaning, not of syntax.** It is explicit in the dialect
  (`retry_on_check_conflict`, `before_replace`) and has a concurrency test that runs on both backends.
- **A fix to how storage behaves gets a test in the conformance suite**, not in one backend's tests.
