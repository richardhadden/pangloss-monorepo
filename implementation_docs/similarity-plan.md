# Similarity, reconciliation and comparison: the implementation plan ⏳

Written 2026-11-11, from the investigation in [graph-embeddings.md](graph-embeddings.md), which holds the design,
the measurements and the decisions so far. **Nothing here is built.** This page says what would be built, in which
packages, in what order, how each stage is tested, and what the user still has to decide. The user asked for it to
be **as modular as possible**: that is the first section, and every stage follows it.

## Contents

- Modular: what that means here
- The packages
- The general hooks the core gains
- The stages
- What every stage includes
- Decisions for the user
- What this plan does not do

## Modular: what that means here

1. **One job a package.**
   - Storing and searching vectors is one package.
   - Each kind of vector (a *part*: graph, class, name, time) is computed by one module.
   - Reconciliation and comparison are packages of their own.

   A project installs what it uses: comparison without vectors works (by rules); vectors without reconciliation
   work (a "Similar" section).
2. **Packages meet through declared interfaces, not by importing each other's insides.** Each of these is a
   documented protocol, so another implementation can be put in its place:
   - a part is a protocol;
   - a profile is data;
   - a source of candidates is a hook.
3. **The core gains only general hooks.** It learns nothing of similarity. Each hook should have a second use
   (`SemanticTrait` also serves the RDF export and search across a trait; vector indexes serve any package that
   stores vectors).
4. **Backend-neutral by default, faster where the backend allows.** Every computation has a Python implementation
   that runs on any Cypher backend. The Memgraph query module is a second engine behind the same interface, chosen
   by a capability, and tested to give the same answers.
5. **Optional links are optional imports.** Where one package can use another if both are installed, the link is
   made through a hook at `initialise()`, never by a hard dependency:
   - the time part, which lives in `pangloss-dates`;
   - reconciliation candidates, in review's dialog.
6. **Each package owns its settings.** Its own meta slot on model classes, its own settings, its own migrations,
   commands, routes, interface module and translations, as the existing add-ons do.

## The packages

```
pangloss-models / pangloss-cypher / backends     general hooks only (next section)
        ▲
pangloss-vectors          storage, indexes, generations, the Part protocol, profiles, search, overlays,
        ▲                 the worker, rebuild job; the class part (it needs only the models)
        │
        ├── pangloss-fastrp       the graph part: the joined graph, FastRP, exact refresh and overlay;
        │                         a Python engine and a Memgraph engine
        ├── pangloss-names        the name part: folded trigrams, tables of name variants
        └── pangloss-dates        (existing) gains an optional time part, registered if pangloss-vectors is installed

pangloss-reconcile        candidates for an incoming payload: two stages, pairs, reasons, "someone new",
        │                 learning from decisions; fills review's candidate hook if review is installed
pangloss-compare          per-class comparison declarations, verdicts at lookup, judgements as documents,
                          learning from judgements; uses vectors to find pairs if pangloss-vectors is installed
pangloss-learn (small)    fitting and keeping a weighted model from labelled examples, used by both of the above
```

| Package | Depends on | Optional | Ships |
|---|---|---|---|
| `pangloss-vectors` | core, models | — | Models of nothing (its nodes are not models); migrations for its indexes; `api.py`, `cli.py`, `admin.py`; an interface module ("Similar" section, admin slot) |
| `pangloss-fastrp` | vectors | backend `query_modules` capability | A part; `FastRPMeta` slot; the Memgraph module file |
| `pangloss-names` | vectors | `pangloss-typology` (a vocabulary as a table of variants) | A part; tables of name variants (a file, or a typology) |
| `pangloss-dates` (time part) | — | vectors | `pangloss_dates.vector_part`, registered only when `pangloss_vectors` is importable |
| `pangloss-learn` | numpy | — | `fit`, `Model` (kept as a small document of weights, with the date and the judgements it came from) |
| `pangloss-reconcile` | vectors, learn | review (stand-ins, the dialog), library (`IdentificationByToolchain`) | `/api/reconcile/candidates`; a toolchain mode; an interface module |
| `pangloss-compare` | learn | vectors (finding pairs), dates (date gaps) | `CompareMeta` slot; `/api/compare/...`; `EventJudgement` documents; an interface module |

