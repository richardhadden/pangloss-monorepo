# Semantic spaces and the path of a node ✅

## Semantic spaces

A `SemanticSpace[T]` subclass wraps content in a named context that changes how the content should be read, for example `Negative[Statement]` ("it is *not* the case that...").

```python
class Negative[T](SemanticSpace[T]): ...


class Hypothetical[T](SemanticSpace[T]): ...


class Factoid(Document):
    has_statement: list[Statement | Negative[Statement]]
```

A payload looks like:

```python
Factoid(
    label="F",
    has_statement=[
        {
            "type": "Negative",
            "contents": [{"type": "Statement", "label": "S", "text": "..."}],
        },
    ],
)
```

The space is stored as a node of its own (type `Negative`), connected to its contents through the `contents` relation, and read back the same way (`factoid.has_statement[0].type == "Negative"`, `.contents[0].type == "Statement"`). A space may hold another (`Doubt[Negative[Statement]]`).

## What is recorded ✅

When an instance is turned into its `CreateDB` or `UpdateDB` form, every node below the head is given two values, written in its `meta`, so that a node can be placed and filtered without walking up the tree:

- **`meta.path`**: the nodes it is nested in, from the head down to the node that holds it. Each entry is a `PathEntry` (exported from `pangloss_models`), `{kind, type, id, field}`:
  - `kind` is `document`, `entity`, `space`, `reified`, `conjunction` or `embedded`;
  - `field` is the relation of that node through which the next entry, or the node itself, is held (`statements`, `contents`, `cause`, `result`...).
- **`meta.semantic_spaces`**: the types of the spaces of the path, outermost first (`["Doubt", "Negative"]`), made from the path by `pangloss_models.context.spaces_of`. This is what queries filter by: search's `$spaces`, derived rules' blocked spaces. (The RDF export's `pgo:inSpace` comes from its own walk of the document, not from the stored value.)

**The rule**: a child's path is its parent's path and the parent. Nothing is shared between nodes or passed along between siblings, so the order of a class's fields does not matter, a node is never on its own path, and one sibling is never on another's. Every node on the way is on the path, whatever its class (reified relations, conjunctions and embedded objects too; embedded objects are followed, and have paths of their own).

- The head's path is empty, and `path[0]` of everything below it is the head.
- An entity belongs to no document: its path is empty wherever it is met, and what an entity holds (a reified relation on its own field) has a path that starts with the entity (`kind: "entity"`).
- A space has a path, like any other node, and is in the spaces outside it.
- A document in the context of what follows it (the cause of a `Causes`, for its result) is not recorded: a result is not in its cause's spaces and does not have its cause on its path. Should a page need it, it is to be declared on the conjunction and worked out by the view (decision D13 of [the build plan](spaces-and-comparison-plan.md)) ⏳.

The algorithm is one function, `pangloss_models.context.propagate_context`, given a view of the nodes it works on: `_InstanceContext` (`model_bases/instance_context.py`) for an instance about to be written, and the migrations' `StoredContext` for nodes that are stored. On a `CreateDB` or `UpdateDB` instance the path is the field `context_path` (a reserved field name; a project's class may have a field `path`); in `meta`, stored and read, it is `path`. The reads give it in an item's meta (read alone, in lists, and in the incoming relations).

### An example

```python
class Person(Entity): ...


class When(Embedded):
    year: int


class InRole[T](ReifiedRelation[T]):
    when: When


class Doubt[T](SemanticSpace[T]): ...


class Negative[T](SemanticSpace[T]): ...


class Statement(Document):
    people: list[InRole[Person]]


class Factoid(Document):
    statements: list[Statement | Doubt[Negative[Statement]]]
```

A factoid `F` with two statements: `S1` asserted, and `S2` inside `Doubt` `D` inside `Negative` `N`; `S2` names a person `P` through an `InRole` `R`, which has a `When` `W`. Each entry is written `kind Type.field`:

