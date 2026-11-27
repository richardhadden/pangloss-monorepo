# Packages

This is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/); each directory under `packages/` is a separate distributable package (`pydantic-meta-kit` is a clone of another repository, outside the workspace). Python 3.15 or newer is required (the models use `lazy from ... import`, PEP 810).

```
pangloss-memgraph / pangloss-neo4j ──► pangloss-models ──► pangloss-core
        └──► pangloss-users ──► pangloss-core

pangloss-sdk ──► pangloss-models, pangloss-core
pangloss-sdk-server ──► pangloss-models, pangloss-core, pangloss-sdk   (builds the SDK; serves it from the API)

pangloss-cli ──► pangloss-core, pangloss-models, pangloss-users
pangloss-api ──► pangloss-core, pangloss-models, pangloss-users

optional apps (INSTALLED_APPS):  pangloss-history, -review, -typology, -calendar, -dates, -zotero, -interface, -sdk-server
test support:                    pangloss-testing (live-database fixtures for either backend; the conformance suite)
```

Arrows show declared dependencies. [The guides](../guide/packages.md) say which guide explains which package. (`pangloss-models` uses `pangloss-sdk` only in its tests, as a database module that needs no connection: a dev dependency.) A client of the API needs only the SDK's side of this: it needs no `neo4j`, FastAPI or Memgraph package.

## pangloss-core ✅ / 🚧