Why `pangloss-learn` is apart:
- Both reconciliation and comparison fit weights from people's decisions, the same way.
- One small package keeps the method and its storage in one place.
- A project could replace it with another learner behind the same two functions.

## The general hooks the core gains

Each is small, tested in the conformance suite on both backends, and documented where its kind of hook already is.

| Hook | Where | For | A second use |
|---|---|---|---|
| `SemanticTrait`, `SemanticNonHeritableTrait` | `pangloss-models` (`model_bases/trait.py`), exported, in stubs and `export_models()` | The class part counts these and not mixins | RDF export (a trait that is a class), search across a trait, the interface's type grid |
| Vector index as an index kind in migrations (`AddIndex` with `kind: "vector"`: labels, property, dimension, metric) | `pangloss_models.migrations.changes`; DDL in each backend's migration backend | `pangloss-vectors`' indexes, made and dropped by migrations | Any package that stores vectors (text embeddings later) |
| `Dialect.vector_search(index, k, vector, filter)` | `pangloss-cypher` dialect, both backends | Search, the same call on both | Same |
| Capabilities `vector_index`, `query_modules` | `pangloss_core.storage.Capabilities` | What a package may use; `requires = {"vector_index"}` | Any add-on |
| `Backend.install_query_module(name, source)` (Memgraph: `mg.create_module_file` / `update_module_file`, compared first; others: absent) | `pangloss_core.backend`, Memgraph backend | An app ships database code; installed at server start and by `migrate` | Any add-on wanting in-database code |
| `pangloss_review.hooks.candidate_providers` | `pangloss-review` (a package hook, not the core) | Review's reconcile dialog asks for ranked candidates without knowing who gives them | Another reconciler (an external authority file) |

No hook names similarity, FastRP or Memgraph-only behaviour in the core.

## The stages

Each stage ends with something usable and tested. Stages 1-6 are the shared base; 7-8 add parts; 9-10 are
reconciliation; 11-12 comparison; 13 is the second backend's tuning. Comparison (11-12) needs only stages 1 and 10,
so it can be built in parallel with 2-9.

### Stage 0: evaluate on real data (before any package code)

**Why first:** every measurement so far is on generated data. Real names, real hubs and real decisions decide which
parts and settings matter.

- **What:** the trial scripts (`/tmp/embed-proj/`), turned into a script in `notes/similarity-evaluation/`, run
  against **a copy** of a real project's data on a scratch database. Never the demo's or the user's live database.
  - Reconciliation against real `Unreconciled` mentions and the choices made for them.
  - Comparison of real statements, with a hand-checked sample.
  - The sizes `refresh` meets at real hubs.
  - The name part on real Latin and vernacular forms.
- **Done when:** the numbers are in `graph-embeddings.md`, and the user has decided which of stages 7, 8, 9 and 11 go
  ahead and in what order.
- **Needs from the user:** a project and a copy of its data to use (decision 1).

### Stage 1: the core hooks

- **What:**
  - `SemanticTrait` and `SemanticNonHeritableTrait`;
  - the vector index kind in migrations, with DDL on both backends;
  - `Dialect.vector_search`;
  - the two capabilities;
  - `Backend.install_query_module`.
- **Tests:**
  - Conformance: a migration makes and drops a vector index, and a search finds the nearest.
  - Model tests: semantic traits in labels, the export and the stubs.
  - A Memgraph live test: a module installed, updated, and refused when unchanged.
- **Docs:**
  - `models.md` (traits), `migrations.md` (index kind), `database-abstraction.md` (dialect method),
    `backend-neutral-addons.md` (capabilities, modules).
  - The skill: the new trait bases and the module hook.
