# Overview

## The idea

You describe your research data (people, statements, events, places, and how they relate) as Python classes. Pangloss then:

1. **Registers** every class as it is defined.
2. **Initialises** all of them at once with `pangloss_models.initialise()`. This inspects the fields and generates a family of Pydantic models for each class (one for creating, one for updating, one for viewing, and so on).
3. **Persists** to a graph database through a pluggable backend. Memgraph is the only real backend so far.

```python
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.entity import Entity


class Person(Entity):
    pass


class Statement(Document):
    text: str
    was_carried_out_by: Person


initialise()  # generates Person.Create, Statement.Create, Statement.View, ...

st = Statement.Create(
    label="A statement",
    text="...",
    was_carried_out_by={"type": "Person", "id": some_uuid},
)
saved = await st.save()  # writes to the configured database
loaded = await Statement.get(saved.id)  # reads it back as Statement.HeadView
```

`initialise()` needs a `BaseSettings` instance to exist first, because it reads `DATABASE_MODULE` to decide which backend to bind `save`, `get` and `list` to. See [Settings](settings.md).

## Using the models from outside the project

`DATABASE_MODULE` can also be one whose functions are **requests to the project's API**. `pangloss sdk build` (with `pangloss_sdk_server` installed) makes a package of the project's models and their type stubs, which the server hands out (`pip install` of a wheel, or `git clone` of a read-only repository, for an admin). A script, a notebook or another service installs it with `pangloss-sdk` (no database driver, no web framework), and `Person.get(...)`, `Factoid.Create(...).save()` and the rest are the same code as on the server, doing HTTP: the login is asked for when a request needs one, and the server says when the SDK is out of date. See [the SDK](sdk.md), and `sdk-demo/` for a script that does it.

## Core concepts

- **Declared classes** are the classes you write: `Document`, `Entity`, `Embedded`, `ReifiedRelation`, and so on. See [Defining models](models.md).
- **Action classes** are generated from declared classes: `Statement.Create`, `Statement.View`, and so on. Every action class has an `_owner` (the declared class) and shares its `_meta`. See [Generated models](generated-models.md).
- **Head nodes.** A `Document` or `Entity` is a top-level, independently addressable object. Documents may contain nested documents and relate to entities. The top-level one is the *head node*; the nested ones record its type and id as `head_node_type` / `head_node_id`.
- **Graph storage.** Only literal values (strings, numbers, dates, lists of these) are stored as node properties. Everything else (documents, entities, embedded objects, reified relations, semantic spaces, conjunctions) is stored as a node, and every relation field becomes a pair of edges (forward and reverse). See [Memgraph backend](memgraph.md).

## Data flow for a write

```
user dict / kwargs
      │  validate
      ▼
 Statement.Create ──_to_db_model()──► Statement.CreateDB
                                           │  assign ids, labels,
                                           │  semantic spaces, context labels
                                           ▼
                                  build_head_create_query()
                                           │  one Cypher statement
                                           ▼
                                       Memgraph
                                           │
                       ReferenceView (default) or HeadView ◄─ detail
```

## Data flow for an update

An update replaces the whole document, rather than working out what changed. In one transaction: check the document exists, that everything it refers to exists, and that the ids it uses are free; then delete everything below the head node (never entities), and write the new version in the same way as a creation. See [Memgraph backend](memgraph.md#update_head_nodeinstance-detailfalse-).

## Data flow for a read

`Statement.get(id)` runs a Cypher query that walks outward from the node, collects paths to entities and nested documents, makes them into a tree, adds `meta`, and validates the result as `Statement.HeadView`.
