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
| [Zotero](zotero.md) 🚧 | `pangloss-zotero`: a library kept in the database. Not yet run against the real Zotero |
| [Zotero items as sources and subjects](zotero-sources.md) 🚧 | The modelling question behind it, and what was decided |
| [RDF export](rdf.md) 🚧 | `pangloss-rdf`: every item as RDF, and an ontology made from the models |
| [RDF export: the plan](rdf-export-plan.md) 🚧 | Its design, the decisions, and what is not built |
| [Duplicate entities: merging, identity statements, citations](entity-identity.md) 🚧 | A merge of two entities that can be undone (the backend is built: `Entity.merge`, `unmerge`, `KeepOnMerge()`); planned: its API and interface, statements that two entities are one, documents citing documents |
| [Similarity, reconciliation and comparison: the plan](similarity-plan.md) ⏳ | 2026-11-11: modular packages (vectors, fastrp, names, the time part in dates, reconcile, compare, learn), the general core hooks, thirteen stages after an evaluation on real data; decisions open |
| [Similar items by graph embeddings](graph-embeddings.md) ⏳ | An investigation (2026-11-11): FastRP over a graph of heads, vector indexes on Memgraph and Neo4j, the batch and the update on write; measured on a synthetic 520k-node graph; decisions open |
| [The admin page and jobs](admin.md) 🚧 | `pangloss-admin`: `/admin`, and long-running jobs in a process of their own |

## Reviews

| Page | |
|---|---|
| [Code reviews and refactorings](code-reviews.md) | Four passes over the code, condensed: what changed, the decisions and traps that still matter, what is open |

Design notes older than these pages: [`../notes/modelling.md`](../notes/modelling.md) (how to model roles) and
[`../packages/pangloss-models/todo.md`](../packages/pangloss-models/todo.md).
