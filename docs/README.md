# Pangloss Documentation

Pangloss (*Prosopography and Network Graph Labyrinth Orientation System*) v3 is a modular rewrite of the original Pangloss. You declare a data model as Python classes, and Pangloss generates the validated input/output models for it and stores the data in a graph database.

Each feature in these docs is marked with its status:

| Marker | Meaning |
|--------|---------|
| ✅ Implemented | Works and has tests |
| 🚧 Partial | Some of it works; the gaps are described |
| ⏳ Planned | Not implemented yet (stub, `TODO`, or only mentioned in a description) |

## Contents

| Document | What it covers |
|----------|----------------|
| [Overview](overview.md) | What Pangloss is for and how a model becomes stored data |
| [Packages](packages.md) | The five workspace packages and how they depend on each other |
| [Defining models](models.md) | Documents, Entities, Embedded, Traits, EdgeModels, and the other model kinds |
| [Relations and fields](relations.md) | Literal fields, relations, `ViaEdge`, `RelationConfig`, field binding, `Fulfils` |
| [Generated models](generated-models.md) | The `Create`, `CreateDB`, `Update`, `UpdateDB`, `View`, `HeadView` and reference models, and the initialisation pipeline |
| [Semantic spaces and context labels](semantic-spaces.md) | How nesting inside `SemanticSpace` wrappers is tracked |
| [Memgraph backend](memgraph.md) | Graph schema, query builders, and the database API |
| [Settings](settings.md) | `BaseSettings` and database settings |
| [Users](users.md) | User models, passwords and the `service` functions |
| [REST API](api.md) | Authentication and the user endpoints |
| [Command line](cli.md) | The `pangloss` command, and adding commands from apps |
| [Development](development.md) | Setting up, running tests, repository layout |
| [Status and roadmap](status.md) | What is and is not implemented |

Design notes that predate these docs live in [`../notes/modelling.md`](../notes/modelling.md) (how to model roles) and [`../packages/pangloss-models/todo.md`](../packages/pangloss-models/todo.md).