- **Done when:** both backends pass. Nothing uses the hooks yet but their tests.

### Stage 2: `pangloss-vectors`, the framework, with the class part

- **What:**
  - **Storage**: `(:PGVector:PGV<group> {of, part, generation, vector, at})` with an index on `of` and no edge to the
    item.
    - Groups are declared by `SimilarMeta(searchable=True)` on a class; a vector index is made for each group by
      migration.
    - Generations: a rebuild writes a new one, then switches.
  - **The Part protocol**:
    - `name`, `dimension(models)`;
    - `batch(reader) -> rows`;
    - `local: bool`; `refresh(changed, reader)`; `overlay(plan, reader)`;
    - `requires`.
  - **Profiles**: named sets of part weights (data, in settings or a module's `vectors.py`). A search scales the parts
    of the query.
  - **The class part**: the hierarchy, semantic traits, fulfilled classes; one exact dimension per class.
  - **Search**:
    - `nearest(item_id | vector, profile, group, k)`, through the dialect;
    - overfetch, then `fragments.visible` and `not_deleted`;
    - tolerant of a deleted node returned by the index.
  - **Rebuild**: as an admin job (`admin.py`) and a command (`pangloss vectors rebuild [--part]`). Written before it
    is indexed.
  - **Status**: generation, when built, how many stale.
  - **API**: `GET /api/{NAME}/{id}/similar?profile=&type=&limit=`, `GET /api/vectors/status`.
- **Tests:**
  - Live, both backends: a rebuild, a search, visibility (deleted, unpublished), the generation switch while
    searching.
  - The class part: `CreationOfArtwork` near `CreationOfPainting`, as measured.
- **Docs:** a package page `vectors.md`, `guide/vectors/`, `guide/cli.md`, `api.md`, `status.md`.
- **Done when:** with the class part alone, the API answers "documents of a like class".

### Stage 3: `pangloss-fastrp`, the graph part (Python engine)

- **What:**
  - **The joined graph**: documents and entities; through the modelling kinds; never a reverse edge.
  - **`FastRPMeta` slot**: `through`, `stop`, a class weight, `weights={field: w}`, `include=False`.
  - **The Python engine**:
    - reads the nodes and forward edges in pages, by Cypher both backends run;
    - joins, runs FastRP seeded by id (numpy, scipy), writes through `pangloss-vectors`.
  - **Exact `refresh` and `overlay`** in Python, reading the neighbourhood by Cypher, two rings.
- **Tests:**
  - The equality the trial showed: refresh equal to a rebuild; overlay equal to the same plan written.
  - Weights and stops change what they should.
  - Both backends.
- **Measured:** the batch and an overlay at 300k nodes, on both backends, against the trial's figures.
- **Done when:** "Similar" works by the graph part on both backends.

### Stage 4: the Memgraph engine

- **What:**
  - The query module, the same maths as stage 3 behind the same interface. It is installed by stage 1's hook, and
    chosen when the backend has `query_modules`.
  - The rebuild is a write procedure (the fault of more than about 100,000 records), or pages.
- **Tests:**
  - Python engine and module give the same vectors on the same data (the trial: identical).
  - The module is reinstalled when its file changes.
  - The record-count fault is covered by a test that fails if Memgraph fixes it (`xfail(strict=True)`), so the
    workaround can then go.
- **Measured:** overlay latency (the trial: 37 ms against Python's 267 ms on Neo4j).
- **Done when:** Memgraph projects use the module without knowing it.

### Stage 5: keeping vectors current

- **What:**
  - **Marking**: a `pending_work` kind `vectors` for each class with vectors.
  - **The worker**, in `pangloss-vectors`, generic over parts:
    - it claims batches;
    - asks each `local` part to refresh;
    - leaves non-local parts to the rebuild;
    - keeps the stale count.
  - **The hub cap** (a setting): past it, approximate and count.
  - **A scheduled rebuild** (a setting: after N stale, or at a time).
  - **The former neighbours**, kept with each vector, so a removed reference updates the entity.
- **Tests:**
  - Live: a save is reflected within the worker's interval; a removed reference updates both ends; the cap; a
    rebuild while writes go on.
- **Measured:** the cost a save pays for the mark (expected below 1 ms, as for derived), and the worker's lag under
  four writers.
- **Done when:** vectors follow the data without a manual rebuild.

### Stage 6: the "Similar" section in the interface

- **What:**
  - **The section**: an `itemSections` entry on an item's page and on a nested document's page. Fetched on its own.
  - **Its contents**: `ReferenceChip`s with a similarity bar, and a `MenuSelect` of profile and type.
  - **The admin slot**: status and a Rebuild button (the job).
  - **Text**: every string a `t()` slot with translations.
- **Tests:** e2e (rows in `e2e/COVERAGE.md`), loaded in the dev build.
- **Done when:** a reader sees similar items, and an admin can rebuild.

### Stage 7: `pangloss-names`, the name part

- **What:**
  - **The part**: trigrams of folded labels, hashed, weighted by rarity, as an index of its own for each searchable
    group.
  - **Tables of name variants**, applied before the trigrams: a file in the project, or a typology. The measured
    gain was the largest single one (people 86% to 94%).
  - **Kept separately**: label search here is for candidates. Review's `likeness` stays for exact re-ranking.
- **Tests:** variants found; a name table changed rebuilds only this part.
- **Done when:** a search by name returns spelling variants and namesakes, ranked.

### Stage 8: the time part, in `pangloss-dates`

- **What:**
  - `pangloss_dates.vector_part`: soft bumps over each date's bounds, of a width set to the project's dates (2
    years in the trial; 1 was too narrow).
  - Registered only if `pangloss_vectors` is importable.
  - For an entity: the span of its documents' dates.
- **Tests:** in `pangloss-dates`' own tests, skipped when `pangloss-vectors` is absent; recurring events kept apart.
- **Done when:** a profile with time finds an event's other reports (the trial: 99.5% in the 10 nearest).

### Stage 9: `pangloss-reconcile`

- **What:**
  - **The service**: `POST /api/reconcile/candidates` with a `Create` payload whose unknowns are stand-ins
    (`Unreconciled`). It validates, plans (`plan_create`), overlays, and writes nothing.
  - **The answer**, for each unknown:
    - ranked candidates as `ReferenceView`s, each with its part scores;
    - reasons (shared neighbours by name, "already named with the other unknown's candidate");
    - how likely "someone new" is.
  - **Stage 1** (a profile per kind of entity) and **stage 2** (a weighted score over label, context, time and class
    fit).
  - **Several unknowns** ranked jointly.
  - **A toolchain mode**: given a threshold, it writes `IdentificationByToolchain` for a person to confirm, never a
    silent merge.
  - **Review's dialog** (if review is installed): candidates through `candidate_providers`.
- **Tests:**
  - The API: payload in, ranked candidates out, nothing written.
  - Overlay equality.
  - Two unknowns.
  - Review installed and not.
- **Measured:** on the stage 0 data.
- **Done when:** a toolchain can post a factoid and get candidates.

### Stage 10: `pangloss-learn`, and reconciliation learning from decisions

- **What:**
  - `fit(examples) -> Model`, `Model.score(features)`.
  - A model is kept as a small document of weights, with its date and the decisions it came from: history records it.
  - Reconciliation's examples are the reconciliations and the confirmed or rejected toolchain suggestions review
    already records.
  - A command and an admin job retrain; the hand-set weights are the default until there is a model.
- **Tests:** a model reproduces planted weights; retraining is reproducible; a project with no decisions still works.
- **Done when:** reconciliation improves from the project's own decisions.

### Stage 11: `pangloss-compare`, verdicts at lookup

- **What:**
  - **`CompareMeta`**, a slot on statement classes, inherited, checked at `initialise()` (a field it names must be a
    field of the class):
    - `identifying=[fields]`;
    - `once_per="field"`;
    - `recurs=True`.
  - **Pairs**: statements of related classes (the same or one an ancestor of the other) sharing an identifying entity.
    By rule, needing no vectors. If `pangloss-vectors` is installed, also by a profile of graph, class and time, for
    people not yet reconciled.
  - **The verdict**:
    - agree, disagree (with the fields), or two events, with the likelihood;
    - compared on the fields of the nearest common class;
    - worked out when shown, **never written**.
  - **People's judgements**: `EventJudgement` documents (the statements, the verdict, the fields, a note), which
    override the computed verdict. In `pangloss-compare`, or in `pangloss-library` beside `Identification`
    (decision 6).
  - **API**: `GET /api/compare/{statement_id}`.
  - **A list across the database** ("every disagreement in source S"), as a rebuildable cache the worker keeps, only if
    pages need it.
- **Tests:**
  - The trial's cases: a general and a specific class; once per; recurring; negated.
  - A judgement overrides.
  - Declarations refused at `initialise()` when wrong.
- **Done when:** a statement's page can list its likely duplicates and disagreements.

### Stage 12: comparison in the interface, and learning from judgements

- **What:**
  - **Side by side**: a panel or page setting two statements next to each other, field by field, on the history
    compare page's pattern.
  - **Recording a judgement** from there.
  - **Training**: comparison learns from `EventJudgement`s through `pangloss-learn` (the trial: a few hundred equal
    the hand-set rules; a thousand cut mistakes by a third).
  - **Later**: asking for judgements on the pairs it is least sure of.
- **Tests:** e2e; learning reproducible.
- **Done when:** a scholar can review a disagreement and the system learns from it.

### Stage 13: Neo4j tuning, and the measurements written up

- **What:**
  - A cheaper overlay on Neo4j: read only joined neighbour ids by aggregation, or keep degrees with vectors.
  - Measurements of every stage on both backends at 300k and 640k nodes, in `backend-comparison.md`.
- **Done when:** the docs say what each backend costs, measured.

## What every stage includes

As the skill's "Before a change is finished":
- `./run_tests.sh` passes;
- storage behaviour has conformance or live tests on both backends;
- the docs and `status.md` say what is now true, with markers;
- the guide, if what a user types changed;
- `guide/cli.md` for every command;
- interface strings as `t()` slots with translations;
- `e2e/COVERAGE.md` rows;
- the dev build loaded;
- the skill corrected in the same commit when a package or hook is added.

Each stage is its own commit, or a few, on its own branch.

## Decisions for the user

1. **Stage 0's data**: which project, and a copy of its data on a scratch database.
2. **Package names**: `pangloss-vectors`, `pangloss-fastrp`, `pangloss-names`, `pangloss-reconcile`,
   `pangloss-compare`, `pangloss-learn`.
3. **The time part in `pangloss-dates`** (as proposed, the principle that dates own what is about dates), or in a part
   package of its own.
4. **The review hook** `candidate_providers` in `pangloss-review`, or a small bridge app between review and reconcile.
5. **Unpublished documents** in the graph or not (recommended: not, until published; overlays still give them
   vectors when needed).
6. **Where `EventJudgement` lives**: `pangloss-compare` or `pangloss-library`.
7. **Model method or route only**: `Person.similar(id)` with an SDK side, or only the API routes.
8. **Which stages, in what order**, after stage 0.

Already decided, with the dates, in [graph-embeddings.md](graph-embeddings.md):
- per-class weights by the node's `type`, default 1;
- the class part, with `SemanticTrait` and `SemanticNonHeritableTrait`, and fulfilled classes from labels;
- machine verdicts are worked out at lookup, and only a person's judgement is written.

## What this plan does not do

- **Text embeddings** (a part of what documents *say*): the Part protocol allows one later.
- **Merging anything**: reconciliation proposes, and a person confirms; comparison judges, and nothing is merged.
- **A permission model** for who may judge or retrain: as elsewhere, an open decision in `TODO.md`.
