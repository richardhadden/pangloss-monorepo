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
| [Settings](settings.md) | `BaseSettings` and database settings |
| [Logging](logging.md) | What is logged, at what level, and how to set it up |
| [Large data](large-data.md) | How long loads and migrations take on 600,000 nodes, what to turn up, and what to look out for |
| [Users](users.md) | User models, passwords and the `service` functions |
| [REST API](api.md) | Authentication and the user endpoints |
| [Command line](cli.md) | The `pangloss` command, and adding commands from apps |
| [Meta slots](meta-slots.md) 🚧 | Built in `pangloss_models` (and the protection of fields the API will not change): letting optional packages (the interface) keep their own `_<name>_meta` on a model class |
| [Translations](translations.md) 🚧 | Translating the interface: the JSONC files per app and project, keeping manual edits when the models change, and the `generate`, `gather` and `check` commands (built; no page uses them yet) |
| [Zotero](zotero.md) 🚧 | `pangloss-zotero`: keeping a Zotero library in the database, one way (sync by version, a websocket watcher run as a background task, commands), brought over from the earlier plugin; built, not yet tried on the real Zotero |
| [Zotero items as sources and subjects](zotero-sources.md) 🚧 | How a Zotero item can be both the source of a factoid and what a factoid is about, as one node: the options, and what was decided and built |
| [History](history.md) ⏳ | A design for recording every version of a document or entity (best effort, in SQLite), and restoring one, including after the models have changed |
| [Dates and the calendar](dates.md) ⏳ | A design for two optional packages: uncertain dates, periods and recurrence with probabilities (`pangloss-dates`), and a calendar of days, observances and a background worker (`pangloss-calendar`) |
| [Database migrations](migrations.md) 🚧 | The design and progress of migrations: how changes to the models are applied to existing data. To use them, see the [user guide](../guide/migrations/README.md) |
| [Development](development.md) | Setting up, running tests, repository layout |
| [Status and roadmap](status.md) | What is and is not implemented |

Design notes that predate these docs live in [`../notes/modelling.md`](../notes/modelling.md) (how to model roles) and [`../packages/pangloss-models/todo.md`](../packages/pangloss-models/todo.md).
