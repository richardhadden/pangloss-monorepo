# How Pangloss is put together

The layers, how data is stored, what a backend is, how an optional package attaches, and what to know before writing
Cypher. The reference is `implementation_docs/packages.md`, `implementation_docs/generated-models.md`, `implementation_docs/memgraph.md`,
`implementation_docs/database-abstraction.md` (as built) and `implementation_docs/backend-neutral-addons.md`.

## Contents

- The layers
- From a class to stored data
- How data is stored
- Storage backends
- The API
- An optional package (an "app"): how it attaches
- Writing an add-on that reads the graph
- Writing Cypher: what has been learned
- The SDK

## The layers

```
pangloss-core            settings, logging, the Storage object, the backend loader
   ▲
pangloss-models          base classes, initialise(), generated models, export, search patterns,
   ▲                     migration planner, hooks, meta slots. Knows no database
   │
pangloss-cypher          storage for Cypher databases, written once; asks a Dialect where they differ
   ▲
pangloss-memgraph / pangloss-neo4j      dialect, connection, DDL, bulk load, CLI

pangloss-users ─► core            pangloss-api, pangloss-cli ─► core, models, users
pangloss-sdk ─► models, core      (no database driver, no web framework)
optional apps ─► models, core     (and the backend only through pangloss_core.backend)
```

Dependencies point down. Keep them so: `pangloss-core` must not import the models; `pangloss-models` must not import a
backend, the API or an optional package; the API and CLI know no particular database; an add-on names no backend. A
client of the API installs only the SDK's side: no `neo4j`, no FastAPI.

## From a class to stored data

`pangloss_models.initialise()` is `ModelRegistry.finalise()`. In order: rebuild the classes so forward references
resolve; sort by dependency; analyse every field into a field definition (errors here are `PanglossModelError`); work
out incoming relations; make the reference models, then `Create`/`CreateDB`, `Update`/`UpdateDB`, `View`, `HeadView`
(and `EditView`), then `Where`; rebuild; then **bind the database**: the functions of the backend's `operations`
module are assigned to `Document.get`, `.list`, `.delete`, `Create.save` and the rest. The pipeline is in
`implementation_docs/generated-models.md`.

A write: user data → `Statement.Create` (validated) → `_to_db_model()` → `Statement.CreateDB` (ids, labels, semantic
the path of each node, with its semantic spaces, filled in: `pangloss_models.context`) → a `WritePlan` (`pangloss_cypher.write_plan`: nodes, relations, references; no
Cypher yet) → a few Cypher statements, each over a list of rows (`render_write`: the head, the nodes, the edges) → the
database → a `ReferenceView` or `HeadView`.

An update, in one transaction: check the document exists, that what it refers to exists, that the ids it uses are
free, and that it is based on the latest version; only then delete everything below the head (never entities) and
write the new tree. A failed update changes nothing.

A read: one query walks out from the head node, the paths are made into a tree (`build_tree`), `meta` is added, and the
result is validated as the `HeadView`. An entity's view also has what refers to it (`read_incoming`), all of it by
default: the query finds the rows, drops what the models do not show, sorts, counts and cuts **before** reading any
properties (reading them is what costs). `?incoming_limit=` and `GET /api/NAME/{id}/incoming/{field}` read some of it
(`operations.get_entity_with_some`, `get_incoming`: for the API, not bound to the models).

Tests reset the registry before each test (`ModelRegistry._reset()`), so classes declared inside a test do not leak.
Do the same in a scratch script that declares classes twice.

## How data is stored

