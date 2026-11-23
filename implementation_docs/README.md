# Pangloss documentation

Pangloss (*Prosopography and Network Graph Labyrinth Orientation System*) v3: you declare a data model as Python
classes, and Pangloss makes the validated models for it, stores the data in a graph database, and gives it an API,
migrations, an SDK and a web interface.

**These pages are the reference**: the design of each part, what is built, and what was measured. To *use* Pangloss,
read [the guides](../guide/README.md): [getting started](../guide/getting-started/README.md),
[the tutorial](../guide/tutorial/README.md), [every command](../guide/cli.md).

| Marker | Meaning |
|--------|---------|
| ✅ | Built and tested |
| 🚧 | Partly built; the gaps are said |
| ⏳ | Planned, not built |

A page that began as a plan keeps the plan, with "As built" sections where the code differs; the status line at its
top says which. Plans whose work is long finished have been condensed to what still matters (the decisions, the
traps, what is open); the full text of each is in the history of the repository.

## Start here

| Page | |
|---|---|
| [Overview](overview.md) | What Pangloss is for, and how a model becomes stored data |
| [Status and roadmap](status.md) | What works and what does not, on one page |
| [Packages](packages.md) | The packages of the workspace and how they depend on each other |
| [Development](development.md) | Setting up, running the tests, the layout of the repository |
| [The demo project](demo-setup.md) | `pangloss-demo/`: a finished project, and how to set it up |

## Models

| Page | |
|---|---|
| [Defining models](models.md) | Documents, entities, embedded objects, traits, edge models and the other kinds; `Meta` options |
| [Relations and fields](relations.md) | Literals, relations, `ViaEdge`, `RelationConfig`, field binding, `Fulfils`, optional relations |
| [Generated models](generated-models.md) | `Create`, `Update`, `View`, `HeadView` and the rest, and how `initialise()` makes them |
| [Semantic spaces and context labels](semantic-spaces.md) | How nesting inside `SemanticSpace` wrappers is tracked |
| [Meta slots](meta-slots.md) 🚧 | How an optional package keeps its own `_<name>_meta` on a model class; fields the API will not change |
| [Importing](imports.md) ✅ | Every package exports its public names from its root; why there is no `pangloss.` namespace |
| [Modelling DX](modelling-dx.md) ✅ | A review of the footguns of declaring models, and what was built to close them: clear refusals, the literal registry |
| [Language server](language-server.md) ✅ | `pangloss check` and `pangloss-lsp`: mistakes at the line, quick fixes, completion, hover; the editor extensions |
| [Shares](shares-plan.md) ✅ | `SumsTo`, `pangloss-library`: a conjunction whose members' shares add up to 100 |
| [Implied types](implied-types.md) 🚧 | Narrowing a document by what a field holds; what is built in the interface, what is not, and why not on the backend |
| [Label templates](label-templates.md) 🚧 | Labels worked out from a document's contents, in Python and in the interface; locked unless a user writes their own. The plan, what was built (2026-11-11), and a trial of readable English and German |
| [Companion documents](companion-documents.md) ✅ | A document offered with a new entity (a factoid with a naming and a gendering of a new person), filled in from the document the entity is made from, written in one transaction with it: the plan of 2026-11-12, and what was built |

## Storage

| Page | |
|---|---|
| [The database abstraction](database-abstraction.md) ✅ | Why operations and a dialect, not a query builder; what Memgraph and Neo4j differ in; `pangloss-cypher` |
| [Memgraph](memgraph.md) ✅ | The graph schema, the queries, the database API |
| [Neo4j](neo4j-implementation.md) ✅ | The same layer for Neo4j: what differs and why |
| [Backend-neutral add-ons](backend-neutral-addons.md) ✅ | How an add-on package runs on either backend; the `pangloss-testing` fixtures |
| [Migrations](migrations.md) 🚧 | How changes to the models are applied to data that exists: the design and its progress |
| [Large data](large-data.md) | Loads and migrations on 600,000 nodes: how long, what to turn up, what to look out for |
| [The two backends compared](backend-comparison.md) ✅ | One workload timed on both, at 8,500 and at 600,000 nodes |
| [Profiling the backends](backend-profiling.md) ✅ | The Cypher of each request profiled on both; what was fixed |
| [An RDF (Oxigraph) backend](rdf-oxigraph-feasibility.md) | A report on a third backend. Not planned |
| [DozerDB trial](dozerdb-trial.md) ⏳ | What to test before using DozerDB with Neo4j Community. Not run |