| Node | `meta.path` | `meta.semantic_spaces` |
|---|---|---|
| `F` (the head) | (none) | `[]` |
| `S1` | `document Factoid.statements` | `[]` |
| `D` | `document Factoid.statements` | `[]` |
| `N` | `document Factoid.statements`, `space Doubt.contents` | `["Doubt"]` |
| `S2` | `document Factoid.statements`, `space Doubt.contents`, `space Negative.contents` | `["Doubt", "Negative"]` |
| `R` | the same, then `document Statement.people` | `["Doubt", "Negative"]` |
| `W` | the same as `R`'s, then `reified InRole.when` | `["Doubt", "Negative"]` |
| `P` (an entity) | `[]` | `[]` |

Each entry also has the node's `id`. `S1` and `S2` are siblings and neither is on the other's path. `N` is in `Doubt`, the space outside it; `D` is in nothing.

## Storage ✅

- **Memgraph** stores `meta` as a map property, the path in it as a list of maps.
- **Neo4j** cannot hold a list of maps as a property: the path is JSON text, `meta.path#json`, with `meta.path_types` (the types on the path) flat beside it for a migration's rename. A read query gives the path through `Dialect.meta_entry(node, "path")`, which names the entry so that it is read back as the list on either backend ([Neo4j](neo4j-implementation.md)).
- **Migrations**: every operation that puts a node on a path, takes one off, or changes a name that is in paths ends with `recompute_contexts` for the heads it touched: wrapping and unwrapping (in a reified relation or a space), `change_wrapper`, `literals_to_embedded` (and so `add_embedded`), a renamed relation, and a renamed class (the heads found by `meta_mentions`, which looks in the path) ([migrations](migrations.md)).
- Data stored before the path was recorded (2026-11-25) is not carried over: such a database is made again. There is no migration of it.

## What the interface shows ✅

The interface reads the path in `interface-core`'s `api/context.ts`:

- **A row of a list and an item's console** show the spaces the item is in (`wrappingSpaces`, the meta's `semanticSpaces`).
- **A nested document's own page** (`Item.tsx`, `ContextFrames`) has, beside "Contained in" and the head's chip, a band for each space and a frame for each document of the path after the head, outermost first, each linked (`contextPath`). A document's frame names its field that holds what follows, as a field is named on a page; the head's field is named beside "Contained in".
- **A chip of a nested item** (`ItemContents.tsx`, `SpaceBands`) has bands of the same, by name (`contextTrail`); no field is said there.

Reified relations, conjunctions and embedded objects on the path are passed over. `use_in_semantic_space_label=False` on a document class (exported as `useInSemanticSpaceLabel`) leaves a nested document of that class out of these trails; a class the interface's models do not know is kept. The flag is for display only: storage does not read it, and the path has every node. In the example, `S2`'s page shows "Contained in `F`" (field `statements`) and the bands `Doubt` and `Negative`; `R`'s shows those and the frame of `S2`, naming its field `people`.

How a band shows what kind of space it is (each has a colour of its own today) is to be decided later ([the build plan](spaces-and-comparison-plan.md), D17) ⏳.

## Conjunctions

`Conjunction` subclasses work similarly as generic wrappers (`Causes[Statement, Statement]` has `cause` and `result` slots) and are likewise stored as nodes (with their slots such as `cause` and `result` as relations). A conjunction is on the path of what it holds (`kind: "conjunction"`, `field` the slot), but it is not a space and adds nothing to `semantic_spaces`. They are declared and generate models; see [Defining models](models.md#conjunction).

## Tests

- Pure, in `pangloss-models`: `tests/test_context_path.py` (the algorithm on plain objects, and the shapes that were wrong before 2026-11-25 on the models' instances: two single slots each in a space, a list after a single relation that holds a space, a bare result after a negated cause, a space inside a cause, a space's own path).
- Conformance, on both backends: `test_stored_path.py` (create, update, read back, listed and read alone), and after every conformance test a check that each nested node's path is its parent's path and its parent, by the edges alone (`conftest.paths_are_true`, `helpers.assert_paths_true`); `test_migrations_context.py` (a recomputation of what the models wrote changes nothing).
- The interface: `api/context.ts`'s functions and `ContextFrames` in Vitest; the field said on a nested page in e2e (`test_keys_and_nesting.py`, `test_fields_and_wrappers.py`).