| In the graph | Meaning |
|---|---|
| Node labels | The class, each parent class, heritable traits, the kind (`Document`, `Entity`, …); `PGIndexableNode` on everything; `HeadNode` on the top-level node |
| Node properties | `id` (a UUID7), `type`, `label`, the literal fields that are not `None`, `meta`; on nodes below the head, `head_node_id` and `head_node_type` |
| `meta` | Stored: who made it and when; on a node below a head, `path` (the nodes it is nested in, from the head down, each `{kind, type, id, field}`: `pangloss_models.context`), and `semantic_spaces` (the types of the path's spaces, what a query filters by); Neo4j cannot hold a map as a property, so its dialect flattens `meta`, and keeps the path as JSON text (`meta.path#json`). A read adds `updated_by`/`updated_when` and `version` from the update records: the version is 1, and 1 more for each update |
| A relation | `(a)-[:field]->(b)` and `(a)<-[:reverse_name {reverse: true}]-(b)`; edge properties on both |
| An embedded object | A node, joined like a relation |
| An annotated value | A map property on its node |
| `PGCreation`, `PGUpdate`, `PGDeletion`, `PGUndeletion` | Records of who did what and when, linked to the head node and to a `PGUser` |
| `PGUrl` | A URL of an entity, as a node so that it can be unique |
| `deleted: true`, `marked_for_deletion`, `published` | The flags that hide a node, or mark it |
| `computed: true` (and `seen_by`) on an edge; `pg_computed_basis` on a node | The pair of edges of a relation the server computes (`Computed()`), and the hash of what a node with computed fields says, by which an update keeps them |
| `merged_into` (on an entity), `PGMerge`, `PGMergeMove` | An entity merged into another (a property, not an edge), the record of the merge, and of each edge it moved (`pangloss_cypher.merge`, `implementation_docs/entity-identity.md`) |

The acting user is a context variable (`current_request_username` in `pangloss_users`); a write as a user who does not
exist or is disabled is refused. The text index is on `label` of `PGIndexableNode`. Details: `implementation_docs/memgraph.md`,
"Graph schema".

## Storage backends

`STORAGE = "module:attribute"` names a `pangloss_core.storage.Storage`: a name, `capabilities` (`snapshots`,
`fast_bulk_load`, `accent_folding`, `deep_search`, `cypher`, `vector_index` (Memgraph and Neo4j), `query_modules`
(Memgraph)) and the module whose parts are the backend:

| Part | Is |
|---|---|
| `exposed_functions` (`Storage.operations`) | The functions the models are bound to. For both Cypher backends this is `pangloss_cypher.operations`, re-exported |
| `setup` | `create_database(settings)`, `connect`, `disconnect`, `setup_database`: what the CLI and server need |
| `migration_backend` | Applies the changes the planner in `pangloss_models.migrations` finds |
| `backend` | What an add-on that runs its own Cypher may use (`pangloss_core.backend.Backend`) |

Decisions that stand (`implementation_docs/database-abstraction.md`, §1):

- The shared code is in `pangloss-cypher`. A backend package is its `Dialect` (`dialect.py`), connection, DDL, bulk
  load, snapshots and CLI. If you find yourself writing the same query in both backends, it belongs in the kit (the record of migrations, its lock, `apply` and `unapply` are `pangloss_cypher.migrations.record`, which each backend's `migration_backend` names; `tests/test_no_copies.py` of the kit fails on a copy).
- A difference between the databases is a **named method of the `Dialect`** (`pangloss_cypher.dialect`): a fragment of
  Cypher (tree traversal, text search, tie-break), a codec (encoding properties, classifying errors), or a whole query
  swapped by name (`Dialect.query`). Not an `if backend == ...`, and not a query builder.
- Driver exceptions do not leave the kit: a timeout is `PanglossSearchTimeoutError`, a clash of ids is a
  `PanglossConflictError`, and so on (`pangloss_models.exceptions`).
- A fully typed, non-Cypher `Storage` port (for an RDF backend) is deferred, not rejected; the seams it needs are
  kept (a neutral write plan, a neutral read shape, a conformance suite that goes through the models).
- `DATABASE_MODULE` is the old name of `STORAGE`; it is still read, with a warning. Do not use it in new code or docs.

What the databases differ in (isolation, map properties, label order, full-text search, DDL) is listed in
`implementation_docs/neo4j-implementation.md` and measured in `implementation_docs/backend-comparison.md`.

**The conformance suite** (`packages/pangloss-testing/src/pangloss_testing/conformance/`) is the specification: it
goes through the models and the API and runs on each backend (`PANGLOSS_TEST_BACKEND=neo4j`). Storage behaviour is
tested there. A backend's own `tests/` are for what only it has.

## The API

`pangloss_api.app:create_app` builds a FastAPI application from the initialised models:

- For every Document and Entity `NAME` (the class name): `GET /api/NAME` (list, `q`, `deep`, pages),
  `GET /api/NAME/{id}`, `POST /api/NAME`, `GET /api/NAME/{id}/edit`, `PUT /api/NAME/{id}` (needs `If-Match`),
  `DELETE`, `/undelete`, `/deletable`. An abstract class has only the reads. A read at a parent class answers as the
  subclass, with `Content-Location`.
- `POST /api/NAME/with-companions` (an entity with companions): it and its companion documents in one transaction,
  through `pangloss_models.create_heads`, which writes several heads in order, each able to refer to those before.
- Merging two entities (`pangloss_api/routes/merges.py`): `POST /api/NAME/{id}/merge` (and `/merge/preview`,
  `/merge/propose`), `GET /api/merges`, `POST /api/merges/{merge}/verify|reject|undo`. Who merges alone is the
  setting `MERGE_DIRECTLY` (admins by default); everyone else proposes and a different user verifies, a rule the
  storage enforces. A write addressed to a merged entity is 409; one that names it is written with the survivor and
  says so in `Pangloss-Resolved-References`. `pangloss merge`, `unmerge`, `merges` and `check-data --move-merged`
  do the same from the command line.
- `POST /api/search`, `GET /api/autocomplete`, and the user, session and token routes under `/api/users`.
- Reading needs no login; every change needs a logged-in user. Finer permissions are not built (an open decision in
  `TODO.md`): do not invent a permission model in passing.
- Errors carry `detail` and `error` (the exception's class name), which the SDK raises again as the same exception.
- Query parameters are read in either case (`pageSize` is `page_size`) and one a route does not have is a 422
  (`pangloss_api/query.py`). An app's route that reads parameters it does not declare is marked
  `@checks_own_parameters` and calls `refuse_unknown_parameters(request, also=...)`; a middleware that reads a
  parameter of its own takes it out of the query string (as `pangloss_review` does with `review_status` on a write).
- A 422 for a body is FastAPI's list, cleaned (`pangloss_api/validation.py`): `loc` is the path in what was sent,
  the union member it was read as is in `model`, and a long `input` is left out. Do not rely on Pydantic's own `loc`.
- The server will not start with migrations pending, or with an app whose `requires` the backend does not meet. A
  server that is running when `pangloss migrate` is applied notices (`pangloss_api/migration_watch.py`,
  `MIGRATION_WATCH_SECONDS`) and answers 503 to everything until it is restarted.

Full table and status codes: `implementation_docs/api.md`.

## An optional package (an "app"): how it attaches

An app is a Python package named in `INSTALLED_APPS`: a library (`pangloss_review`) or the project's own
(`demo_app`). It is found by the names of its modules. All are optional:

| In the app | Found by | Does |
|---|---|---|
| `models.py` | CLI, server | Declares models, imported before `initialise()` |
| `migrations/` | `makemigrations`, `migrate` | Its migrations (a library ships its own) |
| `api.py` with `router` | the API | Routes, under the prefix the router gives |
| `api.py` with `configure_app(app, settings)` | the API | Middleware; `app.state.startup_hooks`; `app.state.background_tasks` (a `BackgroundTask(name, run)` kept running, restarted with backoff) |
| `cli.py` with `cli` (a `typer.Typer`) | the CLI | `pangloss <name> …` |
| `interface/` | `pangloss interface …` | An interface module: a Solid library with a manifest (see the interface reference) |
| `interface_config.py` with `config` | the interface | Navigation links and sections; `disabled=[...]` turns off what a module adds |
| `translations/models.jsonc`, `translations/ui.jsonc` | the translation commands | Words for its models and for its own interface |
| `derived.py` | `pangloss_derived` | Rules that derive relations |
| `admin.py` with `jobs` (`JobKind`s) | `pangloss_admin` | Long-running jobs started from `/admin`, each in a process of its own (`implementation_docs/admin.md`). Work too heavy for the server's event loop goes here, not in a `BackgroundTask` |
| `requires = {"cypher"}` in `__init__.py` | CLI and server, at start | What it needs of the backend's capabilities |

The general hooks in the core that packages use, instead of the core knowing about them:

- **Meta slots** (`pangloss_models.meta_slots.register_meta_slot("_x_meta", XMeta)`): a typed, inherited setting on a
  model class. Needed because pydantic turns a bare `_name = value` into a private attribute. See `implementation_docs/meta-slots.md`.
- **`pangloss_models.hooks`**: lists a package appends to. `after_write` (a `WriteEvent` for each committed create,
  update, delete, undelete, merge, unmerge: history records from it); `before_merge` (an app refuses a merge of two
  entities: typology refuses a type with subtypes, Zotero an item of the library as the one absorbed); `new_head_properties` and `updated_head_properties` (review's
  `published`); `pending_work` (work left in the write's own transaction for a background worker: derived, criteria; a kind in
  `pending_keeps_before` has on its mark what an update took away, `pangloss_cypher.pending`; review's index of the
  URIs that parts of documents name, `PGUriClaim`, nodes with no edges so that no read of a document meets them);
  `instructed_work` with `declare_write_instruction` (what one create or update says, `save(instructions={...})` or a
  declared query parameter of the model write routes, decides a kind of pending work for that write: `True` marks,
  `False` takes a standing mark off; asked only by creates and updates of heads, passed down as an argument, never a
  context; may be asked twice for one write, so answer the same and read nothing; an undeclared name or value is a 422,
  `PanglossInstructionError`; reconcile's `suggest`; `implementation_docs/packages.md`, "The instructions of one
  write"); the marks themselves are `pangloss_cypher.pending` (the core's write applies the answers, `unmark` for a `False`;
  reconcile's worker uses `mark_unmarked(again=)`, `claim(before=)`, `renew`, `release` to give claims back,
  `complete`, and `count` for its status);
  `head_view_extras` (what an app adds to a head's view in the API: `_derived`); `from_database` (converting what a
  database returns); `translatable_models`; `migration_changes` (awaited in the transaction of each data change of a migration, with the snapshots before and after: an app rewrites what it keeps that names classes and fields, as `pangloss-criteria` its stored patterns with `migrations.patterns`; safe to run twice, never the code's classes) and `after_migrate` (after `pangloss migrate`, with `complete`: whether the classes now describe the data); a `LiteralCodec` with `migrate` has its stored values brought through each change by history; `stand_ins` (a document, or the use of a generic wrapper with the entity classes as its parameter (`pangloss-criteria`), that a relation takes in the place of an entity:
  review's `Unreconciled`); `resolve_citation` (an app says what is cited in the place of something that cannot
  itself be cited: written as a `PGCitedBasis`, only if the app called `citations.enable_cited_basis()`),
  `citation_marked` (told after a commit of each cited basis marked changed or lost) and `in_write` (awaited in
  the transaction of every write of a head: must be safe to run twice; one that raises refuses the write, as
  `pangloss-derived` refuses a write of a derived document by anyone but its worker); a `ValueError` raised by a `@create_validator` or `@update_validator` refuses the write too, as `PanglossWriteRefused` (a 422 with the path of the part); `not_written_by_people` (a
  class an app alone writes: no `POST`, and `createDirectly: false` in the export); `work_marked` (told when a head
  is marked pending by something that is not a write: a change of review status, or `set_published_in_db`, which
  sets `published` alone on a document of a class that is not reviewed); `references_not_counted` (classes whose
  references to an entity are not uses: derived documents); `unconfirmed` (wrapper classes whose nodes hold a guess no
  person has confirmed: the library's classes of suggestion; the graph part does not walk below one, reconciliation's
  `shared` does not count it; nothing else). `edges_of_no_field` (an app says there are edges between entities that are of no field: the shortcut edges of `pangloss-derived`; see `fragments.model_edge` below). `notices` / `give_notice(tx, Notice)` (something an app says of a document that a person should look at, given in the write's transaction: the core says it of a citation through a lost derivation, `pangloss-derived` of a converted document; review makes it an open comment with a `kind`). `resolved` / `tell_resolved(Resolution)` (a stand-in was resolved through a package's own route: review's `reconcile`, not `in_form`; criteria's `resolve`, once for each place; awaited after the write, outside any transaction, so a listener may write; one that raises is logged; not raised by a form's edit, a restore, the SDK or a toolchain). `confirmed` / `tell_confirmed(Confirmation)` (a toolchain's suggestion confirmed by a person, raised by review for every way of confirming: its route `direct`, the others given the same, those a mention names, and a save of the document that writes it again as an identification, not `direct`; `entities`, the id and class of each entity of the confirmed target, several while alternatives are open; as `resolved`, after the write and outside any transaction; nothing for a suggestion deleted or edited away, a save by a toolchain, or a restore; reconcile's `decisions.confirmed` listens to it and learns from a person's confirmations). `kept_head_properties` (names an update keeps on the head unless it writes them); `class_changed_from()` (read in `in_write`: the class a head was, in an update that changes it).
- **Who made it**: `meta.created_by` is a list of `Creator` (people, then a toolchain with its version and date);
  an admin writes in others' names with `save(created_by=, toolchain=)` (`pangloss_models.creators`,
  `implementation_docs/users.md`).
- **What the server computes** (`Computed()` on a field, `pangloss_models.computed`): an app writes it with
  `operations.set_computed(node_id, values, based_on_version, less=[its own kind of pending work])`, or
  `set_computed_batch` (several in one transaction, and `then(tx)` to complete a worker's claims), never with Cypher
  of its own. No `PGUpdate`, no version, no history; a write event `computed`; the head marked with its other
  pending work. An update keeps what was computed for a node with the same id and the same `pg_computed_basis`
  (`pangloss_cypher.computed`); a delete or a merge of an entity takes the computed edges to it away and marks their
  heads. `implementation_docs/matches-criteria.md`, "As built".
  A search with `exclude_wrappers` also asks `pangloss_models.search.head_conditions` which documents it reads
  nothing inside (derived: one whose `derived_context` names an excluded wrapper).
- **A head written again with a part replaced** (`pangloss_models.rewriting`: `prepare_rewrite` without writing,
  `rewrite`, `replaced_where`, `read_head`; `Missing("head")` when no head of that id is there that the reader may see, or it is deleted, `Missing("part")`
  when the change found nothing in it to change; save options such as
  `instructions=`, `before_write=` passed on): what review's reconciling, criteria's resolve and share and
  reconcile's worker use; use it rather than a copy of read, `editable`, replace, `Update`, save.
- **`operations.search_ids`**: a structured search that gives the count and the first ids by label, as a reader named
  (`see_unpublished=`), without or among given ids: for an app that works with what a pattern finds.
- **`@read_validator`** (`pangloss_models.write_checks`): a class changes the data its `View` is made from (the one
  hook that runs on a read). **`classes_stood_for(model, "T")`**: what a generic's type variable stands for in the use
  a generated model was made for.
- **Fragments** for Cypher over model data (next section).
- **The database's structure** an app needs beside the models: `<app>/structure.py` with `INDEXES` and `CONSTRAINTS`,
  entries as in the snapshot, made by the app's migrations (`AddIndex`), and perhaps functions `indexes()` and
  `constraints()`, called after `initialise()`, for structure that follows the project's models; an entry that names
  an installed app (`"app"`) goes in that app's migrations instead (the vector indexes of `pangloss-vectors` go in the
  project's). Index kinds: `label`, `label+property`, `text`, and `vector` (`name`, one property, `dimension`,
  `metric: "cos"`, `capacity`, `quantization`: `False` turns Neo4j's off, which costs recall;
  `implementation_docs/migrations.md`).
- **Interface manifest hooks**: `components`, `routes`, `collapseRules`, `consoleActions`, `newItemActions`,
  `newItemFields`, `itemSections`, `itemNotices`, `incomingViews`, `partActions`.

When a package needs something that is not there, add a hook of this kind, general enough for a second user, and
document it. The existing packages are the examples: `pangloss-review` is the smallest complete one (a slot, a head
property, routes, commands, an interface module, translations).

## Writing an add-on that reads the graph

Prefer going through the models (as `pangloss-zotero` and `pangloss-history` do). If the package must run Cypher (its
own graph, like the calendar's days, or a query the models cannot express):

- Get everything from `pangloss_core.backend.current()`: `database()` and its `read_transaction` /
  `write_transaction` decorators, `timeout_from_setting`, `unpublished_visible`, `user_exists`, `ensure_lock` and
  `lock`, `fragments`, `dialect` (the backend's `Dialect`: `vector_search(index, k, vector, carry)` gives the clauses
  of a search of a vector index, binding `node` and `score`, the cosine; `vector_cosine(a, b)` the same cosine of two
  vectors as an expression, for an exact scan without an index); where `Capabilities.query_modules` is true
  (Memgraph) also `install_query_module(name, source, ...)`, which is absent elsewhere. Never import a backend package
  outside tests.
- **Do not write your own rule for what a reader may see.** Use `fragments.visible(node)` (the query is given
  `$see_unpublished`), `not_deleted`, `head_of`, and `label(name)` / `field_edge(field)` for names. For what a
  reader looks through (a list, a search, what refers to an entity) use `fragments.listed(node)`, which also leaves
  out an entity merged into another; `visible` is for what a document shows. Copies of the
  visibility rule have gone wrong before.
- **A read that follows an edge that may be computed says `fragments.seen(edge)`** (nothing unless some model has a
  computed relation; otherwise `edge_visible`: an edge may say `seen_by: "logged_in"`). `visible` judges nodes only.
- **A query that counts or moves references says `fragments.asserted(edge)`** (or `fragments.reference(edge)`, which
  is nothing unless some model has a computed relation): the pair of edges of a computed relation is marked
  `computed: true`, is followed by every read, and is no reference.
- **A query that takes any edge between two items, where both can be entities, says `fragments.forward(edge)`**
  (not a reverse edge, and `fragments.model_edge(edge)`: not a shortcut of a derived edge), or `model_edge` alone
  where reverse edges count too. A class of `pangloss-derived` with `DerivedEdge.Meta(shortcut=True)` has an edge of
  its own name from one entity to the other (`derived: true`), which no read may show as a relation and no write
  may move or delete. Queries that follow only reverse edges, walk down a document's tree, or name their fields need
  nothing. Add the read of a new such query to the conformance test `test_shortcut_edges.py`.
- **Do not write model data around `save()`.** A relation of a model changed by raw Cypher gets no `PGUpdate`, no
  version, no write event (so no history), and slips past `expected_version`. If a bulk change is needed, see how
  typology's `move` and `merge` were brought onto the write path (`pangloss_cypher.relink`). An edge written to an
  entity by your own Cypher must go to its survivor if it is merged (`validate_write.survivors_of`): the models'
  writes resolve it themselves.
- `await ensure_lock(key)` **before** opening the transaction that calls `lock(tx, key)`.
- Keep to Cypher both databases run; test on both (`tests/live/`, fixtures from `pangloss_testing.live`). Neo4j keeps
  no order of labels, and has read-committed isolation where Memgraph has snapshot isolation.
- Declare `requires = {"cypher"}`.

## Writing Cypher: what has been learned

All measured; the numbers and query plans are in `implementation_docs/backend-profiling.md`, `implementation_docs/large-data.md`,
`implementation_docs/structured-search.md` and `implementation_docs/deep-search.md`.

- **`WHERE n:A OR n:B` after an `UNWIND` loses rows on Memgraph** when both labels have an index: it is planned
  as a union of two label scans, and the unwound variable is lost to the conditions after it (one id of several is
  found). Use `any(label IN labels(n) WHERE label IN [...])` (`pangloss_review.graph.has_a_label`).
- **Memgraph caches a plan by the query's text, with the statistics of the first run.** A plan made on a small
  database stays. Write a pattern so the planner has no choice of where to start: match from the node you have. A
  test on a near-empty database cannot show a bad plan; profile on the large scratch database.
- **A property lookup whose value comes from another matched variable is not an index lookup** on Memgraph
  (`MATCH (b:L {n: a.n + 1})` scans the label for every row). Compute the values in Python and `UNWIND` them.
- **Begin a pattern comprehension at the node already in hand.** Memgraph plans `[(h:PGIndexableNode)-[e]->(n) | h]`
  (the bound `n` last) as a scan of every node for each row; `[(n)<-[e]-(h:PGIndexableNode) | h]` follows `n`'s edges
  (a merge's query went from 66 s to 47 ms). Tests on small databases do not show it.
- **A label-and-property index does not serve a scan by label alone**; classes of documents and entities have label
  indexes for that. An index for searching a field's values is `Meta(indexes=[...])`, made by a migration.
- **The text index costs per commit, not per node** (a few milliseconds each, and writers queue behind it). The lever
  for write throughput is more nodes per transaction; a bulk load into an empty Memgraph uses analytical mode.
- **A transaction timeout arrives as a transient error, which the driver retries** for many seconds. It is translated
  to `PanglossSearchTimeoutError` inside the transaction function for that reason; keep new timeouts there too.
- `toLower(prop) CONTAINS` never uses an index; regular expressions over the text index are slow on common words.
- **A statement's cost grows much faster than its length** (about the cube of the number of clauses, on both
  databases): one with a clause for each of 3,000 nodes and edges took 27 seconds. Put what varies in rows
  (`UNWIND $rows`), so the text is short and the same each time. Labels can come from a row (`Dialect.labels_from`);
  the type of an edge cannot, so `render_write` has a `FOREACH` for each pair of names.
- **The text index keeps no word of 40 bytes or more** (Memgraph), and gives 1,000 hits unless asked for more
  (`{limit: ...}`): pass `SEARCH_HIT_LIMIT` wherever the label index is searched.
- **Memgraph tests a pattern from the variable of a list predicate wrongly, silently**: a pattern comprehension
  (`any(j IN … WHERE all(h IN [(j)-->(h) | h] …))`: build the inner list inside the outer comprehension), and an
  `EXISTS { MATCH (nd)-… }` or `exists(pattern)` inside `any(nd IN [nodes(p)[i]] WHERE …)`: name the node by `UNWIND`
  in a subquery instead (`Compiler.step_with_relations`; `implementation_docs/memgraph.md`, "Known rough edges").
- Memgraph must be started with `--storage-properties-on-edges=true` and have the `text_search` module (the
  `memgraph-mage` image has it).

## The SDK

`pangloss sdk build` (with `pangloss_sdk_server` installed) packages the project's models and stubs; the server hands
the package out. In a script, `sdk.connect(url)` sets `STORAGE` to a backend whose operations are HTTP requests, so
`Person.get(...)` and `Factoid.Create(...).save()` are the same code as on the server. What follows from that:

- The models must be importable without the server's dependencies. Code that needs the database is `@server_only` or
  lives in a module the models do not import.
- The model tests of `pangloss-models` use the SDK's storage because it needs no connection.
- A new operation on the models needs its SDK side (`packages/pangloss-sdk/src/pangloss_sdk/databases/`) and a contract test.
- A client has no interface and no project settings. Interface names in a shipped module are rewritten to the inert
  `pangloss_sdk.no_interface`; a setting that changes what a model is must be named in
  `pangloss_core.settings.model_settings` (read with `model_setting`), or the SDK's models will differ from the
  server's and the build's check will fail. A framework package that declares models must import on a client: no
  server package at module level.
- The packages ship stubs of their own model modules. After changing a model of a package:
  `uv run python -m pangloss_testing.framework_stubs` (`run_tests.sh` runs its `--check`).

Design and phases: `implementation_docs/sdk.md`. Using it: `guide/sdk/README.md`.