## Search

| Page | |
|---|---|
| [Autocomplete](autocomplete.md) ✅ | Entities by their label, over any set of types |
| [Structured search](structured-search.md) ✅ | `POST /api/search`: documents and entities by a pattern written as JSON; how it is compiled; measurements |
| [Typed search patterns](search-where-implementation.md) ✅ | `Model.Where` and `Model.Order`: the same patterns typed, for Python and the SDK |
| [The search form](search-form.md) ✅ | The form on a list page that builds a pattern |
| [Deep search](deep-search.md) ✅ | Why a search through everything in a document was slow, what was rewritten, what remains |

## The API, users and tools

| Page | |
|---|---|
| [REST API](api.md) ✅ | Authentication, sessions, tokens, the user endpoints, the routes of the models |
| [Users](users.md) 🚧 | The user models, passwords, the pages for users. Permissions are not built |
| [Settings](settings.md) | `BaseSettings` and the database settings |
| [Logging](logging.md) | What is logged, at what level, and how to set it up |
| [Command line](cli.md) | How the `pangloss` command finds a project, runs the server and takes commands from apps. The list of commands is [in the guide](../guide/cli.md) |
| [SDK](sdk.md) ✅ | A project's models as an installable package that talks to its API: the design and how it was built |
| [Publishing](publishing.md) ⏳ | How the packages would be released |

## The interface

