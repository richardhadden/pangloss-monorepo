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

The space is stored as a node of its own (type `Negative`), connected to its contents through the `contents` relation, and read back the same way (`factoid.has_statement[0].type == "Negative"`, `.contents[0].type == "Statement"`). A space may hold another (`Doubt[Negative[Statement]]`). A space is never empty ([below](#how-many-items-a-space-holds-)).

## What a space says of its contents ✅

Built 2026-11-25, phase 2 of [the build plan](spaces-and-comparison-plan.md). Five options of `SemanticSpace.Meta(...)`
(`SemanticSpaceMeta`, `model_bases/semantic_space.py`) say how a space behaves, not what it is called, so a project's
own `Rumoured` or `Befehl` needs nothing of the core. The design and its reasons are in
[semantic-space-fields.md](semantic-space-fields.md) and [the report](semantic-spaces-formalisation.md).

| Option | Values | Left out | Says |
|---|---|---|---|
| `veridical` | `1` (the contents are asserted), `0` (neither asserted nor denied), `-1` (denied) | what `logical` implies: `-1` for `"not"`, else `0` | Whether what is inside is taken to be so |
| `fit` | `"describes"`, `"prescribes"` | `"describes"` | Whether the contents say how the world is, or how it is to be made (an order, a wish, a request) |
| `logical` | `"not"`, a `Modal(force, flavour, of_not=False)`, or `None` | `None` | Its logic, where it has one a program can use: a negation, or a modality |
| `unary` | `True`, `False` | what `logical` implies: `True` for `"not"` and for a modal with `of_not=True`, else `False` | Whether it holds one item only |
| `degree` | `"impossible"`, `"unlikely"`, `"possible"`, `"likely"`, `"expected"` (`DegreeStep`, `DEGREE_STEPS`), or `None` | `None` | How far its contents are taken to be so when nothing says otherwise of a statement: an order above a request. Only of a space whose contents are neither asserted nor denied |

**`Modal`** (exported from `pangloss_models`) is a frozen dataclass, written by position and checked: `force` is
`"necessity"` or `"possibility"`; `flavour` is the project's own word, one word with no space in it (`"epistemic"`,
`"command"`, `"deontic"`); `of_not=True` is a modality of the negation of the contents ("it is ordered that it not
be"). Two spaces are of one modality when their flavours are the same as written: `"command"` and `"Command"` are two
(a warning, below).

**Inherited**: a subclass inherits each option and may set any anew, so a family class can set them once.

**What is set and what holds are apart**: `veridical` and `unary` stay `None` where the class says nothing. The
properties `_meta.veridicality` and `_meta.is_unary` give what holds (what is set, or what `logical` implies); code
that reads a space uses them.

### An example ✅

```python
from typing import Annotated

from pangloss_models import Attribution, Document, Entity, Modal, SemanticSpace


class Person(Entity): ...


class Negative[T](SemanticSpace[T]):
    """The source says this is not so"""

    _meta = SemanticSpace.Meta(logical="not")


class Hypothetical[T](SemanticSpace[T]):
    """It may be so"""

    _meta = SemanticSpace.Meta(logical=Modal("possibility", "epistemic"))


class Ordered[T](SemanticSpace[T]):
    """Someone ordered that it be so"""

    _meta = SemanticSpace.Meta(
        logical=Modal("necessity", "command"), fit="prescribes", degree="expected"
    )


class Forbidden[T](Ordered[T]):
    """Someone ordered that it not be so"""

    _meta = SemanticSpace.Meta(logical=Modal("necessity", "command", of_not=True))


class Statement(Document):
    _meta = Document.Meta(abstract=True)


class Journey(Statement):
    traveller: Person


class Order(Statement):
    ordered_by: Person
    ordered_to: list[Person]
    thing_ordered: Annotated[
        Ordered[Statement], Attribution(by="ordered_by", to="ordered_to")
    ]


class Factoid(Document):
    statements: list[Statement | Negative[Statement] | Hypothetical[Statement]]
```

What holds, after `initialise()`:

| Space | `veridicality` | `fit` | `logical` | `is_unary` | `degree` |
|---|---|---|---|---|---|
| `Negative` | `-1` | `"describes"` | `"not"` | `True` | `None` |
| `Hypothetical` | `0` | `"describes"` | `Modal("possibility", "epistemic")` | `False` | `None` |
| `Ordered` | `0` | `"prescribes"` | `Modal("necessity", "command")` | `False` | `"expected"` |
| `Forbidden` | `0` | `"prescribes"` (inherited) | `Modal("necessity", "command", of_not=True)` | `True` | `"expected"` (inherited) |

`Forbidden` sets `logical` anew and inherits the rest. It is below `Ordered`, so `thing_ordered` takes it too (a
field takes the classes below a wrapper it names). What is forbidden is not denied: its `veridicality` is `0`, as for
what is ordered.

### Refused at `initialise()` ✅

`initialise_models/check_semantic_spaces.py` reads what a class sets (not what follows), and refuses a contradiction
with a `PanglossModelError` that begins with the class's name:

| Refused | Why (from the message) | Quick fix |
|---|---|---|
| `logical="not"` with `veridical` `0` or `1` | "what is under a 'not' is denied, so veridical can only be -1 (or left out)" | `space_veridical` |
| A possibility (`Modal("possibility", ...)`) with `veridical` `1` or `-1` | "what may be so is neither asserted nor denied, so veridical can only be 0 (or left out)" | `space_veridical` |
| A necessity that is not `of_not` with `veridical=-1` | "only what is necessarily not (a necessity with of_not=True) is denied, so veridical can only be 1 or 0 (or left out)" | `space_veridical` |
| A necessity `of_not=True` with `veridical=1` | "what is necessarily not is not asserted, so veridical can only be -1 or 0 (or left out)" | `space_veridical` |
| `unary=False` with `logical="not"` or a modal `of_not=True` | "of two items under a 'not', neither is denied by itself, so the space holds one item: unary can only be True (or left out)" | `space_unary` |
| `degree` on a space whose contents are asserted or denied (`veridicality` not `0`) | "a degree is only of contents neither asserted nor denied. Leave degree out" | `space_degree` |
| A `MinLen` of two or more on a unary space's `contents` (`initialise_field_definitions.py`) | "MinLen(2) asks for at least 2 items, but Negative holds one item only (...). Leave the MinLen out, or make it MinLen(1)" | none |

For example: `Never: logical='not' with veridical=0: what is under a 'not' is denied, so veridical can only be -1 (or
left out)`.

- **A class is refused only for what it says itself.** A fault it inherits whole is reported of its parent alone; a
  subclass that sets one value against an inherited one is refused by its own name (`class Denied[T](Negative[T])`
  with `veridical=1`). A parametrisation (`Negative[Person]`) is not checked: its generic class is.
- **The fixes** (`diagnostics.FIXES`; offered by the [language server](language-server.md)) edit a keyword of the
  class's own `_meta = ...Meta(...)` and never change `logical`: "Leave out" where the class would then inherit `None`
  or the right value, else "Change to", or "Add" where the value is inherited. A class with no `_meta` of its own gets
  no fix.
- **A warning, not a refusal**: two flavours that differ only in case (`PanglossModelWarning`, at the `_meta` of the
  first class by name, no fix): "The flavours 'Command' and 'command' of Modal differ only in case, and so are
  different modalities ('Command' by Requested; 'command' by Ordered). Write them alike if they are to be one".

### How many items a space holds ✅

- **A space is never empty** (the user, 2026-11-25): every space's `contents` has `MinLen(1)` in its field definition
  (`limit_contents`), unless the class's own `MinLen` is one or more. `Create`, `Update` and the database models
  refuse an empty list first with "Hypothetical holds nothing: a semantic space has at least one item" (pydantic's
  error type `too_short`). The read models have the length too: a stored empty space would not be read.
- **A unary space holds exactly one**: `MaxLen(1)` as well, and a second item is refused with "Negative holds one item
  only (it is unary: of two items under a 'not', neither is denied by itself)" (for a `"not"` or a modal `of_not`) or
  "X holds one item only (it is declared unary=True)" (`too_long`). A class's own larger `MaxLen` becomes one; a
  `MinLen` of two or more is refused (above).
- **A space that is not unary may hold several items, and they are read each by itself, never together** (the user,
  2026-11-25). `Hypothetical` holding A and B says that A may be so and that B may be so, not that A and B together
  may be. Where the difference matters (a possibility, a degree), or where one item's degree or attribution differs
  from another's, give each item a space of its own. A `"not"` is unary for this reason: not (A and B) is not the same
  as (not A) and (not B).
- The lengths are exported among the validators of `contents` (`{"name": "MinLen", "min_length": 1}`, and
  `{"name": "MaxLen", "max_length": 1}` for a unary space), as for a list annotated so.

### Whose a space is: `Attribution` ✅

`Attribution(by=..., to=...)` (`markers.py`, exported from `pangloss_models`) marks the field that holds a space with
the names of two other fields of the class: `by`, the field that says whose attitude or act it is (who orders,
believes, reports); `to`, the field that says whom it is addressed to (who is ordered, asked; left out for a belief).
In the example: `thing_ordered: Annotated[Ordered[Statement], Attribution(by="ordered_by", to="ordered_to")]`.

Checked at `initialise()` (`initialise_models/check_attributions.py`), each refusal at the field:

- one marker on a field, naming `by`, `to` or both ("Attribution() names no field. Give `by` (whose attitude or act it
  is), `to` (whom it is addressed to), or both");
- the marked field is a relation with a semantic space among its top-level options (directly, in a list, or in a
  union; a space only inside a reified relation does not count);
- each named field is another field of the class (a misspelt name is underlined, with "Did you mean 'ordered_by'?")
  and a relation that reaches an entity, directly or behind wrappers as search reaches them (`InRole[Person]`). Any
  entity will do: there is no notion of an agent. A field that reaches only documents is refused.

`by` and `to` may name one field; several fields of a class may each have a marker. A subclass in which a named field
no longer reaches an entity is refused by its own name. Readers: `pangloss_models.markers.attribution_of(definition)`
and `attributions(model)` (inherited fields included).

### Exported, and not data ✅

- **The export** (`export.export_space`) gives a semantic space `veridical` and `unary` as they hold (never null),
  `fit`, `logical` (null, `{"not": true}` or `{"force", "flavour", "ofNot"}`) and `degree` (a step or null); a field
  with an `Attribution` has `attribution`: `{"by": {"name", "key"} | null, "to": ...}` (`export_attribution`). The
  TypeScript types are in `interface-core/src/types/models.ts` (`Veridical`, `SpaceFit`, `DegreeStep`, `SpaceLogical`,
  `FieldAttribution`). Nothing in the interface reads them yet.
- **Not data**: none of this changes what is stored. The migrations' snapshot leaves the five keys out of a semantic
  space's entry and `attribution` out of a field's (`migrations/snapshot.py`, `SPACE_KEYS`, `FIELD_KEYS`), so a change
  of any of them makes no migration and leaves the hash as it was. The lengths of `contents` are validators, which are
  not in the hash either.

### Not built yet ⏳

- A degree entered on a statement, the field marker `Degree()` (step 2.7).
- Anything that reads these options: the walk over a node's path to what holds of it (phase 3), the packages that
  read spaces (derived, criteria, identity claims, RDF: phase 4, each to be decided), the vector parts (phase 5) and
  comparison (phase 6). Until then a space's options change no behaviour but the length of its `contents`.
- Fulfilment, which reads `Attribution` (step 6.2).
- The interface drawing any of it (phase 7).

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
- What a space says of its contents, pure, in `pangloss-models`: `tests/test_semantic_space_fields.py` (the options, inheritance, `Modal`), `tests/test_check_semantic_spaces.py` (each refusal by its message and its fix, the warning), `tests/test_space_contents_length.py`, `tests/test_space_export.py`, `tests/test_attribution.py`, the migration diff's cases (`test_migration_diff.py`) and the stubs (`tests/typestubs/test_space_meta_stubs.py`, `test_attribution_stubs.py`); in `pangloss-cli`, `test_check_command.py` (the diagnostics and fixes).
- The interface: `api/context.ts`'s functions and `ContextFrames` in Vitest; the field said on a nested page in e2e (`test_keys_and_nesting.py`, `test_fields_and_wrappers.py`).
