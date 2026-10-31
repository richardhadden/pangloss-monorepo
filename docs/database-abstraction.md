# A database abstraction layer: what it would take

**Status: proposal (2026-10-31). Nothing here is built.** It follows on from
[code-review-2026-10-31.md](code-review-2026-10-31.md), finding 6 (the two backends are copies), and from the decision
recorded in [neo4j-implementation.md §2](neo4j-implementation.md#2-what-is-reused-and-what-changes): copy now, and
extract a common package "when a third backend or the second round of fixes makes the drift painful". The review is that
second round of fixes. Most of its findings have to be made twice.

## Summary

Pangloss already has an abstraction layer. It is the set of module names that `DATABASE_MODULE` must provide
(`exposed_functions`, `setup`, `migration_backend`, `backend`), and it sits at the right level: **domain operations**
("create this head document", "list this class"), not queries. What it lacks is everything that would make it *real*:

- it is not written down as a type;
- it is bound by importing modules and assigning functions to classes;
- the semantics it promises (visibility, versioning, `meta`, reverse edges) exist only as Cypher text, repeated in each
  backend;
- the only thing that checks a backend meets it is a copy of the other backend's test suite.

The proposal has two layers and one test suite:

1. **A storage port.** A typed `Storage` protocol in `pangloss-models`, with the operations the models, the API, users,
   review and migrations call. It uses Pangloss's own types and exceptions, and declares its optional features as
   capabilities. Any backend implements it, including a non-Cypher one such as the [RDF/Oxigraph
   idea](rdf-oxigraph-feasibility.md).
2. **A Cypher kit.** A new package, `pangloss-cypher`, holding the one implementation of the port for property-graph
   databases. Where Memgraph and Neo4j differ, it calls a `Dialect` object. Each backend package shrinks to its dialect,
   its connection, its DDL, its bulk load and its CLI.
3. **A conformance suite.** One test suite in `pangloss-testing`, written against the port. Every backend runs it. It
   replaces the two copied suites of about 20,000 lines each.

Do **not** build a general Cypher query builder or AST. The measured differences between the backends are few and
specific (listed in [§3](#3-what-actually-differs-measured)), and a query builder would not help an RDF backend anyway.
Abstract at the level of operations, and inside the Cypher kit abstract at the level of the **named points where the
backends differ**.

Rough size: 4 to 6 weeks of focused work, done in steps that each leave the tests passing ([§8](#8-how-to-get-there)).
The first step, moving the identical files, takes about a day and pays off at once.

---

## 1. What exists today

| Piece | What it is | Problem |
|---|---|---|
| `DATABASE_MODULE` | a module path in the settings | the module is the interface; nothing types it |
| `exposed_functions` | about 30 functions, bound to `Document`, `Entity` and the `Create`/`Update` bases by `ModelRegistry._bind_database_functions` (`model_registry.py:448`) | binding is by assignment; the functions bind to `Database.default` at import time (review finding 5) |
| `setup`, `migration_backend` | imported by name from the API and CLI | optional parts (backups) are found with `hasattr`; [neo4j-implementation.md §3](neo4j-implementation.md#3-the-contract-a-backend-must-meet) lists the contract by hand |
| `pangloss_core.backend` | a `Protocol` for what the add-ons need (`Database`, `Transaction`, `lock`, …) | the one part that is already typed; it is Cypher-specific by nature (add-ons run their own queries) |
| `pangloss-neo4j/tests/test_contract.py` | checks that both backends export the same names and signatures | checks names, not behaviour |
| the copied test suites | the actual specification | 261 raw-Cypher calls in 25 of the 51 memgraph test files: the tests reach under the contract |

The model layer is already neutral, which is what makes this feasible:

- `_meta.fields`, the `CreateDB`/`UpdateDB` instances, and the migration `changes` describe data without any
  database;
- `pangloss_models.search.check_match` produces a neutral condition tree that the backend's `Compiler` turns into
  Cypher;
- `build_tree` (identical in both backends) builds a document from a root, its labels and a list of edges, which is a
  neutral shape.

## 2. Levels at which to abstract, and the choice

| Level | What it means | Verdict |
|---|---|---|
| **Driver** ("any Bolt database") | share everything, swap the URL | Already false: the backends differ in DDL, text search, property types and isolation ([§3](#3-what-actually-differs-measured)). |
| **Query** (a Cypher AST or builder with dialect renderers) | build queries as objects and render them per database | A large framework for about a dozen differences. It hides the query text, which the performance work depends on (the plan cache keys on text; query shapes are chosen for each planner, see `docs/backend-profiling.md`). It is no use for SPARQL. **No.** |
| **Operation** (a storage port) | an interface of domain operations; each backend implements it however it likes | **Yes, as the outer layer.** It is the only level that admits a non-Cypher backend, and it is what callers use today. |
| **Difference point** (a dialect inside a shared Cypher implementation) | one Cypher implementation that calls named hooks where backends differ, or swaps a whole query | **Yes, as the inner layer, for Cypher backends only.** It matches the measured diffs. |

## 3. What actually differs (measured)

I diffed the two packages with the backend names normalised. These are the differences that exist, which is what the
`Dialect` has to cover. Everything else is identical text.

| Difference | Memgraph | Neo4j | Where |
|---|---|---|---|
| Tree traversal | `-[*BFS (e, n \| …)]->` | quantified path pattern (`traversal.below`) | update, read, delete, migrations |
| Property encoding | maps stored as maps | maps flattened to `meta.created_by`, lists of maps as `name#json` (`properties.py`, 182 lines); results decoded (`DecodedResult`) | every write, every read, every query that reaches into `meta` |
| Label as a parameter | `MATCH (n:$t)` | `MATCH (n:$($t))` | list, migrations |
| Text search | `text_search.regex_search("label_text", ".*w.*")` | `db.index.fulltext.queryNodes(...)`, with words folded and escaped (`schema.py`) | list, deep list, autocomplete, truncation |
| Facets | `collect(k, v)` | a list of `{type, nodes}`, made into a map in Python | list |
| Tie-break ordering | `id(n)` | `n.id` / `elementId(n)` | list |
| Error classification | timeout = `TransientError` with "timeout"; unique = `ClientError` with "unique constraint" | timeout = `ClientError` `TransactionTimedOut`; unique = `ConstraintError` | database, exposed functions, users |
| Isolation | snapshot isolation: concurrent writes conflict at commit and the driver retries | read committed: updates take a node lock first (`lock_node`); a check may see a write committed meanwhile, so conflicts are retried too | `replace_head_node`, `write_with_retries` |
| Index hints in patterns | `(:Entity {id})` | `(:PGIndexableNode:Entity {id})` | `validate_write.replace_urls` |
| DDL and schema reading | `CREATE INDEX ON :L(p)`, `SHOW INDEX INFO` | named `CREATE … IF NOT EXISTS`; constraints before indexes; `SHOW INDEXES` | initialise, migrations, CLI |
| Bulk load | analytical storage mode; constraints dropped and restored | batched `UNWIND` in normal transactions | `bulk.py` |
| Snapshots | `CREATE SNAPSHOT` | none in Community | migration backend (optional) |

These differences fall into three kinds, and the design gives each kind its own mechanism:

- **Fragments** inside an otherwise shared query: traversal, label parameter, text-search call, tie-break, index
  hints. These are dialect methods that return Cypher text.
- **Codecs** around a query: property encoding and decoding, facets, error classification. These are dialect methods
  that wrap parameters, results or exceptions.
- **Whole subsystems**: DDL, bulk load, snapshots, isolation strategy. These stay in each backend package, behind the
  port's capabilities or the dialect's hooks.

## 4. Layer 1: the storage port

### 4.1 Where it lives

The port's signatures use model types (`_DocumentCreateDBBase`, `HeadView`, `Match`, the migration `Change`s). So the
port lives in **`pangloss-models`** (`pangloss_models.storage`), not in `pangloss-core`, which must not depend on the
models. `pangloss_core.backend` stays as it is, as the Cypher-level protocol for add-ons ([§6](#6-add-ons)).

### 4.2 Shape

```python
class Storage(Protocol):
    capabilities: Capabilities

    # lifecycle (see the review's answer on explicit binding)
    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def initialise(self) -> SetupReport: ...               # indexes, constraints, text index

    # documents and entities
    async def create_head(self, item: CreateDB, *, review_status: str | None) -> WriteResult: ...
    async def replace_head(self, item: UpdateDB, *, expected_version: int | None,
                           review_status: str | None) -> WriteResult: ...
    async def read_head(self, cls: type, id: UUID | AnyHttpUrl, *, incoming: bool) -> HeadRecord | None: ...
    async def delete(self, cls: type, id: UUID | AnyHttpUrl) -> DeletionResult: ...
    async def undelete(self, cls: type, id: UUID | AnyHttpUrl) -> tuple[UUID, int]: ...

    # finding
    async def list(self, cls: type, query: ListQuery) -> Page: ...
    async def search(self, cls: type, conditions: CheckedConditions, page: PageRequest,
                     order: CheckedOrder) -> Page: ...
    async def autocomplete(self, cls: type, words: list[str], types: list[type], page: PageRequest) -> Page: ...

    # users, tokens, sessions; review
    users: UserStore
    review: ReviewStore

    # migrations
    migrations: MigrationStore
```

Requirements:

1. **Neutral values in and out.** Arguments are model instances and plain values. Results are dicts or Pangloss
   dataclasses (`WriteResult`, `HeadRecord`, `Page`), never driver records. Turning these into `HeadView` and
   `ReferenceView` objects, and firing `announce` for write events, moves **above** the port into `pangloss-models`,
   because those steps are the same for every backend. Today they sit inside `exposed_functions`, duplicated.
2. **Pangloss exceptions only.** No `neo4j.exceptions.*` escapes the port. Timeout becomes
   `PanglossSearchTimeoutError`, a uniqueness race becomes `PanglossConflictError` after retries, and an unknown failure
   becomes `PanglossStorageError` with the cause chained. Today `write_with_retries` matches on driver exception
   strings. That matching belongs to the dialect, and the retry policy to the port.
3. **Capabilities, not `hasattr`.** Optional features are declared:

   ```python
   @dataclass(frozen=True)
   class Capabilities:
       snapshots: bool            # migrate --backup, restore
       fast_bulk_load: bool       # an offline/analytical mode
       accent_folding: bool       # "zurich" finds "Zürich"
       deep_search: bool
       cypher: bool               # add-ons that run their own Cypher may be installed
   ```

   The CLI and the API ask `storage.capabilities.snapshots`, not `hasattr(migration_backend, "backup")`. An add-on
   declares that it needs `cypher` and fails at start-up with a clear message on a backend without it.
4. **An explicit instance.** `storage = await connect(settings)` returns the backend object. `ModelRegistry` binds the
   model methods to **that object** (`Document.get = lambda cls, id: storage.read_head(...)`, or better, model methods
   that call `storage_of()` when they run). It no longer imports `exposed_functions`. This replaces `DATABASE_MODULE`
   with a factory (`STORAGE = "pangloss_memgraph:MemgraphStorage"`), which can be kept as an alias for a while.

### 4.3 The semantic contract

This is the part that makes the layer real, and the part with no code today. Each rule below is currently enforced
only by Cypher text, and repeated in each backend. Each must be **written down** (in `docs/storage-contract.md`) and
**tested by the conformance suite**:

| Rule | Today |
|---|---|
| A deleted head hides itself and everything nested in it; a nested node is never deleted alone | `deleted` filters pasted into list, read, search and autocomplete (8 copies in `build_list_query.py` alone) |
| An unpublished document is invisible unless `unpublished_visible()`; entities are always published | the same pasted filters |
| The version is 1 + the number of updates | `VERSION_OF_HEAD` (counts `PGUpdate`) |
| `meta.created_*` comes from the creation record; an update keeps the `created_*` of nested nodes it rewrites | `get_tree_meta` and `previous_meta` |
| An update replaces the head's tree but never touches entities, their URLs, or edges that other heads own | `TREE_TRAVERSAL` and `build_replace_head_query` |
| `published` and the review fields survive an update | `KEPT_PROPERTIES` |
| A URL belongs to at most one entity, deleted or not | the `PGUrl` nodes and their constraint |
| An inline entity that exists is linked to, not rewritten; one that is the wrong type is a conflict | `find_existing_entities` and `check_inline_entities` |
| Two updates from one version: exactly one succeeds | `expected_version` with the backend's isolation strategy |
| Writes are refused while a migration holds the lock | `refuse_while_migrating` |

How the data is stored (`PGCreation` nodes, reverse edges marked `reverse: true`, `PGUrl` nodes) is **not** part of the
port contract. It is part of the Cypher kit's own storage format, which the migrations depend on.

## 5. Layer 2: the Cypher kit

### 5.1 Package layout

```
pangloss-cypher/               (new; depends on pangloss-models, neo4j driver)
  storage.py                   CypherStorage(Storage): the port, implemented once
  dialect.py                   the Dialect protocol
  write_plan.py                neutral plan of a write (see 5.3)
  render_write.py              WritePlan -> Cypher, through the dialect
  read.py, tree.py             read query + build_tree
  list.py, search.py           with a shared visible(node, head) fragment
  delete.py, validate.py, users.py, review.py, lookup.py, incoming.py
  transactions.py              read/write decorators, logging, timeouts, migration refusal
  migrations/operations.py     the ~70 data operations, through the dialect
pangloss-memgraph/
  dialect.py                   MemgraphDialect
  ddl.py, bulk.py, snapshots.py, cli.py, shipped migrations
pangloss-neo4j/
  dialect.py, properties.py, schema.py (folding), ddl.py, bulk.py, cli.py, shipped migrations
```

### 5.2 The Dialect

```python
class Dialect(Protocol):
    name: str

    # fragments (return Cypher text; must be stable text, for the plan cache)
    def tree_below(self, start: str, end: str) -> str: ...          # the BFS walk that skips entities and reverse edges
    def label_param(self, param: str) -> str: ...                   # ':$t' or ':$($t)'
    def text_search(self, index: str, pattern_param: str, limit_param: str,
                    node: str, score: str) -> str: ...
    def search_patterns(self, text: str) -> list[str]: ...          # escaping/folding: the whole input rule
    def tie_break(self, node: str) -> str: ...
    def entity_by_id(self, var: str, id_param: str) -> str: ...     # where index hints differ

    # codecs
    def encode_properties(self, props: dict) -> dict: ...           # identity / flatten
    def decode(self, value: Any) -> Any: ...                        # identity / unflatten
    def meta_expr(self, node: str) -> str: ...                      # 'n.meta' / the flat map
    def facets_from(self, raw: Any) -> dict: ...

    # errors and concurrency
    def is_timeout(self, error: Exception) -> bool: ...
    def is_unique_violation(self, error: Exception) -> bool: ...
    async def before_replace(self, tx, head_id: str) -> None: ...   # no-op / take the node lock
    retry_on_check_conflict: bool                                   # read committed: a failed check may be a lost race

    # whole-query override (escape hatch)
    def query(self, name: str, default: str) -> str: ...
```

The **override hatch** matters. Some queries are tuned to one planner (the memory notes on EXISTS scans, the plan
cache, picking the start node). The kit names each of its queries (`"list.plain"`, `"read.document"`, …). A dialect may
replace one query entirely, so long as it takes the same parameters and returns the same columns. This keeps the
performance work possible without forking a module.

### 5.3 Separate planning a write from rendering it

`build_create_query.py` (795 lines, 5 lines different between backends) does two jobs in one pass:

- **planning**: which nodes, edges, references, URLs and inline entities a document produces. This is the same for any
  database. `QueryObject.references`, `nodes_to_write`, `urls_to_write` and `inline_entities` are this plan.
- **rendering**: the `MATCH`/`CREATE`/`SET` text.

Split them. `write_plan.py` turns a `CreateDB`/`UpdateDB` instance into a `WritePlan` (nodes with labels and
properties, edges with forward and reverse names and properties, references to check, URLs, inline entities).
`render_write.py` turns the plan into Cypher through the dialect. The validators (`check_references_exist`,
`check_ids_available`, …) read the plan, not the query object.

This is the most valuable single refactor:

- the planner can be unit-tested without a database;
- the plan is exactly what an RDF backend would render into SPARQL Update, which the feasibility doc names as the
  largest piece of new work;
- the bulk loader can render many plans into one `UNWIND`.

The read path already has this split: `build_tree` takes nodes and edges. Make that the documented read interface
(`GraphFragment`) and the symmetry is complete.

### 5.4 One visibility fragment

`visible(node: str, head: str) -> str` returns the four-line filter (deleted, published, the `$published` and
`$review_status` filters). Every list, read, search and autocomplete query uses it. This deletes the copies the review
found and enforces the visibility rules of [§4.3](#43-the-semantic-contract) in one place, which the next
"`published`-like" property ([review.md](review.md) lists the current places by hand) will need.

## 6. Add-ons

`pangloss-typology` and `pangloss-calendar` write their own Cypher (28 `tx.run` calls between them) through
`pangloss_core.backend`. That is fine and should stay, as a **declared** dependency:

- an add-on that runs Cypher requires `capabilities.cypher`, checked at start-up;
- it gets `backend.current()` from the kit, which supplies `Database`, `Transaction`, `lock`, and (new)
  `dialect`, so it can use `dialect.label_param`, `dialect.tree_below` and so on instead of rediscovering the
  differences (the `labels(a)[0]` ordering bug found on Neo4j);
- its live tests already run on both backends (`PANGLOSS_TEST_BACKEND`).

Making the add-ons portable to a non-Cypher backend would mean giving each one an operation-level port of its own, as
users and review have. Do that only if a non-Cypher backend becomes real.

## 7. Layer 3: the conformance suite

The copied suites are the specification today. Turning them into one suite is about half the total work, because 25 of
the 51 memgraph test files check the database with raw Cypher (261 call sites: `run(db_driver, …)`, `count_nodes`,
`labels_of`).

What is needed:

1. **`pangloss_testing.conformance`**: test modules that take a `storage` fixture and use only the port (and the
   models above it). Each backend package's `conftest` provides the fixture and runs the suite (`pytest --pyargs
   pangloss_testing.conformance`).
2. **An inspection interface for the checks that must look underneath:**

   ```python
   class Inspect(Protocol):
       def count(self, kind: str) -> int: ...            # "Person", "PGUpdate", "PGUrl"
       def labels_of(self, id: UUID) -> set[str]: ...
       def edges(self, from_id, name, to_id) -> list[dict]: ...   # properties, incl. reverse
       def raw(self, query: str, **params) -> list[dict]: ...      # backend-specific escape hatch
   ```

   Most of the 261 raw calls are one of the first three. The Cypher kit supplies one implementation, using the dialect
   for flattened properties. Tests that need `raw` are marked with the backend they need, and are the honest list of
   what is backend-specific.
3. **What stays per backend:** DDL and schema reading, bulk load modes, snapshots, query-plan assertions
   (`test_model_indexes_live.py`), and the dialect's own unit tests (escaping, folding, error classification). This is
   roughly what `pangloss-neo4j/tests/NOT_PORTED.md` already lists.
4. **Rules for the suite**, from the review:
   - clear the database on setup as well as teardown;
   - no `except Exception` that turns test bugs into reported failures;
   - every concurrency test is checked to fail with its mechanism removed (`test_lock` passed with the lock removed).

## 8. How to get there

Each step leaves `run_tests.sh` passing, and each is worth having even if the later steps never happen.

| Step | What | Size (estimate) | Unlocks |
|---|---|---|---|
| 0 | Review prerequisites in both backends: call-time database binding; error translation in `transactions`; delete the redundant timeout handlers | 2 days | a stable base |
| 1 | **Create `pangloss-cypher` and move the identical files there unchanged**: `delete_node`, `read_incoming`, `review`, `users`, `lookup`, `build_tree`, `from_database`, `visibility` (about 1,040 lines, 0 differences). Both backends import them. | 1 day | fixes made once from here on |
| 2 | Add the `Dialect` with the fragment and codec methods of §5.2, and move the near-identical files through it: `build_create_query` (5 lines differ), `validate_write` (6), `build_update_query` (12) | 3–4 days | the write path shared |
| 3 | Split `WritePlan` from rendering (§5.3); validators read the plan; planner unit tests without a database | 1 week | testable planning; RDF and bulk reuse |
| 4 | Move read, list, search and autocomplete into the kit with `visible()` and the query-override hatch; the facet and tie-break codecs | 1 week | the 8 pasted filters become 1 |
| 5 | Define `Storage` and `Capabilities` in `pangloss-models`; `CypherStorage` implements it; models bind to the instance; `announce` and view-building move above the port; `DATABASE_MODULE` becomes an alias | 1 week | a real typed interface |
| 6 | Conformance suite and `Inspect`; move tests file by file and delete each copy as it moves | 1–2 weeks, can run in parallel with 4–5 | one specification |
| 7 | Migration operations (2,434 lines) through the dialect | 1 week | the last large duplicate |

After step 2, most of the drift risk is gone. After step 5, a third backend is "write a dialect, DDL and bulk load" for
a Cypher database, or "implement `Storage`, reusing `WritePlan`, `build_tree` and the conformance suite" for anything
else.

## 9. Risks

- **Performance regressions from shared queries.** One query text has to suit two planners. Mitigation: the override
  hatch, and running the large-data measurements (`docs/large-data.md`, the :7689 scratch database) before and after
  steps 4 and 7.
- **Plan-cache stability.** Fragments must produce the same text for queries of the same shape. `QueryParams` already
  ensures this for parameter names; dialect fragments must not include anything that varies (no random names).
  `test_a_write_of_the_same_shape_is_the_same_query_text` has to move into the conformance suite.
- **The isolation difference is semantic, not syntactic.** The retry-on-check-conflict behaviour of Neo4j's copy
  (`exposed_functions.py` in pangloss-neo4j, around line 487) must be explicit in the dialect, and covered by a
  concurrency test that runs on both backends.
- **Over-abstracting.** Do not add dialect methods in advance. Add one only when a diff shows a difference. If a dialect
  starts to hold whole query modules, that part was not shared after all, and should go back to the backend.
- **Effort against features.** This competes with feature work for 4 to 6 weeks. Steps 1 and 2 give most of the value
  in about a week. The later steps can wait until a third backend or a non-Cypher store is actually wanted.

## 10. Decisions for you

**Answered 2026-10-31** (see [database-abstraction-plan.md §1](database-abstraction-plan.md#1-decisions)):

1. RDF is not an immediate goal, but will be considered, so the port is deferred and its seams are kept.
2. `pangloss-cypher`.
3. Deferred with the port.
4. Yes, fold on both backends.

The plan also covers what this doc missed: typology writes model relations around the model write path, and the
add-ons hold two more copies of the visibility rule. See
[database-abstraction-plan.md §2](database-abstraction-plan.md#2-cypher-outside-the-backends).

The original questions:

1. **Is a non-Cypher backend (RDF) a real goal?** If yes, do step 5 (the port) early and design `WritePlan` with
   SPARQL in mind. If no, steps 1 to 4 and 6 are enough, and the port can stay as an informal module contract.
   *Recommendation: do steps 1 to 3 regardless; decide on the port after.*
2. **Package name:** `pangloss-cypher` (what it is) or `pangloss-graph-common` (the name in neo4j-implementation.md).
   *Recommendation: `pangloss-cypher`.*
3. **`DATABASE_MODULE` → `STORAGE` factory**, with an alias kept for how long?
4. **Accent folding:** make it a dialect concern (Memgraph's `label_folded` property, see neo4j-implementation.md)
   so that both backends answer `zurich` the same, or keep it as a declared capability difference?