| Page | |
|---|---|
| [The interface](interface.md) 🚧 | `pangloss-interface`: the architecture, the tooling, the build in a project |
| [Still to document](interface-to-document.md) | The running list of what is built and not yet written up in the page above |
| [Features, as built](interface-features.md) ✅ | Collapsed wrappers, form validation, unsaved changes and the stash, the hooks for modules |
| [Interface modules](interface-modules-implementation.md) 🚧 | A Solid library in an installed app: its pages, cards and sections |
| [The homepage and a project's pages](homepage-and-pages.md) ✅ | The default homepage, "search everything", `new-homepage` and `new-page` |
| [Translations](translations.md) 🚧 | The files of each app and project, keeping edits when the models change, the commands |
| [Hard-coded strings](interface-strings.md) | Every fixed text of the interface and its slot |
| [Look and feel](look-and-feel.md) ✅ | The one button, table and badge; what was tried and taken out |

History, review, the calendar and typologies have their interface described in their own pages, below.

## Optional packages

| Page | |
|---|---|
| [History](history.md) ✅ | `pangloss-history`: every version, restore (also after the models changed), the panel and compare page |
| [Review](review.md) ✅ | `pangloss-review`: unpublished until checked, comments, the panel and the queue |
| [Review update](review-update-plan.md) ✅ | The plan of 2026-11-10 and what was built: several creators and toolchains, `published`, tasks and who they are given to, unreconciled mentions, identifications by a toolchain; the spec is [review_update_spec.md](review_update_spec.md) |
| [Dates: the first design](dates.md) 🚧 | The wide design for uncertain dates and a calendar; both were built narrower (the next two rows) |
| [Dates](dates-implementation.md) ✅ | `pangloss-dates`: day numbers, the four bounds, the types, `Dateable`, the timeline |
| [Calendar](calendar-implementation.md) 🚧 | `pangloss-calendar`: days, months, years, feasts, the date-first query |
| [Typology](typology-implementation.md) 🚧 | `pangloss-typology`: vocabularies in a hierarchy; the live drag-and-drop tree |
| [Derived relations](derived.md) ✅ | `pangloss-derived`: rules that derive relations from documents; why it is built as it is; measurements |
| [Derived edges and documents](derived-edges-and-documents.md) ✅ | 2026-11-17 plan: `DerivedEdge` (two ends, qualifiers) replaces `Derived`; edges declared on a document class; derived documents (`DerivedFactoid`) with non-protecting `DerivedFrom` citations; interactions with matches criteria and embeddings; reviewed against the code and corrected; all decisions taken (D1 to D21); all eleven steps built by 2026-11-18 (the last: shortcut edges); what differs from the plan is at its top, and what is as built is in [derived.md](derived.md) |
| [Zotero](zotero.md) 🚧 | `pangloss-zotero`: a library kept in the database. Not yet run against the real Zotero |
| [Zotero items as sources and subjects](zotero-sources.md) 🚧 | The modelling question behind it, and what was decided |
| [RDF export](rdf.md) 🚧 | `pangloss-rdf`: every item as RDF, and an ontology made from the models |
| [RDF export: the plan](rdf-export-plan.md) 🚧 | Its design, the decisions, and what is not built |
| [Duplicate entities: merging, identity statements, citations](entity-identity.md) 🚧 | A merge of two entities that can be undone (built but for the interface: `Entity.merge`, `unmerge`, `KeepOnMerge()`, the API, SDK and CLI, proposals verified by a second user); planned: its interface, statements that two entities are one, documents citing documents |
| [Matches criteria](matches-criteria.md) 🚧 | 2026-11-17: someone described, not identified ("N. N., Maximilian's secretary"): a reified relation holding a search pattern, linked to every entity that fits, kept up to date in the background; `Computed()` in the core; a specification, all 28 questions answered, checked against the code; being built since 2026-11-19, step by step (its "As built" section says how far) |
| [Vectors](vectors.md) 🚧 | `pangloss-vectors`: similarity. What is stored, parts and profiles, groups, generations, search, rebuild and status, the routes, the class part, the worker that keeps vectors current, the "Similar" section and the part of `/admin`. Not built: a model method and the SDK's side, a rebuild at a time of day, `pangloss check` saying a rebuild is due |
| [FastRP](fastrp.md) 🚧 | `pangloss-fastrp`: the graph part of similarity. The joined graph, `FastRPMeta`, the settings, rebuild, refresh and overlay, approximate vectors past the cap, measured on Memgraph at size (2026-11-21). Not built: the engine in a Memgraph query module (deferred by the user) |
| [Names](names.md) ✅ | `pangloss-names`: the name part of similarity (phase 8 of the build plan): the maths (trigrams, rarity by the word, hashed), `NamesMeta`, the part `"name"` at weight 0, the table of rarity kept with a generation, the table of variants (`NAMES_VARIANTS`), search by a name (`pangloss names search`), the demo's profile `who`, measured on a planted world. Not built: a typology as a table, a route (phase 10), anything in the interface |
| [The time part](dates-vectors.md) ✅ | `pangloss-dates-vectors`: the time part of similarity (phase 9 of the build plan): the maths (a date's bounds as a soft bump on a ring of years), the part `"time"` at weight 0, whose vector a date is, the settings `DATES_VECTOR_DIMENSION` and `DATES_VECTOR_WIDTH`, the demo's profile `when`, measured on a dated planted world on both backends. Not built: an entity's span from the documents that name it (decided against), a date on a wrapper for the document that holds it, a recurrence's rule |
| [Reconciliation](reconcile.md) 🚧 | `pangloss-reconcile`: the entities a stand-in of a document may be (phases 10 and 11 of the build plan): the settings (`RECONCILE_PROFILE`, `RECONCILE_FETCH`, `RECONCILE_WEIGHTS`, `RECONCILE_MOST_UNKNOWNS`, `RECONCILE_REASONS`, `RECONCILE_LEAST_SCORE`, `RECONCILE_KEEP_DECISIONS`, `RECONCILE_SHOWN_FOR`, `RECONCILE_LEARN_FROM`, `RECONCILE_NEW_ABOVE`), the candidates found by each part exactly and scored part by part and by the entities shared (`shared`, the reasons), `POST /api/reconcile/candidates` (a payload, checked as its create, nothing written) and `GET /api/reconcile/candidates/{id}` (a stored stand-in), the answer's shape, what is not refused, the decisions kept, learning from them (`pangloss reconcile learn`) and "none of these" (`new`, `probablyNew`), the interface ("Suggested" in review's reconcile dialog), the measurements at size. Not built: the toolchain mode, a ranking by the fitted model, unknowns ranked jointly |
| [Editing together](live-editing.md) ⏳ | An initial specification, nothing built: a form that knows its document changed underneath it, that can take the change, and two people editing one document at once; the questions its design has to answer |
| [Learning](learn.md) 🚧 | `pangloss-learn`: a library, not an app: `fit` (a logistic regression with a ridge), `Model`, `compare` (a fitted model against a score set by hand, on decisions held out), `compare_calls` (a yes or no of a whole decision against the commoner answer). Used by `pangloss-reconcile` |
| [Similarity, reconciliation and comparison: the plan](similarity-plan.md) 🚧 | 2026-11-11: modular packages (vectors, fastrp, names, the time part in dates, reconcile, compare, learn), the general core hooks, thirteen stages after an evaluation on real data; decisions open. Revised 2026-11-20 (the joined graph's rules, decisions 9-15). Stages 1-3, 5 and 6 built by 2026-11-21, stage 4 deferred |
| [Similarity: the build plan](similarity-build-plan.md) 🚧 | 2026-11-20: phases 0-7 step by step (core hooks, `pangloss-vectors`, `pangloss-fastrp`, the Memgraph module, the worker, the interface, the demo), the tests of each by file, what is measured, who builds each (`builder`, `test-runner`, `Explore`, main); phases 8-13 in outline. Phases 0-3, 5 and 6 built by 2026-11-21, with "As built" sections; phase 4 deferred by the user |
| [Similar items by graph embeddings](graph-embeddings.md) 🚧 | An investigation (2026-11-11): FastRP over a graph of heads, vector indexes on Memgraph and Neo4j, the batch and the update on write; measured on a synthetic 520k-node graph; decisions open. Revised 2026-11-20: relations through several wrappers are one join (measured), what the join weighs, and the rules for computed edges, citations, merges and derived documents |
| [One kind of edge model](edge-models-unified.md) | An investigation (2026-11-20): what collapsing `ViaEdge`/`EdgeModel` and `ReifiedRelation` into one would take; the rough edges of a relation through several wrappers, checked live (two faults in reading an entity); three options and their size. Option A built (✅, "As built": which rough edges are closed); B and C not |
| [A relation through several wrappers as one edge: the plan](relation-steps-plan.md) ✅ | The plan for option A of the report above (2026-11-20, branch `relation-steps`), built, with "As built" for each step: the two reverse-read faults, a wrapper's own relations in a search, `via` (one ordered condition on any step of the way, on an edge or a node), `$incoming`; measured |
| [A field takes the classes below a wrapper it names: the task](reified-relation-inheritance-plan.md) ✅ | Built 2026-11-20 (branch `reified-relation-inheritance`): `InRole[Person]` takes a `Finer[T](InRole[T])`, as a field takes the classes below a document; what was known, the steps, and "As built" (the size, the decisions, what is not taken) |
| [The admin page and jobs](admin.md) 🚧 | `pangloss-admin`: `/admin`, and long-running jobs in a process of their own |

## Reviews

| Page | |
|---|---|
| [Code reviews and refactorings](code-reviews.md) | Four passes over the code, condensed: what changed, the decisions and traps that still matter, what is open |
| [Mutation testing](mutation-testing.md) 🚧 | 2026-11-18: mutmut on pangloss-dates (98.4%) and on the search checking and label templates of pangloss-models (survivors 789 → 507); what it found, how to run it, what is left, what to check next |

Design notes older than these pages: [`../notes/modelling.md`](../notes/modelling.md) (how to model roles) and
[`../packages/pangloss-models/todo.md`](../packages/pangloss-models/todo.md).