Settings shared by every module: `DatabaseSettings`, `ClientSettings` (only `INSTALLED_APPS` and `STORAGE`, which is all the models read; what a client of the API uses) and the generic `BaseSettings[TDatabaseSettings]` (the server's, which extends it). Constructing a `BaseSettings` stores it in the module global `pangloss_core.settings.SETTINGS`. See [Settings](settings.md).

## pangloss-models ✅ (the main package)

Everything about *declaring* and *initialising* models:

| Path | Purpose |
|------|---------|
| `model_bases/` | The declarable base classes (`Document`, `Entity`, `Embedded`, `Trait`, ...) and the generated-model base classes in `base_models.py` (Create / Update / the `...DB` models / the views), with what they use in `labels.py`, `fulfilment.py`, `binding.py`, `instance_context.py`, `from_database.py` and `model_tools.py` |
| `field_definitions.py` | Dataclasses describing each field after analysis (`LiteralFieldDefinition`, `RelationFieldDefinition`, `FieldBinding`, ...) |
| `initialise_models/` | Field-definition and incoming-relation analysis, and the builder of the generated models (`kinds.py` describes `Create`, `CreateDB`, `Update`, `UpdateDB` and `View`; `builder.py` makes them); see [the pipeline](generated-models.md#the-initialisation-pipeline) |
| `model_registry.py` | `ModelRegistry`: registration, dependency ordering, and the `finalise()` entry point |
| `utils.py` | Type-introspection helpers (parent classes, traits, concrete subclasses, relation detection) |
| `exceptions.py` | `PanglossInitialisationError`, `PanglossModelError`, `PanglossMetaError`, `PanglossImportError`, ... |

Public entry point: `pangloss_models.initialise`, an alias for `ModelRegistry.finalise`.

It contains `pangloss_models.meta_kit`, the `WithMeta[...]` / `BaseMeta` machinery behind `_meta` and `Meta(...)`, vendored from [pydantic-meta-kit](https://github.com/richardhadden/pydantic-meta-kit) (commit `6f8ea9c`; changes are made in `pangloss-models` now). It knows nothing of any database: what a database returns that the models cannot read (Memgraph's date types) is converted by a function the database module adds to `pangloss_models.hooks.from_database`. The function is given each value; the hook walks the data once and marks what it has been through, so that the models nested in a document do not convert their subtree again (a read of a document 60 deep took a second before, 2026-11-07).

### The instructions of one write ✅

What a write itself says about the work that follows it, not stored with what it writes (built for step 10.5b of
[the similarity build plan](similarity-build-plan.md): a save may say whether `pangloss-reconcile`'s worker is to
suggest identifications in it). An app declares each instruction it reads, when its module is imported:
`hooks.declare_write_instruction(hooks.WriteInstruction("suggest", ("true", "false"), "..."))` (snake_case; not
the name of a parameter the write routes already have; the same declaration twice is one, a different one is a
`PanglossModelError`). A write says it as `save(instructions={"suggest": False})` (a `Create` or an `Update`, and
`create_heads`, `save_with_companions` and `checked_create`, which only checks), or over the API as a query
parameter of a create, update or with-companions route (`?suggest=false`; no other route takes one). A `bool` is
`"true"` / `"false"`; a name no app declares or a value not declared is `PanglossInstructionError` (a
`PanglossWriteError`, 422 over the API), raised before anything is written.

An app reads them only where the head is marked pending: a function of `hooks.instructed_work` is given the class and
the write's instructions (an empty mapping if it said none) and answers, by kind of work, `True` (marked, as a kind of
`hooks.pending_work` is) or `False` (a standing mark of that kind taken off, claimed or not, in the write's
transaction: `pangloss_cypher.pending.unmark`; whoever holds the claim then completes nothing); a kind it does not
name is left as it is, and of two functions that answer one kind the later is taken (`hooks.instructed_kinds`). It is
applied after the kinds of `pending_work`. It is asked in the write's transaction, which may be run again, so a
function may be asked twice for one write: it answers the same, quickly, reading and writing nothing. It is asked only
by a create or an update of a head, and, in either, for each entity the write makes, by its class: never by a delete, an undelete,
a merge or its undoing, a relink, a change of review status or publication, a computed write or a derived conversion
(a restore is an update that says none). The instructions are passed down as an argument, not held in a context, so
nothing started from inside a write (a task an `after_write` listener makes) carries them. With no function in
`instructed_work`, a write runs no statement more. An app uses this instead of `pending_work` for a kind that
depends on what the write said. The one there is: `pangloss-reconcile`'s `suggest` (`marking.py`, kind `reconcile`),
which marks a head for its worker, or takes the mark off, by the instruction or else by `RECONCILE_SUGGEST_ON_SAVE`.
Tests: `pangloss_testing/conformance/test_write_instructions_live.py`,
`test_write_instructions_sdk.py`; `pangloss-api/tests/test_write_instruction_routes.py`.

### A head written again with a part replaced ✅

`pangloss_models.rewriting`: what reconciling a mention (`pangloss_review.reconcile.rewrite_part`), resolving a
description and sharing criteria (`pangloss_criteria.resolving.resolve`, `sharing.share`) each did, once.
`replaced_where(value, chosen, replace)` and `replaced(value, id, replace)` change a copy of what an `Update` takes;
`prepare_rewrite(model, head_id, change)` reads the head (an entity as it is edited, a document as it is read),
applies `change(data) -> (data, found)` to `editable(view.model_dump())` and makes the `Update`, writing nothing: it
gives `Prepared(view, update, version)`, or `Missing("head")` / `Missing("part")`, and lets a pydantic
`ValidationError` through for the caller to word. `rewrite(model, head_id, change, *, version=None, **save_options)`
saves the `Update` based on `version` or the version read (`instructions=` among the options). Both take `read=` for
what reads the head.

## pangloss-memgraph ✅ / 🚧

A database backend for [Memgraph](https://memgraph.com/) (using the `neo4j` async driver). It supplies the `exposed_functions` module that `ModelRegistry` binds to `Document.get`, `Document.list`, `Entity.list` and `.save()`. See [Memgraph backend](memgraph.md).

`cli.py` adds `pangloss memgraph <command>` (`info`, `bulk-load`, `bulk-recover`); `databases/memgraph/bulk.py` is the bulk load (`bulk_ingest`: analytical storage mode, for an empty database), and `pangloss_models/bulk_upload.py` reads and writes the file; `databases/memgraph/setup.py` is what the core `pangloss setup-database` calls. 
## pangloss-cli ✅

The `pangloss` command (`pangloss_cli.main`), built with [Typer](https://typer.tiangolo.com/). It finds the project's settings, adds the commands of installed apps, and has the core commands `new-project`, `new-app`, `run`, `dev`, `setup-database` and `users ...`. The templates for new projects and apps are in `pangloss_cli/templates`. It knows nothing about a particular database: it uses the `setup` module of the storage backend (`STORAGE`). See [Command line](cli.md).

## pangloss-api 🚧

The FastAPI application (`pangloss_api.app.create_app`). Done: token and session login (JWT with PyJWT), revocation, personal access tokens, the limit on wrong passwords, the user endpoints, CRUD routes for every Document and Entity, search and autocomplete, background tasks, and the routes and middleware of installed apps (`api.py` with `router` and `configure_app`). Not done: finer permissions. See [REST API](api.md).

## pangloss-interface 🚧

A Python package that holds the JavaScript of the web interface: `interface-core` (a Solid 2.0 component library) and `interface-app` (a server-rendered Solid 2.0 application), with `pangloss interface` commands that wrap Node or Bun, endpoints under `/api/interface`, `InterfaceMeta` and `InterfaceConfig`, interface modules and the translation commands. Reading is built; forms are not. See [The interface](interface.md).

## pangloss-zotero 🚧

Optional: `"pangloss_zotero"` in `INSTALLED_APPS`. Keeps a Zotero library in the database, one way (from Zotero), as entities that are both the sources of factoids and what factoids are about; the watcher runs as a background task of the server. `pangloss zotero sync|watch|status|check`. It also gave the other packages three general things: meta slots and protected fields (`pangloss-models`) and background tasks (`pangloss-api`). See [Zotero](zotero.md) and [Zotero items as sources and subjects](zotero-sources.md).

## pangloss-sdk-server ✅

Optional: `"pangloss_sdk_server"` in `INSTALLED_APPS`. Builds the SDK of the project: `pangloss sdk build|status|show`. It also serves it: `/api/sdk` (manifest, wheel, sdist; `SDK_ACCESS`) and tells a client whether its SDK is current; `git clone` of it (read-only), and a package index (`/api/sdk/simple/`). See [the SDK](sdk.md).

## pangloss-sdk ✅

Lets Pangloss models be used locally and read and write a remote Pangloss instance through its API ("API as database"). Built (see [the SDK](sdk.md) and [the guide](../guide/sdk/README.md)); `sdk-demo/` in the repository shows it used from outside a project.

- `databases/api` (async) and `databases/api_sync` (blocking) are database modules whose functions are requests: set `STORAGE` to `pangloss_sdk.storage:api` or `:api_sync`, or call `pangloss_sdk.connect(url, apps=[...])`.
- `SdkSettings`, login (settings, prompt, tokens kept in memory, or a kept refresh token: `pangloss-sdk login|logout|status`), `pangloss-sdk update` (installs the SDK the server has now, the way it was installed before), `pangloss-sdk sync-stubs` (type stubs for the blocking SDK), the errors the server's database module raises, and `iterate`.
- The model tests use `databases/api` as a database module because it needs no live connection.

## pangloss-admin 🚧

Optional: the page `/admin`, for admins only, and long-running jobs, each in a process of its own. Apps add jobs in an `admin.py` and parts of the page through the manifest's `slots`. See [Admin](admin.md).

## pangloss-rdf 🚧

Optional: an RDF export of every document and entity, a button for it, a full dump, an ontology, SHACL shapes and a JSON-LD context made from the models, and mixins for outside ontologies (CIDOC-CRM ships ready-made). See [RDF export](rdf.md).

## pangloss-review ✅

Optional: documents of the models marked `_review_meta = ReviewMeta(reviewable=True)` are written unpublished, and checked by a user (`unchecked`, `errors_found`, `checked` = published), with comments on the document or a part of it. The core part is the `published` property, which hides a document from requests that are not logged in (like `deleted`). Service, storage, API routes (`/api/review`), commands and the interface (the panel, the queue, the tasks) are built. Since the review update its statuses are `unchecked`, `errors_found` and `published`, and it gives tasks: unreconciled mentions (`Unreconciled`) and a toolchain's suggestions (`pangloss-library`'s `IdentificationByToolchain` and the classes below it), confirmed as they are or as one alternative, each confirmation by a person told to `hooks.confirmed` (not one by a toolchain's write, nor a restore). Migrations 0001 to 0003. See [Review](review.md) and the [guide](../guide/review/README.md).

## pangloss-users 🚧

Users and their passwords. See [Users](users.md).

- `current_request_username`: a `ContextVar` (default `"pangloss_default_user"`) naming the acting user. The Memgraph backend uses it to record who created, updated or deleted a node, and refuses writes by a user who does not exist or is disabled.
- `models.py`: `User` (what can be shown: no password or hash), `UserCreate`, `UserUpdate` and `UserInDB` (with `hashed_password`).
- `passwords.py`: Argon2id hashing and checking.
- `service.py`: `create_user`, `get_user`, `get_user_by_email`, `list_users`, `authenticate`, `update_user`, `set_password`, `change_password`, `set_admin` and `set_disabled`. They call the database backend's `exposed_functions`.

Tokens, sessions and the user routes are in [`pangloss-api`](#pangloss-api-), not here; permissions are not written yet ⏳. Personal access tokens (`create_access_token`, ...) are here too.

## pangloss-neo4j 🚧

The database layer for Neo4j: the same functions as `pangloss-memgraph`, ported from its tests. `STORAGE = "pangloss_neo4j:storage"`. See [Neo4j backend](neo4j-implementation.md).

## pangloss-history ✅

Optional: every version of every Document and Entity, in SQLite, best effort; `pangloss history`; diffs and restore, upgraded through the migrations. See [History](history.md).

## pangloss-dates ✅ and pangloss-calendar 🚧

Optional: uncertain dates, periods and recurrence in the Julian and Gregorian calendars (`pangloss-dates`), and days, months, years, feasts and Easter (`pangloss-calendar`; no interface). See [Dates](dates-implementation.md) and [Calendar](calendar-implementation.md).

## pangloss-typology 🚧

Optional: a vocabulary of types in a hierarchy. See [Typology](typology-implementation.md).

## pangloss-derived ✅

Optional: rules in `<app>/derived.py` that derive relations between entities from what documents say (person-to-person
networks from factoids that speak of one person each), each fact with its justifications ("why"), kept up to date by a
worker in the background from a queue of pending work that writes leave in their own transaction (`pangloss_cypher.pending`,
generic). See [Derived relations](derived.md) and [the plan](derived.md).

## pangloss-vectors 🚧

Optional: similarity. A vector for each document and entity, made by **parts** that other packages
register (`"class"` here, `"graph"` in `pangloss-fastrp`, `"name"` in `pangloss-names`, `"time"` in `pangloss-dates-vectors`), stored on nodes of their own, kept current and searched
through the backend's vector index; profiles weigh the parts (`VECTORS_PROFILES`). Needs `cypher` and
`vector_index`. Built as phases 2, 5 and 6 of [the build plan](similarity-build-plan.md); not built: a model method
and the SDK's side, a rebuild at a time of day (`VECTORS_REBUILD_AT`), `pangloss check` saying a rebuild is due.
What there is:

- the package, the `Part` protocol and the settings (step 2.1);
- the store (step 2.2, `store.py`): the vectors of each part of an item (`PGVector`, no vector index), and for each
  profile one vector of the parts end to end, each at length one and scaled by the square root of its weight, so
  that its cosine is the weighted mean of the parts' cosines (`PGProfileVector`, under a label that carries the
  profile and the dimension, `PGV_default_191`, with a vector index of that name in lower case). Rebuilds write a new
  generation beside the one in use, and a switch of the state nodes (`PGVectorState`, `PGVectorProfile`) makes it the
  one in use; `set_vectors` changes the one in use in place;
- `_vectors_meta = VectorsMeta(searchable=, include=)`: a class with `searchable=True` (a document or entity class)
  is a group, with a label and a vector index of its own for each profile; `include=False` gives its items no
  vectors, and so do `VECTORS_EXCLUDE` (classes by name, with those below) and being a stand-in's document (review's
  `Unreconciled`) unless `VECTORS_INCLUDE` names it (step 7a.3, `meta.included`). The vector indexes follow the
  models and are in the project's migrations
  (`structure.indexes()`; `VECTORS_MIGRATIONS_APP` names the app if the one with the most models is not it);
- the class part (step 2.3, `class_part.py`, registered when the package is imported, weight 0.1): a dimension for
  each declared class of documents or entities and each semantic trait; an item's vector is its class at 1 and each
  class above at `VECTORS_CLASS_DECAY ** depth` (0.5), a semantic trait as a parent of the class that has it (a
  `SemanticNonHeritableTrait` only for the class that names it), a class it fulfils (`Fulfils`, by the label on the
  node) at the decay; normalised. A class added or taken away changes its dimension, so the indexes' names;
- search (step 2.4, `search.py`): `await nearest(of, vector=, profile=, group=, k=, see_unpublished=)` gives a
  `Nearest` (`status`: `"ok"`, `"pending"` for an item with no vector or a profile not built, `"rebuild_due"` for a
  profile of another dimension than today's; `hits`, nearest first, each `Hit(id, type, score)`, the score the
  weighted mean of the parts' cosines). One query through the profile's (or group's) vector index, in the generation
  in use, the hits matched to their heads by id and cut by `fragments.listed`; never the item itself; an id merged
  into another answers for its survivor; a `group` that is not one is refused (`NotAGroup`). While the hits are fewer
  than `k` (on Memgraph a deleted node keeps its place among the nearest for up to a collection cycle; during a
  rebuild both generations are in the index) it asks again for four times as many, up to twice the profile's count
  (with what was deleted in place since its build) and one, or 4096;
- rebuild, status and the routes (step 2.5): `rebuild.rebuild(part)` under a lease (`VectorsRebuildBusy`),
  `status.status()` with the reasons a rebuild is due, `pangloss vectors rebuild | status | weights`, the admin job
  `vectors_rebuild`, `GET /api/NAME/{id}/similar` and `GET /api/vectors/status`;
- the worker (phase 5, `worker.py`): a write of a head (a document or an entity, of a class with vectors or not)
  leaves a mark of the kind `vectors`
  (an update's keeps what the old tree named); the worker, a background task of the server
  (`VECTORS_WORKER_IN_SERVER`) or `pangloss vectors worker`, tells each part that has been built what changed,
  deletes the vectors of what is gone, counts what a part left stale and, past `VECTORS_REBUILD_AFTER`, starts a
  rebuild. It and a rebuild never overlap;
- the interface module (phase 6): the section "Similar" after every item's contents, and the part of `/admin` with
  the state of the vectors and Rebuild.

The whole of what is built is described in [vectors](vectors.md); how to use it, in [the guide](../guide/vectors/README.md).

## pangloss-fastrp 🚧

Optional: the graph part of similarity, a part of `pangloss-vectors` (`INSTALLED_APPS += ["pangloss_fastrp"]`).
A vector for each document and entity from what it is joined to, by FastRP over the joined graph (wrappers hopped
over, shares, citations). The pure maths (`maths.py`: the joins, the vectors, the exact update after a change, the
overlay of a write not yet made); the rules as plain data worked out of the models (`maps.py`: `graph_maps()`,
`signature()`), with what a class says of them (`_fastrp_meta = FastRPMeta(weight=, weights=, stop=, own=,
include=)`); the reader of a Cypher database (`cypher_reader.py`: `load_all()` for a rebuild, `CypherReader` for a
refresh and an overlay); the part `"graph"` (`part.py`: `rebuild`, `refresh`, `overlay`, `refresh_ids(..., before=)`),
registered when the package is imported; the in-memory reader (`memory.py`) and the oracle its tests compare against
(`testing.py`); the settings `FASTRP_STEPS`, `FASTRP_DIMENSION` and `FASTRP_REFRESH_CAP` (past which a refresh
writes approximate vectors of what was written, `approximate.py`, counted stale until a rebuild). Measured on
Memgraph at about a million nodes. Not built: the engine in a Memgraph query module (phase 4, deferred by the user,
2026-11-21). Depends on numpy and scipy, imported only when the maths is used. See [FastRP](fastrp.md) and
[the build plan](similarity-build-plan.md), phases 3 and 5.

## pangloss-names ✅

Optional: the name part of similarity, a part of `pangloss-vectors` (`INSTALLED_APPS += ["pangloss_names"]`). A
vector of each item from its names: the trigrams of their words, hashed to `NAMES_DIMENSION` (256) and weighted by
how rare each word is (`maths.py`, no database in it). Which classes have names and which fields are names is
`_names_meta = NamesMeta(fields=["label"], include=True)` (`meta.py`: entities have their label by default, documents
none). The part `"name"` (`part.py`), at weight 0, so that only a profile that weighs it uses it: a rebuild reads
every name, makes the table of rarity and keeps it with its generation (`Part.kept`, `pangloss_vectors.store.keep`); a
refresh and an overlay weigh by that kept table. A table of name variants, `NAMES_VARIANTS` (a CSV file, checked at
`initialise()` by the line, step 8.5); a search by a name, `vector_of` and `search` (`by_name.py`), and its command
`pangloss names search` (8.6; a hit's score is the cosine of the names scaled by the parts the hit has). The demo
weighs it in a profile `who` (name 1, graph 0.25) with a table of given-name variants (8.7). Not built: a typology as a
table, a route (phase 10), anything in the interface. Depends on numpy, imported only when a vector is
made. See [Names](names.md) and [the build plan](similarity-build-plan.md), phase 8.

## pangloss-dates-vectors ✅

Optional: the time part of similarity, a part of `pangloss-vectors` (`INSTALLED_APPS += ["pangloss_dates_vectors"]`,
with `pangloss_dates`). A vector of each item from its dates (`pangloss-dates`): each date's four bounds a soft bump
along the years, read at `DATES_VECTOR_DIMENSION` (128) places `DATES_VECTOR_WIDTH` (2) years apart that the years go
round (`maths.py`, no database in it). The part `"time"` (`part.py`), at weight 0, so that only a profile that weighs
it uses it: a date counts for the document or entity that holds it and for its head (a date held by a wrapper for the
head only, an end of a range or period for nothing, a date only unknown for nothing); rebuild, refresh (exact) and
overlay. `pangloss-dates` is not changed. The demo weighs it in a profile `when` (graph 1, class 0.1, time 0.5;
step 9.5). Not built: an entity's span from the documents that name it (measured and decided against, 9.4). Depends
on numpy, imported only when a vector is made. See [The time part](dates-vectors.md) and
[the build plan](similarity-build-plan.md), phase 9.

## pangloss-reconcile 🚧

Optional: reconciliation, with `pangloss-vectors` and its parts (`INSTALLED_APPS += ["pangloss_reconcile"]`). For
each stand-in of a document (an unknown, `pangloss_vectors.unknowns_of`: review's `Unreconciled`), the entities it
may be: found by each part of similarity alone (`nearest(vector=..., exact=True)`, by the profile
`RECONCILE_PROFILE`, `RECONCILE_FETCH` of each), scored part by part (`score.py`, no database in it; the weights
`RECONCILE_WEIGHTS`, else the profile's) and by the entities of the document each is named with in other stored
documents (`reasons.py`, one query for every candidate found: `shared`, the name's cosine × n / (n + 2), at 1.5),
those under `RECONCILE_LEAST_SCORE` (0.15) left out, as the reader may see them (`candidates.py`, `candidates_of`;
the other settings `RECONCILE_MOST_UNKNOWNS`, `RECONCILE_REASONS`). Two routes (`api.py`): `POST
/api/reconcile/candidates`, a `Create` payload validated and refused as its create route does and checked by
`checked_create`, nothing written; `GET /api/reconcile/candidates/{id}`, a stored stand-in, its document planned as an
update of it would be without writing (`stored.py`), which keeps what it offered the user; each candidate with what it
shares (the reasons). What was offered and what a person chose of it are kept as plain nodes of its own
(`decisions.py`, a listener of `hooks.resolved`; `RECONCILE_KEEP_DECISIONS`, `RECONCILE_SHOWN_FOR`; `pangloss
reconcile sweep`), and learnt from (`learning.py`, `fits.py`, with `pangloss-learn`): `pangloss reconcile learn
[--dry-run] [--use ID|none]` and the admin job `reconcile_learn` fit a ranking model and a "none of these" model from
the decisions of today's signatures, and put the fit in use when its "none of these" model is no worse than always
answering the commoner (`RECONCILE_LEARN_FROM`). With a fit in use the stored route's answer has `model`, and on each
unknown `new` and `probablyNew` (`RECONCILE_NEW_ABOVE`); the ranking stays the hand-set score's. Two migrations
(`pangloss migrate`). An interface module: "Suggested" in review's reconcile dialog, with a line when a mention is
probably not in the database yet. Seeded floors of quality and of learning, and measurements at size on both
backends.

Pangloss's own toolchain (step 10.5 of [the build plan](similarity-build-plan.md)): a worker that writes, in the place
of an unreconciled mention of an unpublished document, a suggestion for a person to confirm (an
`IdentificationByToolchainFromText` of `pangloss-library`, or the class `RECONCILE_SUGGEST_AS` names), as the
toolchain user `RECONCILE_TOOLCHAIN`.

| Module | What it holds |
|---|---|
| `suggest.py` | The decision, pure: from the candidates as the dialog would be answered, nothing (under `RECONCILE_SUGGEST_ABOVE`, or "probably new" by a fit in use) or the best `RECONCILE_SUGGEST_MOST` within `RECONCILE_SUGGEST_WITHIN` of the best, as percentages that sum to 100 |
| `marking.py` | No database: which classes can be marked, the write's instruction `suggest` (`hooks.WriteInstruction`), the function of `hooks.instructed_work` (kind `reconcile`), by the instruction or `RECONCILE_SUGGEST_ON_SAVE` |
| `suggesting.py` | The worker (in the server by `RECONCILE_WORKER_IN_SERVER`, or `pangloss reconcile worker [--once]`): one update of each head as the toolchain, the mark completed and what it saw kept in that update's transaction; `mark_stored` for what is stored already |
| `judging.py` | A project's own judge, `RECONCILE_SUGGEST_WITH` (`"package.module:function"`, checked at `initialise()`) under `RECONCILE_SUGGEST_TIMEOUT`: given plain data (`Asked`), it answers `Unchanged`, `Leave` or `Suggest` |
| `decisions.py` | Beside `heard` (of `hooks.resolved`), `confirmed`, a listener of `hooks.confirmed`: an example (`via: "suggestion"`) of a person's confirmation of one of the worker's suggestions as exactly one entity |
| `api.py`, `admin.py`, `cli.py` | `POST /api/reconcile/suggest` and `GET` (admin only), the admin job `reconcile_suggest`, `pangloss reconcile suggest [--class] [--again]` and `pangloss reconcile status` |

The other settings of it: `RECONCILE_LEARN_FROM_SUGGESTIONS` (whether `learn` takes the examples of confirmations in).
Three migrations of its own (`pangloss migrate`): 0001 and 0002 of phase 11 (what was offered and chosen, and the
fits), and **0003** (step 10.5d: `PGReconcileSuggested` unique by `id` and indexed by it, `PGReconcileTried`
unique by `stand_in` and indexed by it; Memgraph's unique constraints make no index). It imports no part's package, not `pangloss-review` and not `pangloss-library` (it knows two of the
library's names as text). `requires = {"cypher", "vector_index"}`; depends on `pangloss-learn`. Not built: a ranking
by the fitted model, unknowns ranked jointly, the measurements of the worker at size (10.5g). See
[Reconciliation](reconcile.md) and [the build plan](similarity-build-plan.md), phases 10 and 11 and step 10.5.

## pangloss-library ✅

Optional: `"pangloss_library"` in `INSTALLED_APPS`. Ready-made models, with an interface module for them:
`WeightedAlternative[T]` and `Likelihood` (alternatives whose percentages add up to 100); `Identification[T]`,
`IdentificationByToolchain[T]` (a toolchain's suggestion, which review lists until a person confirms it), and the
two that keep what the source wrote, `IdentificationFromText[T]` and `IdentificationByToolchainFromText[T]`
(`text`; the second's `confirmed_as` is the first); `SameEntity[T]` and `IdentityClaim()`, with
`pangloss_library.clusters` and `GET /api/identity/{id}/cluster`. Each class of suggestion is checked at
`initialise()` against the class it becomes (`check_confirmed_classes`, and the warning
`check_fields_take_confirmed`), and given to `hooks.unconfirmed` (`suggestion_classes`). Its `before_update`
`note_if_confirmed` notes the suggestions a write confirms (`confirmed_in_write`, `ConfirmedInWrite`), for review.
Migrations: 0001 (initial), 0002 (the identifications), 0003 (`uris` on `Identification`), 0004 (`SameEntity`),
0005 (step 10.5a: the two classes that keep the text and the label index of the second). A field that takes
`Identification[...]` takes the two new classes too, so each project with the library has a migration of its own
for it (`AlterRelationTarget`, safe). See [Shares](shares-plan.md) and [duplicate entities](entity-identity.md).

## pangloss-learn 🚧

Not an app: a library with no database and nothing of Pangloss in it (numpy). `fit(examples, features)` makes a
`Model`, a logistic regression fitted with a ridge (the same examples in any order give the same model);
`Model.score(features)` is a likelihood; a model is plain data, to and from JSON; `compare(examples, features,
baseline)` says how often the one a person took is first by a model fitted on other decisions, and by a score set by
hand; `compare_calls(examples, features)`, the same of a model that says yes or no of a whole decision, against
always answering the commoner. Used by `pangloss-reconcile` (its ranking and "none of these" models, steps 11.5 and
11.6); comparison (phase 12) is to. See [Learning](learn.md) and [the build plan](similarity-build-plan.md),
phase 11.

## pangloss-compare 🚧

An app, being built (phase 6 of [the spaces plan](spaces-and-comparison-plan.md#phase-6-pangloss-compare)): the
comparison of statements, which tell of one event and how they stand to each other. Built (step 6.1): `CompareMeta`
(`_compare_meta`: `identifying`, `once_per`, `recurs`, `compared`, and on a semantic space `orientation`), inherited,
checked at `initialise()`, and its readers (`pangloss_compare.meta`); the verdict on two statements as plain data
(step 6.2, `maths.py`); stored statements read as that data and the pairs by rule (step 6.3, `reading.py`,
`pairs.py`, the setting `COMPARE_MOST_PAIRS`, `requires = {"cypher"}`). Depends on `pangloss-core`, `pangloss-cypher`,
`pangloss-models`, `pangloss-dates` and `pangloss-learn`; `pangloss-vectors` only as a dev dependency (pairs by vectors
are optional). See [Comparison of statements](compare.md).

## pangloss-testing

Fixtures for the tests that need a live database, on Memgraph or Neo4j (`PANGLOSS_TEST_BACKEND`), and the **conformance suite** (`pangloss_testing/conformance/`): the tests every backend passes, written once and run on each by `run_tests.sh`. See [Backend-neutral add-ons](backend-neutral-addons.md) and [the plan, phase 9](database-abstraction.md).
