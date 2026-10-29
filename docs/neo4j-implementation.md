# Neo4j backend: implementation plan 🚧

**Status: built 2026-10-29 (see [As built](#9-as-built)); the 572 tests of the package, ported from Memgraph's, pass against Neo4j 2026.10.1 Community. The add-on packages (typology, calendar, zotero) are not yet backend-neutral ([§7](#7-after-this)).**

`pangloss-neo4j` is the same database layer as [`pangloss-memgraph`](memgraph.md) for Neo4j, so that a project is not tied to one vendor: `DATABASE_MODULE = "pangloss_neo4j.databases.neo4j"` and `"pangloss_neo4j"` in `INSTALLED_APPS` instead of the Memgraph pair. The models, the API, the interface and the SDK are not touched: they speak to a backend only through its `exposed_functions`, `setup`, `migration_backend`, `users` and `review` modules (the *contract*, [§3](#3-the-contract-a-backend-must-meet)).

It is a **port**, with the Memgraph package as the template and its test suite as the specification: what Memgraph's tests ask of a backend, the Neo4j package's must meet too ([§6](#6-tests)).

## 1. What was checked, and what it showed

Everything here was run, on 2026-10-29, against `neo4j:latest` in Docker: **Neo4j 2026.10.1 Community** (Cypher 5 and 25), with the Python driver 6.2. Nothing is claimed for other versions or for Enterprise. (The scripts were throwaway; the results that matter are kept as tests, [§6](#6-tests).)

### Your two assumptions

| Assumption | Result |
| --- | --- |
| "Pattern searching is different" | **Right, and more than a syntax change.** Memgraph's `text_search.regex_search("label_text", ".*word.*")` is replaced by the full-text (Lucene) index: `CALL db.index.fulltext.queryNodes("label_text", "*word*")`. Leading wildcards work, matching is case-insensitive and by word (as Memgraph's lower-cased tokens are), a `limit` and a `skip` option exist, and it gives a `score`. Differences that matter: **user text must be escaped** (`a(b` and an empty query are parse errors, where Memgraph's regex accepted most of it); **accents are not folded** by the default analyzer (`*cafe*` does not find "Café": the `standard-folding` analyzer does, and is the choice to make, [§4.2](#42-text-search)); `db.index.fulltext.queryNodes` is *deprecated* in favour of the `SEARCH` clause (which works with full-text indexes in 2026.10; the procedure also works on 5.26 LTS, so it is used, and the notifications are switched off). The `TEXT` index (`CONTAINS`, `STARTS WITH`) is also there but is case-sensitive and a substring of the whole label, not of words: it is not used for search. |
| "Node and edge indexes exist by default" | **Right.** A fresh database has two *lookup* indexes, one for node labels and one for relationship types, so a label index (`model_indexes()` entries of kind `label`) needs nothing. Property indexes do not exist by default and are made as before. |

### What was not assumed, and matters more

| Finding | Consequence |
| --- | --- |
| **A property cannot be a map, or a list of maps.** (Primitives, temporal types, and lists of one primitive type only. A list of mixed types fails; an empty list is fine.) | **The biggest change.** Pangloss stores `meta` on every node as a map (`created_by`, `created_when`, `semantic_spaces`, `context_labels` — a list of maps) and an annotated value as a map (`{value, certainty}`). Both are flattened on writing and rebuilt on reading ([§4.1](#41-properties-maps-are-flattened)). Edge properties have the same limit. |
| DDL is `CREATE INDEX name IF NOT EXISTS FOR (n:L) ON (n.p)` and `CREATE CONSTRAINT name IF NOT EXISTS FOR (n:L) REQUIRE n.p IS UNIQUE`. The Memgraph forms (`CREATE INDEX ON :L(p)`, `... ASSERT ...`) are syntax errors. Indexes and constraints are **named**, and dropped by name. | All DDL is rewritten. Names are made from label and properties, so they are the same every time. |
| A **uniqueness constraint creates its own index**. An index made afterwards on the same properties is silently skipped with `IF NOT EXISTS` and an error without it; **an index made first makes the constraint fail** (`IndexAlreadyExists`). | Constraints first, and an index that a constraint already provides is not made (and not reported as "created"). A migration that adds a constraint where an index exists drops the index first. |
| Composite uniqueness (`REQUIRE (n.app, n.name) IS UNIQUE`) works in Community. **Property existence and node-key constraints do not** (Enterprise). | `PGMigration (app, name)` is fine. Pangloss uses no existence constraints. |
| Labels in a query: `MATCH (n:$node_type)` is a syntax error; **`MATCH (n:$($node_type))`** works, and so do `SET n:$($label)` and `CREATE (n:$($label))`. | Every parameterised label is changed (a mechanical search). |
| `collect(a, b)` (a map from two arguments, used for the facets of a list) does not exist. APOC is not installed. | The facets are collected as a list of `{type, nodes}` and made a map in Python. **APOC is not used**, so that a stock Neo4j works. |
| `id(n)` works but is deprecated (`elementId(n)`, a string). | Orderings that used `id(n)` as the last tie-break use `n.id` (the uuid) or `elementId(n)`. |
| `CALL { WITH x ... }` works, deprecated for `CALL (x) { ... }`. `UNION` inside, `EXISTS { }`, `COUNT { }`, map projection with nested maps in the *result*, `FOREACH`, `MERGE`, slices, `SKIP (expr)`, `randomUUID()`, `datetime()` all work as in Memgraph. | Queries keep the old form where it works (the notifications are off); new ones use the scope clause. |
| The full-text index sees a node **written in the same transaction**, sees a changed label, forgets a deleted node, and indexes a node that gets the `PGIndexableNode` label later. | No "write, commit, then search" workaround. Index creation is asynchronous: `CALL db.awaitIndexes()` after creating one. |
| DDL cannot be mixed into a transaction with data (syntax error). | As in Memgraph (`run_statement` on its own session). |
| One user database (`neo4j`) in Community. | `DATABASE_NAME` stays a setting, defaulting to `neo4j`. Tests wipe the database instead of making one. |
| No online snapshot in Community. | `backup`, `backups`, `restore` and `backup_notice` are *optional* in the migration contract: left out, and `pangloss migrate --backup` says the backend has none (Neo4j's way is `neo4j-admin database dump`/`backup`, offline). |
| The driver reports every deprecation as a notification (a log line per query). | The driver is made with the deprecation class of notifications disabled. |

## 2. What is reused and what changes

Copied from `pangloss_memgraph`, renamed, and changed only where the table above says (about 8,400 lines of source):

| Module (`databases/neo4j/`) | Change |
| --- | --- |
| `settings.py` | `Neo4jDatabaseSettings` (`DB_URL`, `DB_USERNAME`, `DB_PASSWORD`, `DATABASE_NAME = "neo4j"`) |
| `database.py` | the same transactions, logging, timeouts and migration refusal; the driver without deprecation notifications. `neo4j.unit_of_work(timeout=...)` is honoured by Neo4j |
| `properties.py` (new) | the flattening of maps ([§4.1](#41-properties-maps-are-flattened)) |
| `from_database.py` | also rebuilds the flattened properties |
| `initialise_database.py` | Neo4j DDL; constraints before indexes; the full-text index; `awaitIndexes` |
| `build_create_query.py`, `build_update_query.py` | node and edge properties go through `properties.flatten` |
| `build_read_query.py`, `build_list_query.py`, `build_search_query.py`, `build_autocomplete_query.py`, `read_incoming.py`, `build_tree.py`, `delete_node.py` | `$($label)`, the full-text call, `meta` read from its flat properties, facets, tie-breaks |
| `validate_write.py`, `lookup.py`, `visibility.py`, `users.py`, `review.py` | the same Cypher, checked for map properties (users and review keep tokens, sessions, state) |
| `exposed_functions.py`, `setup.py` | the same functions |
| `migration_backend.py`, `migrations/` (`operations.py`, `runner.py`, `conversion.py`) | DDL operations in Neo4j form; the 70-odd data operations (rename a model, change a cardinality, wrap a relation in a semantic space ...) keep their Cypher except where they touch `meta`, a map, `$label` or `id()` |
| `bulk.py` | see [§4.4](#44-bulk-loading) |
| `cli.py` (`pangloss neo4j ...`) | `info`, `indexes`, `bulk-load` as in Memgraph, without the analytical storage mode |
| `pangloss_neo4j/migrations/` | the shipped migrations of the structure, as `pangloss_memgraph.migrations` has, but making Neo4j's |

**Not shared with `pangloss-memgraph`.** The two packages are copies of each other, not one package with two drivers: about two thirds of the code is the same text, and it will drift. The alternative, a `pangloss-graph-common` package holding the shared part with each backend supplying its dialect (text search, DDL, flattening), is the better structure if there will be a third backend, and a larger change to a package that works. It is **not done here**; the copy is kept close enough (same file names and function names) that moving the shared part later is a refactor, not a rewrite. (Decision for you: [§8](#8-decisions-and-open-questions).)

## 3. The contract a backend must meet

What the rest of Pangloss imports from the module named by `DATABASE_MODULE` (found by reading the callers, [list in the tests](#6-tests)):

- `exposed_functions`: `create`, `read`, `update`, `delete`, `list`, `search`, `autocomplete`, `incoming`, `tree`, `bulk` and the rest the API and SDK call (the same names and signatures as Memgraph's, so the contract test calls both);
- `setup`: `create_database`, `connect`, `disconnect`, `setup_database`;
- `migration_backend`: `structure`, `ensure_ready`, `applied`, `has_data`, `lock`, `unlock`, `apply`, `unapply`, `dry_run` (required), and the backup functions (optional);
- `users` and `review` (the functions `pangloss_users` and `pangloss_review` call);
- the `Database` object and `Transaction` type, and `visibility.unpublished_visible`, which **add-on packages import directly from `pangloss_memgraph`**: `pangloss-typology` and `pangloss-calendar` (`graph.py`), `pangloss-zotero` (store), `pangloss-sdk-server` (a list of app names). Those packages therefore do not yet work on Neo4j: see [§7](#7-after-this).

## 4. Design

### 4.1 Properties: maps are flattened

One convention, in one module (`properties.py`), used at the one place nodes and edges are written (`get_node_fields_as_writable_dict` and the edge builder) and the one place rows are read (the `from_database` hook of `pangloss_models`, which already converts the driver's temporal types):

- a map becomes properties named by the path, joined with a dot: `meta.created_by`, `meta.created_when`, `meta.semantic_spaces`; an annotated value `date` of `{value, certainty}` becomes `date.value`, `date.certainty`. (A name with a dot is written with backticks in Cypher: `` n.`meta.created_by` ``. A model field cannot be named with a dot, so there is no clash.)
- a **list of maps** (and a list of mixed values or lists) is stored as a **JSON string under the name with `#json` after it**: `meta.context_labels#json`, `sizes#json` (no model field has a `#` in its name, so text that happens to be JSON is never taken for one; the first plan, a fixed list of names, failed on a `list[TypedDict]` field, which the tests found). What the queries search is also stored flat: `meta.context_label_types` (a list of strings). `meta.context_labels` is always JSON, even when empty, so that there is one form to read. Reading decodes the string.
- an empty map is no property; `None` is no property (as `SET n.x = null`).
- reading is the inverse: dotted names are nested again, so what the models receive is what Memgraph gives them.

Queries that reached into a map (`n.meta.semantic_spaces`, `SET n.meta.updated_by = ...`) are changed to the flat names. There are 17 such places (listed by `grep`), each covered by a test.

### 4.2 Text search

The one full-text index `label_text` on `:PGIndexableNode(label)`, as Memgraph has one text index of that name. A word typed by the user becomes `*word*`, folded (below) and with nothing that Lucene reads as syntax: the text is cut where the index cuts a label into words (at anything that is not a letter, a digit or an underscore), so `max-planck` is the words `max` and `planck` (escaping `-` would have matched nothing, as the index has no token with a hyphen). The words of a search are *and*-ed by the same `UNWIND $patterns ... count(*) = size($patterns)` the Memgraph queries use (so the ranking sum of scores, and the query shapes, stay the same). The list, deep search, truncation check and autocomplete queries differ in this call only.

- **Analyzer:** `standard-folding` (lower-cases and folds accents), so that "cafe" finds "Café" and "zurich" finds "Zürich". Memgraph's index does not fold; a project that wants exact accents would be given a setting. (Decision, [§8](#8-decisions-and-open-questions).)
- **Hit limit:** `SEARCH_HIT_LIMIT` is passed as the procedure's `limit`, as for Memgraph, and truncation is detected the same way (ask for one more).
- **Wildcard terms are not analysed.** With the folding analyzer, `*zurich*` finds "Zürich" but `*Zürich*` finds nothing (checked): Lucene lower-cases a wildcard term but does not fold it. So the words of a search are folded in Python (`unicodedata` NFKD without the combining marks, and a table for what does not decompose: ß, æ, œ, ø, đ, ł, þ) before they are made into patterns, as the index folded the labels.
- **Empty or all-special input** gives no pattern, as an empty search gives none now, instead of a parse error.

### 4.3 Structure (DDL)

`structure()` is unchanged in what it says (the same `UNIQUE_CONSTRAINTS`, `INDEXES`, text index and model indexes: the migrations that make them are the same changes). What changes is how they are made: names from label and properties (`pg_<label>_<props>_idx`, `..._unique`), constraints first, indexes that a constraint covers skipped, label indexes skipped (lookup indexes exist), the full-text index made with `awaitIndexes`. `SHOW INDEXES` and `SHOW CONSTRAINTS` give the existing structure, compared by (label, properties, kind), not by name, so a database made by hand is recognised.

### 4.4 Bulk loading

Memgraph's `bulk-load` relies on its *analytical storage mode* (no transactions, much faster) and on dropping constraints during the load. Neo4j has no such mode; the equivalent is `neo4j-admin database import` on an empty database, which is offline and has its own file format. So: the same command, the same file format, loaded in large batches with `UNWIND` in ordinary transactions into an empty database, with constraints in place. It will be slower than Memgraph's analytical load; how much is measured and written down, not assumed. The offline import is a possible later addition.

### 4.5 Migrations

The data operations are the bulk of `operations.py` and are mostly Cypher that is the same in both. Each is run by the ported test of the same name ([§6](#6-tests)); whatever fails is changed. Known to change: the DDL operations (`add_index`, `remove_index`, `add_constraint`, `remove_constraint`, `rebuild_text_indexes` — no longer needed after a restore, so not ported), operations that read `n.meta`, and the `labels` and `id()` uses.

## 5. Package layout

```
packages/pangloss-neo4j/
  pyproject.toml              (depends on neo4j, pangloss-models, pangloss-users)
  README.md
  src/pangloss_neo4j/
    migrations/               shipped migrations: the structure of the database
    cli.py                    `pangloss neo4j ...`
    databases/neo4j/          the modules of §2, with the names Memgraph's have
  tests/
```

## 6. Tests

The tests come first, as the specification, and are of two kinds:

1. **Ported:** the 60-odd test files of `pangloss-memgraph/tests` (573 tests) are copied, `pangloss_memgraph` to `pangloss_neo4j`, with the container and `conftest.py` for Neo4j. Tests of Memgraph's own machinery have no Neo4j counterpart and are dropped, each listed in `tests/NOT_PORTED.md` with the reason: snapshots (`backup`, `restore`), the analytical mode of `bulk-load`, `SHOW INDEX INFO` parsing, the text-index files. Nothing else is dropped without a note.
2. **New, for the differences of [§1](#1-what-was-checked-and-what-it-showed):** flattening round-trips (`properties.py`, with no database); full-text escaping and accent folding; constraint-before-index order and idempotent setup; a `meta` and an annotated value written and read back equal to what Memgraph returns; the contract: every function that `pangloss_users`, `pangloss_review`, `pangloss_api`, `pangloss_cli` and `pangloss_models` call on the backend exists with the same signature as Memgraph's (checked by `inspect`, so it fails when Memgraph gains one).

The suite uses its own container (`neo4j:latest`, port 7693, user `neo4j`, an ephemeral database) and its own xdist group, and is run in a separate `pytest` process by `run_tests.sh` (`--no-neo4j` skips it), because the test database is wiped and global settings are per process. If Docker is not running the suite is skipped with the reason, not failed.

## 7. After this

Not part of this task, recorded so that it is not forgotten:

- The add-on packages (`pangloss-typology`, `pangloss-calendar`, `pangloss-zotero`) import `pangloss_memgraph` for the `Database` and write their own Cypher. To run on Neo4j they find the backend through `DATABASE_MODULE` instead, and their Cypher is ported and tested the same way.
- The demo project and `pangloss new-project` offer a backend.
- Enterprise features (property existence constraints as a safety net, online backup).
- A version matrix (5.26 LTS and later) in CI.
- **A backend-neutral layer for the Cypher in other packages (noted 2026-10-29).** Typology, calendar, zotero (and any later add-on) hold hard-coded Cypher, much of it Memgraph's (`text_search`, `*BFS`, map properties). Rather than port each package's strings, put the pieces that differ behind the backend: a small interface the backend provides (text search clause, bounded traversal, reading and writing `meta` and annotated values, `elementId`), which the add-ons call instead of writing the dialect. Decide the interface from what the three packages actually use; port one add-on (typology, the smallest) first to test it. Today's `test_contract.py` checks only the functions `pangloss_models`, `pangloss_api` and the others call, not the add-ons' queries.
- **Accent-insensitive search on Memgraph too (noted 2026-10-29).** On Memgraph `zurich` does *not* find "Zürich" (its text index lower-cases but does not fold; this was not known before the Neo4j work), while Neo4j's folding index finds it. The two backends therefore answer the same search differently. Options: (a) fold on both sides on Memgraph, by writing a folded copy of the label (`label_folded`, indexed in the text index) and folding the search words in Python with the same function as `pangloss_neo4j.databases.neo4j.schema.fold`; (b) accept the difference and document it. (a) needs a migration to fill `label_folded` for existing data, and the folding function moved somewhere both backends import (`pangloss_models`), and would make the backends agree. Also decide whether exact-accent search needs a setting.

## 8. Decisions and open questions

1. **Copy or share?** ([§2](#2-what-is-reused-and-what-changes)) Recommendation: copy now, extract a common package when a third backend or the second round of fixes makes the drift painful.
2. **Accent folding by default?** ([§4.2](#42-text-search)) Recommendation: yes (`standard-folding`): a name search that does not find "Zürich" from "zurich" is a worse default than one that is a little looser than Memgraph's.
3. **Which Neo4j versions are supported?** Only 2026.10 Community is tested here. Recommendation: say so in the README; add 5.26 LTS to the container matrix when someone needs it.
4. **`bulk-load` speed** ([§4.4](#44-bulk-loading)) is unknown until measured.

## 9. As built

**Package** `packages/pangloss-neo4j` (`DATABASE_MODULE = "pangloss_neo4j.databases.neo4j"`, `"pangloss_neo4j"` in `INSTALLED_APPS`, `pangloss neo4j ...`): the modules of [§2](#2-what-is-reused-and-what-changes), with the names Memgraph's have, plus `properties.py` (flattening), `schema.py` (names, listing, DDL and the search patterns) and `traversal.py` (quantified path patterns). Verified with 572 tests (about 130 s, against 573 in 100 s for Memgraph's), the list in `packages/pangloss-neo4j/tests/NOT_PORTED.md` being what is not the same. `run_tests.sh` runs them as a run of their own (`--no-neo4j` skips it). A project made in a temporary directory with the real `pangloss` command (`makemigrations`, `migrate`, `users create`, `neo4j bulk-load`, `check-data`) works against Neo4j (`test_bulk_load_cli.py`).

**What the tests found that the checks of [§1](#1-what-was-checked-and-what-it-showed) had not**

| Found | Done |
| --- | --- |
| `[*BFS (e, n \| ...)]`, Memgraph's walk with a test on every edge and node (9 places, in the read, search, update and migration queries) | quantified path patterns: `(a) ((x)-[e]->(y) WHERE ...)+ (b)` (`traversal.py`). They find every path, not the shortest to each node; the queries take each node and edge once, so nothing changed but the number of paths in a diamond |
| Neo4j refuses an aggregate mixed with a grouping key in one expression (`found + collect(x)`) | those steps are split in two (two places in the read query) |
| `CALL { WITH x, $p AS y ... }` and `WITH x WHERE ...` as an import are errors | `CALL (x) { ... }` in the deep search |
| **A transaction timeout is a `ClientError` (`TransactionTimedOut...`), where Memgraph's is a `TransientError`** | `is_timeout` in `exposed_functions`: a search that is too slow is `PanglossSearchTimeoutError`, as for Memgraph (without this it would have reached the user as a database error) |
| **Two updates from the same version at once both succeeded (4 versions of 1)**: Neo4j reads what is committed and does not run the second writer again | `replace_head_node` takes the node's lock first (`lock_node`: set and remove a property, which holds the node until the transaction ends) and reads the version after it. The same test now passes every run |
| A check in a write (`check_urls_available`) after another write committed sees its data, and raises a conflict that is a lost race | `write_with_retries` also runs the write again on `PanglossConflictError` and on `ConstraintError` (Neo4j's name for a unique violation, whose message is not "unique constraint"), so the second finds the entity and shares it |
| `valueType()` says `STRING NOT NULL`; `labels(n)` has no order; `EXPLAIN` names other operators | tests changed ([NOT_PORTED.md](../packages/pangloss-neo4j/tests/NOT_PORTED.md)); nothing reads a label order |
| An enum inside a `TypedDict` was rewritten with `map.set_key` | one assignment per flat property. An enum inside a **list of `TypedDict`s** is JSON text, which Cypher cannot change a part of: that migration is refused with `PanglossMigrationNotSupported` (not supported by this backend, said so) |

**Differences a user will meet**

- `pangloss migrate --backup`, `backups` and `restore` say "This database cannot take a backup" (Neo4j Community has no online snapshot).
- `pangloss neo4j bulk-load` writes in ordinary transactions with the constraints in place. It does not use an analytical mode (there is none), so a duplicate id fails its own record, and there is no "read-only until the duplicates are put right" state. Not yet measured against Memgraph's analytical load: expected to be slower.
- The search finds words by their folded form (a name search for `zurich` finds `Zürich`; Memgraph's does not fold).
- Lists of maps and `meta` are not readable in the database browser as maps: they are flat properties and JSON text.

**Not done**

- The add-on packages ([§7](#7-after-this)).
- The speed of the queries (quantified path patterns, the full-text index, the deep search) has not been measured on a large database: only that it is right.
- Neo4j Enterprise, and other versions than 2026.10.1 Community.
