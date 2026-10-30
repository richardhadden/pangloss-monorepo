# Pangloss Documentation

Pangloss (*Prosopography and Network Graph Labyrinth Orientation System*) v3 is a modular rewrite of the original Pangloss. You declare a data model as Python classes, and Pangloss generates the validated input/output models for it and stores the data in a graph database.

Each feature in these docs is marked with its status:

| Marker | Meaning |
|--------|---------|
| ✅ Implemented | Works and has tests |
| 🚧 Partial | Some of it works; the gaps are described |
| ⏳ Planned | Not implemented yet (stub, `TODO`, or only mentioned in a description) |

**New here?** Start with the [Getting started guide](../guide/getting-started/README.md). These pages are the reference.

## Contents

| Document | What it covers |
|----------|----------------|
| [Overview](overview.md) | What Pangloss is for and how a model becomes stored data |
| [Packages](packages.md) | The five workspace packages and how they depend on each other |
| [Defining models](models.md) | Documents, Entities, Embedded, Traits, EdgeModels, and the other model kinds |
| [Relations and fields](relations.md) | Literal fields, relations, `ViaEdge`, `RelationConfig`, field binding, `Fulfils` |
| [Generated models](generated-models.md) | The `Create`, `CreateDB`, `Update`, `UpdateDB`, `View`, `HeadView` and reference models, and the initialisation pipeline |
| [Cleaning up initialise_models](initialise-models-cleanup.md) | How the five generated models are now made by one builder, what was fixed, and what is left to decide |
| [Semantic spaces and context labels](semantic-spaces.md) | How nesting inside `SemanticSpace` wrappers is tracked |
| [Memgraph backend](memgraph.md) | Graph schema, query builders, and the database API |
| [Neo4j backend](neo4j-implementation.md) 🚧 | `pangloss-neo4j`: the same layer for Neo4j (checked against a real server: maps cannot be properties, full-text search, DDL, isolation), what differs and why, the tests ported from Memgraph's; the add-on packages run on it too |
| [Backend-neutral add-ons](backend-neutral-addons.md) ✅ | How typology, calendar, dates and zotero run on any backend: a loader in `pangloss-core`, timeout translation, a lock primitive, the `pangloss-testing` fixtures |
| [Settings](settings.md) | `BaseSettings` and database settings |
| [Logging](logging.md) | What is logged, at what level, and how to set it up |
| [Large data](large-data.md) | How long loads and migrations take on 600,000 nodes, what to turn up, and what to look out for |
| [Memgraph and Neo4j compared](backend-comparison.md) ✅ | The same workload (the demo models) timed on both, at 8,500 and at 600,000 nodes: loading, reads, writes, search; where each is faster, and the caveats |
| [Profiling the backends](backend-profiling.md) ✅ | The Cypher of each request profiled on both: a write scans the whole Memgraph for its lock (12 ms at 600,000 nodes, 0.3 with an index), the creation lookup scanning 3 million rows, Neo4j scanning every entity; what to fix, ranked |
| [Users](users.md) | User models, passwords and the `service` functions |
| [REST API](api.md) | Authentication and the user endpoints |
| [Command line](cli.md) | The `pangloss` command, and adding commands from apps |
| [Meta slots](meta-slots.md) 🚧 | Built in `pangloss_models` (and the protection of fields the API will not change): letting optional packages (the interface) keep their own `_<name>_meta` on a model class |
| [Translations](translations.md) 🚧 | Translating the interface: the JSONC files per app and project, keeping manual edits when the models change, and the `generate`, `gather` and `check` commands (built; no page uses them yet) |
| [Autocomplete](autocomplete.md) ✅ | One endpoint that finds existing entities by their label over any set of types, for the interface's relation fields and for other tools; built, with what is left to do later |
| [Structured search](structured-search.md) 🚧 | Steps 1-4 built (fields with values, lists, relations by id or nested pattern through wrappers, `$all`/`$any_of`/`$not`, `$any`, `$somewhere`, `$mentions`, `$spaces`, `$incoming`); a design for one endpoint that finds documents and entities by a pattern written as JSON (fields with values, nested patterns, "somewhere in the document", reverse relations): the form, how it is compiled, limits, steps and open questions |
| [Zotero](zotero.md) 🚧 | `pangloss-zotero`: keeping a Zotero library in the database, one way (sync by version, a websocket watcher run as a background task, commands), brought over from the earlier plugin; built, not yet tried on the real Zotero |
| [Zotero items as sources and subjects](zotero-sources.md) 🚧 | How a Zotero item can be both the source of a factoid and what a factoid is about, as one node: the options, and what was decided and built |
| [History](history.md) ⏳ | A design for recording every version of a document or entity (best effort, in SQLite), and restoring one, including after the models have changed |
| [Dates and the calendar](dates.md) ⏳ | A design for two optional packages: uncertain dates, periods and recurrence with probabilities (`pangloss-dates`), and a calendar of days, observances and a background worker (`pangloss-calendar`) |
| [Calendar: implementation plan](calendar-implementation.md) 🚧 | `pangloss-calendar`, built except for the interface: days, months, years and spans in the Julian or Gregorian calendar; `DateCharacterisation` entities (feasts and the like) by rule or by hand; the date-first query (a month over 100,000 dates in 0.07 s); the span, its margin, and what is out of reach. To use it see the [guide](../guide/calendar/README.md) |
| [Interface modules: implementation spec](interface-modules-implementation.md) 🚧 | Built (phases 0 to 4; edit cards and a few checks left): a Solid library in an installed app (`<app>/interface/`) that a model points to from `InterfaceMeta` (list page, item page, view card, edit card, navigation links); `pangloss interface new-module <app>`; how the modules are brought into the build |
| [Typology: implementation spec](typology-implementation.md) 🚧 | `pangloss-typology`, built except the tree picker, the structured-search operator and a few endpoints: a vocabulary of types in a hierarchy (`class RoleTypology(Typology)` generates the `RoleType` entity; `HAS_TYPE`, `IS_SUBTYPE_OF`), moving types safely, a type that is also a concrete entity (`also=Role`), a drag-and-drop tree in the interface; all questions answered |
| [Dates: implementation plan](dates-implementation.md) 🚧 | `pangloss-dates`, built: `python-edtf` as a parser only (its bounds are Gregorian), our own Julian day arithmetic, the four stored bounds, the sort day, the Embedded types (exact, EDTF, range, period, recurrence) in Julian and Gregorian families, ordering and "everything on this day". To use it see the [guide](../guide/dates/README.md) |
| [Review](review.md) 🚧 | `pangloss-review`, service and storage built (API and commands to do): a `published` flag that hides a document like `deleted`, a check status (unchecked, errors found, checked = published), and comments on a document or a part of it |
| [Database migrations](migrations.md) 🚧 | The design and progress of migrations: how changes to the models are applied to existing data. To use them, see the [user guide](../guide/migrations/README.md) |
| [Development](development.md) | Setting up, running tests, repository layout |
| [Status and roadmap](status.md) | What is and is not implemented |

Design notes that predate these docs live in [`../notes/modelling.md`](../notes/modelling.md) (how to model roles) and [`../packages/pangloss-models/todo.md`](../packages/pangloss-models/todo.md).
