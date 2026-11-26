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

from pangloss_models import (
    Attribution,
    Degree,
    DegreeStep,
    Document,
    Entity,
    Modal,
    SemanticSpace,
)


class Person(Entity): ...


class Negative[T](SemanticSpace[T]):
    """The source says this is not so"""

    _meta = SemanticSpace.Meta(logical="not")


class Hypothetical[T](SemanticSpace[T]):
    """It may be so"""

    _meta = SemanticSpace.Meta(logical=Modal("possibility", "epistemic"))
    how_likely: Annotated[DegreeStep | None, Degree()] = None


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

`Hypothetical` has a field of its own, `how_likely`, which whoever writes the factoid fills in for each hypothesis
([below](#a-degree-entered-on-a-space-degree-)); the `degree` of the table is the class's default, and it has none.
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

### A degree entered on a space: `Degree()` ✅

Built 2026-11-25 (step 2.7; decision D16). The class's `degree` is a default for every space of the class; how likely
*this* hypothesis is, the person who enters it says, on a field the project declares and marks `Degree()`
(`markers.py`, exported from `pangloss_models` with `DegreeStep` and `DEGREE_STEPS`):

```python
class Hypothetical[T](SemanticSpace[T]):
    _meta = SemanticSpace.Meta(logical=Modal("possibility", "epistemic"))
    how_likely: Annotated[DegreeStep | None, Degree()] = None
```

- **An ordinary literal field** of the space: stored as a property of the space's node, versioned with the document,
  in its history, refused as any literal is when it is not one of the five steps. A space class without such a field
  has none, and no migration.
- **Written into the path**: the marker says the field's value is the space's degree, and the degree goes into **the
  space's entry** of the path of everything the space holds, `{kind: "space", type, id, field, degree: "likely"}`
  (`PathEntry.degree`, not required), so that what reads a node's path has it without a query. It is in that entry
  only: not in the space's own path, nor in the entries of the statements below it. A space in a space: each entry
  has its own. The key is absent where the value is `None`, and on a class with no marked field. **The class's
  default (`Meta(degree=...)`) is not written** into the path: a reader takes the entry's degree where there is one,
  else the class's ([where a statement's degree comes from](spaces-and-comparison-plan.md), R9).
- **Checked at `initialise()`** (`initialise_models/check_degree_fields.py`, after `check_attributions`), each a
  `PanglossModelError` (no quick fix):

  | Refused | The message |
  |---|---|
  | `Degree()` on a field of a class that is not a semantic space | "Rumour.how_likely: Degree() is for a field of a semantic space class (the degree of what the space holds), and Rumour is not one" |
  | More than one marked field on a class, those it inherits counted | "TwiceLikely: 2 fields are marked Degree() (how_likely, how_sure): a space has one degree, so one field at most is marked" |
  | A marked field that is not `DegreeStep` or `DegreeStep \| None` (a `Literal` of exactly the five steps, in any order) | "WrongDegree.how_likely: Degree() is on a field of the type str, and a degree is one of the five steps 'impossible', 'unlikely', 'possible', 'likely', 'expected'. Write \`how_likely: Annotated[DegreeStep \| None, Degree()] = None\` (\`DegreeStep\` from pangloss_models), or \`DegreeStep\` alone for a degree always given" |
  | On a space whose contents are asserted or denied (`veridicality` not `0`), as the class's `degree` is | "Reported.how_likely: Degree() on a space whose contents are asserted (veridical=1): a degree is only of contents neither asserted nor denied. Take Degree() off the field, or the field out" |

  As for the options, a class is refused only for what it says itself: a fault its parent has too is the parent's;
  a subclass that adds a second marked field, or becomes a `"not"` with the field inherited, is refused by its own
  name (at the field it declares, else at its `_meta`).
- **Exported** as any literal field: the field with `"markers": [{"name": "Degree"}]`; the interface's `PathEntry`
  (`interface-core/src/api/types.ts`) has `degree?: DegreeStep`.
- **Not data beyond the field**: adding the field is an added literal field (a migration, as any). Putting the marker
  on a field that is there already, or taking it off, makes no migration (markers are not in the snapshot); paths
  written before have no `degree` until their document is written again (by D18 nothing stored is carried over), and
  are read as they are. A migration that works the paths out again (`recompute_contexts`) keeps each space's degree,
  taken from the paths stored before: a migration's state does not say which field is marked.
- **Read by the walk** (`signature`, step 3.1): the entry's degree, else the class's default.
- **Drawn beside the space's head** (step 7.3) ✅: on the item page the step entered, in words (`degree_likely`...),
  else the class's default, muted ("expected (default)"), else nothing; in the form a small menu in the head's bar
  (`MenuSelect`: the five steps and an empty choice that says the default, or "No degree"), in place of a row, with
  what is wrong with it said beside it. A space with no head (`InterfaceMeta(headless=True)`) keeps it as a row, its
  pills in words. A space's other fields of its own are shown under what it holds, on the page and in the form.

### Exported, and not data ✅

- **The export** (`export.export_space`) gives a semantic space `veridical` and `unary` as they hold (never null),
  `fit`, `logical` (null, `{"not": true}` or `{"force", "flavour", "ofNot"}`) and `degree` (a step or null); a field
  with an `Attribution` has `attribution`: `{"by": {"name", "key"} | null, "to": ...}` (`export_attribution`). The
  TypeScript types are in `interface-core/src/types/models.ts` (`Veridical`, `SpaceFit`, `DegreeStep`, `SpaceLogical`,
  `FieldAttribution`). The interface's port of the walk reads them (`schema/spaces.ts`, `spaceFacts`, step 7.3).
- **Not data**: none of this changes what is stored. The migrations' snapshot leaves the five keys out of a semantic
  space's entry and `attribution` out of a field's (`migrations/snapshot.py`, `SPACE_KEYS`, `FIELD_KEYS`), so a change
  of any of them makes no migration and leaves the hash as it was. The lengths of `contents` are validators, which are
  not in the hash either.

### Not built yet ⏳

- Any other package that reads the walk: criteria's `$derived` (step 4.2, which waits for `$derived` in stored
  criteria, not built: step 13 of [matches criteria](matches-criteria.md)), the graph part and the parts after it
  (phase 5, 5.3 on) and comparison (phase 6). These follow it (2026-11-25): derived (each justification has a status
  by the walk, the derivation follows it, and a fact's status is summed up: [derived.md](derived.md#through-semantic-spaces-how-a-justification-holds-));
  identity clusters (a claim asserted joins, one denied is "said to be different":
  [entity-identity.md](entity-identity.md)); the RDF export (what is asserted has its direct triples:
  [rdf.md](rdf.md#shape-of-the-data-)); and (2026-11-26) the time part of similarity (a date whose holder is denied
  counts for nothing; the degree of what is prescribed is not weighed: [dates-vectors.md](dates-vectors.md#whose-vector-a-date-is)). Elsewhere a space's options change no behaviour but the length of its
  `contents`, and what `signature` gives.
- Fulfilment, which reads `Attribution` (step 6.2).
- In the interface (phase 7): the rest of phase 7 after 7.3b. Built with 7.3: the walk in TypeScript, the mark of
  what is not asserted, and the degree beside a space's head; with 7.3b, a pattern over a band by the kind of space
  ([below](#what-the-interface-shows-)).
- A judgement of a statement made outside its entry (an `Expectation`, a rule's proposal: phase 8).

## The ground: what a head says of what it holds ✅

Built 2026-11-26, steps 3.4 and 3.5 of [the build plan](spaces-and-comparison-plan.md#the-ground-of-a-head-class).
A space says something of what it holds; the **ground** is what the class of a head (a document or an entity) says of
everything it holds outside any space. A relation an entity holds itself (a person's date of birth) is in a sense true
by definition: it is what the record says. A statement directly in a factoid is what the factoid's source says. Both
are asserted, so the difference is **not on the truth axis**: it is **whose commitment it is, and whether it can be
contradicted** (decision G1 of the user). The walk starts from the ground in place of a plain "asserted".

```python
from pangloss_models import Document, Entity, Ground


class Source(Entity): ...


class Person(Entity):
    born: Date | None = None  # the record: an entity's default ground


class Factoid(Document):
    _meta = Document.Meta(ground=Ground(by="source"))  # a claim, the source's
    source: Source
    statements: list[Statement | Negative[Statement]]


class Rumour(Document):
    _meta = Document.Meta(ground=Ground(veridical=0, degree="possible"))
    statements: list[Statement]
```

`Ground(...)` (`model_bases/ground.py`, exported from `pangloss_models`) is a frozen dataclass, written with keywords
only, so a value of the wrong type is refused where it is written. It is given as `ground=` of `Document.Meta` or
`Entity.Meta`:

| Option | Values | Left out | Says |
|---|---|---|---|
| `veridical` | `1` (what the head holds is asserted), `0` (neither asserted nor denied: a rumour) | `1` | As a space's, so that the walk treats the ground as the outermost thing said. A ground does not deny: `-1` is refused (below) |
| `fit` | `"describes"`, `"prescribes"` | `"describes"` | As a space's: with `"prescribes"`, everything the head holds is prescribed, by the head |
| `degree` | one of the five steps (`DegreeStep`), or `None` | `None` | How far what the head holds is taken to be so. Only with `veridical=0` |
| `by` | the name of a field of the class | `None` | Whose commitment what the head holds is (a factoid's source): a relation of the class that reaches an entity, as for [`Attribution(by=)`](#whose-a-space-is-attribution-) |
| `standing` | `"claim"` (it can be contradicted by another claim), `"record"` (what claims are held against) | `"claim"` for a document, `"record"` for an entity | What kind of commitment it is |

- **By class only** (G2): no field of an item changes its ground. A forged charter is said so by a space, or is of a
  class of its own.
- **Inherited**: a subclass has its parent's ground and may set its own (whole: a `Ground` is not merged with the
  parent's).
- **It counts only where an item of the class is the head**: a nested document has its head's ground, whatever its
  own class says. A `ground` on a class that is never a head (`create_directly=False`) is allowed and says nothing.
- **A class that says nothing reads as before**: asserted, with its kind's standing. `_meta.ground` keeps what was
  written (`None` where nothing was); `pangloss_models.model_bases.ground.ground_of(model)` gives what holds, never
  `None`, with the standing filled in by kind.

### Refused at `initialise()` ✅

`initialise_models/check_grounds.py`, each a `PanglossModelError` that begins with the class's name and
`Ground(...)` as written:

| Refused | The message | Quick fix |
|---|---|---|
| `veridical=-1` | "a ground does not deny what its class holds. Give veridical=0 (neither asserted nor denied), or say what is denied in the document, with a semantic space that is a 'not'" | none |
| `degree` with `veridical=1` | "but what the class holds is asserted (veridical=1): a degree is only of what is neither asserted nor denied. Leave degree out, or give veridical=0" | `ground_degree` |
| `by` on a record (`standing="record"`, or an entity that gives no standing) | "on a record (standing='record'): the record is what claims are held against, and is no one's. Leave by out, or give standing='claim'" (for an entity: "Legend is an entity, whose ground is the record unless it says standing='claim'") | none |
| `by` naming no field of the class | "Factoid has no field 'sorce'. Did you mean 'source'?" (the name underlined) | none |
| `by` naming a field that is not a relation, or a relation that reaches only documents | "Factoid.source is not a relation. It must be a relation that reaches an entity, whose commitment what the class holds is (`Source`, `Person \| None`, or through a reified relation: `InRole[Person]`)" | none |

- **The fix `ground_degree`** leaves `degree` out of the `Ground(...)` written in the class's own `_meta`, and the
  rest of it as written; the only refusal whose fix is plain.
- **The values are checked where a class sets them**: a class whose ground is its parent's is not refused for it
  again. **`by` is checked on every class that is not abstract**, the inheriting ones too, so an abstract base may
  name a field its subclasses declare, and a subclass without it (or in which it no longer reaches an entity) is
  refused in its own name.

### Exported, and not data ✅

- **The export** (`export.export_ground`) gives every model of kind `Document` or `Entity` its `ground`, as it holds
  and never null: `{"veridical": 1 | 0, "fit", "degree", "by": {"name", "key"} | null, "standing": "claim" |
  "record"}`. No other kind has one. The TypeScript types are `GroundDefinition` and `Standing` in
  `interface-core/src/types/models.ts`.
- **Not data**: nothing stored changes. The migrations' snapshot leaves `ground` out of a model's entry
  (`migrations/snapshot.py`, `HEAD_KEYS`), so a change of it makes no migration and leaves the hash as it was.

## The walk: what a path says of a node ✅

Built 2026-11-25, phase 3 of [the build plan](spaces-and-comparison-plan.md). `pangloss_models.spaces.signature(path)`
reads a node's path ([below](#what-is-recorded-)) and what each space class on it says of its contents, and gives a
`Signature`. It reads no database, and nothing it gives is stored: a change of a space's `Meta` changes what the walk
gives and needs no migration.

```python
from pangloss_models import spaces

factoid = await Factoid.get(some_id)
statement = factoid.statements[0].contents[0]
said = spaces.signature(statement.meta.path)
said.veridical      # 1 asserted, -1 denied, 0 neither
```

| Of a `Signature` | |
|---|---|
| `veridical` | `1`: the node is asserted; `-1`: denied; `0`: neither |
| `lean` | Where `veridical` is `0`: `"for"`, `"against"` or `"neither"`. `None` where it is not `0` |
| `degree` | Where it leans for or against: how far, one of the five steps. The degree entered on the innermost space that leaves its contents neither (in its entry of the path), else that class's default (`Meta(degree=...)`), else `None`. An outer space's degree is never taken in its place |
| `fit` | `"prescribes"` where any space of the path prescribes its contents, else `"describes"` |
| `prescribed_by` | The id of the node that holds the innermost space that prescribes: the order, of what is ordered |
| `force`, `flavour` | Of the innermost modality of the path as normalised |
| `standing` | Of the head's [ground](#the-ground-what-a-head-says-of-what-it-holds-): `"claim"` or `"record"`. `None` where the path has no ground |
| `grounded_by` | Where the head's ground has a `by`: `GroundedBy(head, field, key)`, the head's id (`None` for the head itself), the field `by` names and its key in the API's JSON. `None` where the ground names no one |

`as_json()` gives them as `standing` and `groundedBy`.

**In two steps.**

1. **Normalising** (`spaces.normalise`, a reading of the path, never what is stored). In each run of spaces next to
   each other, a "not" is moved as far in as it can go: two cancel; one passes a modality by turning it into its dual
   of the same flavour (not possible = necessarily not, not necessary = possibly not); a modality `of_not` is that
   modality of a "not". A "not" passes nothing else: no space that is not a modality, and no statement.
2. **Walking**, from the outside, with a sign that starts from the head's ground ("From the ground", below):
   asserted, unless the head's class says that what it holds is neither asserted nor denied (a statement nested with
   no space in a head that says nothing is asserted). A space that asserts its contents keeps the sign and a denial turns it. Once it is denied, anything
   further in, a space or a statement, leaves the node neither and leaning neither way. At the first space that
   neither asserts nor denies, the node is neither, and the walk goes on only for the lean: for, until a denial
   turns it against, and anything further in than that leaves it leaning neither way.

**Three examples**, with the spaces of [the example above](#an-example-) and a `Must` that commits
(`Meta(logical=Modal("necessity", "epistemic"), veridical=1)`):

| The path of p | `veridical` | `lean` | Why |
|---|---|---|---|
| `Negative[ChurchService(parts=[p])]` | `0` | neither | There was no such service, which says nothing of its parts. `semantic_spaces` of p is `["Negative"]`, which read alone would say p was denied: only the path has the statement in between |
| `Order(thing_ordered=Ordered[Negative[p]])` | `0` | against | Ordered not to. `fit` is `"prescribes"`, `prescribed_by` the order's id, `degree` the one entered on the `Ordered`, else `"expected"`, its class's default |
| `Negative[Hypothetical[p]]` | `-1` | | "It cannot have been so" is read as `Must[Negative[p]]`, and this project's `Must` commits. With no committing necessity of the flavour declared: `0`, leaning against. `force` is `"necessity"` either way |

**What follows from the options.**

- A modality as written commits the source where its class says so (`veridical=1`, or `-1` on one `of_not`). A
  **dual**, which no entry of the path wrote, is of no class: a possibility never commits; a necessity commits where
  the project has declared a necessity of that flavour and every one it has declared commits (abstract classes not
  counted). Its degree is that of the space as written.
- **Two flavours are never rewritten into each other**: the dual of a deontic modality is deontic, and whether it
  commits is asked of the deontic classes only.
- A space that denies its contents and is no "not" (`Meta(veridical=-1)` with no `logical`: a `Doubted`) turns the
  sign as a "not" does and is rewritten with nothing: two of them leave the node neither.
- Any node that is not a space counts as a statement: a document, a reified relation, a conjunction, an embedded
  object.
- A space says something of its `contents` only. What it holds in a field of its own (who reported it, an embedded
  date) is held as by a statement: the space is a statement in that node's path. (`meta.semantic_spaces` of such a
  node still names the space.)
- A path that names a space class the models do not have raises `spaces.UnknownSpaceError`.

**From the ground.** `spaces.signature(path, spaces=None, grounds=None, head=None)` starts from the
[ground](#the-ground-what-a-head-says-of-what-it-holds-) of the head (`spaces.ground_at(path, grounds, head)`). The
path given must be whole: its first entry is taken to be the head, and the ground is that of its class. For the head
itself (what it holds in its own fields, a person's `born`), whose path is empty, `head=` names its class
(`signature([], head="Person")`); what an entity holds on a reified relation of its own has a path that begins with
the entity. `grounds` is the ground of each head class in the export's shape
(`GroundFacts`); left out, it is read from the models.

| The head's ground | The path of p | `veridical` | `lean` | `degree` |
|---|---|---|---|---|
| `Ground(veridical=0, degree="possible")` (a rumour) | `Rumour.statements` | `0` | for | `"possible"` |
| the same | `Rumour.statements`, `Negative` | `0` | against | `"possible"` |
| the same | `Rumour.statements`, a plain space that leaves its contents neither (`Reported`) | `0` | for | the `Reported`'s own (entered, else its class's), here `None` |

- **A ground of `veridical=0`** starts the walk as the first space that leaves its contents neither would: leaning
  for, at the ground's degree. The rest is the walk as it was: a denial inside leans against, at the ground's degree;
  a space inside that leaves its contents neither has its own degree, and the ground's is never taken in its place
  (as an outer space's is not). A ground is no operator: nothing is normalised with it.
- **A ground that prescribes** (`fit="prescribes"`) makes everything the head holds prescribed, `prescribed_by` the
  head's id (`None` for the head itself); a space further in that prescribes takes its place.
- **Whose a statement is**: `grounded_by` gives the head's id and the field its ground's `by` names; the caller reads
  that field of the head (the factoid's `source`). The walk reads no database.
- **No ground**: a path that begins with neither a document nor an entity (a part of one, made by hand), or an empty
  path with no `head`, starts as asserted, with `standing` and `grounded_by` `None`.
- **A head class the table does not have** reads as its kind's default (`spaces.DEFAULT_GROUNDS`: a document a claim,
  an entity the record, both asserted), which is what a class that says nothing says; so `grounds={}` reads every
  head so. A `head=` the table does not have raises `spaces.UnknownHeadError`: the caller named it.

**The degree is not the sign.** `signature` gives the degree beside the lean and never changes `veridical` by it. A
judgement of the statement made elsewhere is the caller's to weigh (phase 8).

**For many nodes**, make the classes' facts once: `known = spaces.registered_spaces()`, then
`spaces.signature(path, known)`, and the heads' grounds beside them: `grounds = spaces.registered_grounds()` (every
document and entity class, as `ground_of` has it), `spaces.signature(path, known, grounds)`. The facts are the
export's (`veridical`, `fit`, `logical`, `unary`, `degree`, and `abstract`; a ground's as `export_ground` gives it),
so a caller with only the export has what the walk needs.

**In the interface** ✅ (step 7.3): a port of the walk, pure, `interface-core/src/schema/spaces.ts`: `spaceFacts`
(the facts from the exported models, abstract classes too, made once for them), `normalise`, `signature` (the same
`Signature` as `as_json()`), `signatureOf` (`undefined` where a path names a space the models do not know, so that a
list still draws; `signature` throws `UnknownSpaceError`), `statusOf` (the seven statuses of derived's `status_of`)
and `markOf` (what a list marks). The ground (step 3.5): `groundFacts` (the ground of each document and entity class
from the exported models, made once for them; a model exported before the field reads as its kind), `groundAt`,
`DEFAULT_GROUNDS`, and `signature(path, spaces, grounds = {}, head?)`, `signatureOf` the same; `grounds` left out,
every head reads as its kind's default. `UnknownHeadError` is thrown by both (`signatureOf` does not swallow it). The
mark of a list's row (`SpaceBands.tsx`) and the library's reading of identity claims (`identity.ts`) give the
grounds, so the marks in lists follow a head's ground. Its Vitest test reads `pangloss-models/tests/space_cases.json`
where it is (a case of the head itself has `head`, and `grounds` stand beside `spaces`), and passes every case. How a
ground is **shown** (a page's head saying "according to" its source, or "record") is not built ⏳: open with the user.

**Who reads the ground** ✅. The identity clusters do (`pangloss_library.clusters`, with
`registered_grounds()`): a claim of identity in a document whose ground leaves what it holds neither asserted nor
denied joins nothing; a claim that is itself a head reads its own class's ground. Derived does (step 4.5 of
[the build plan](spaces-and-comparison-plan.md#the-ground-of-a-head-class)): each part of a justification is walked
from its ground, and a justification and a fact have a standing, `"claim"` or `"record"`
([derived](derived.md)). The RDF export does (4.5): `pgo:standing` and `pgo:accordingTo` of the graph, and nothing
under a head whose ground does not assert has its direct triples ([RDF](rdf.md#shape-of-the-data-)). The time part
of similarity gives an empty table (`{}`) on purpose, so that every head reads as asserted: what a rumour says did
not happen is denied as what a charter says did not. The planted world for comparison declares
`Ground(by="source")` on its factoids (5.1b). Comparison's use of the ground (phase 6) is not built ⏳.

**From what is stored**: `n.meta.path` of a row a query returns, or `meta.path` of any view, is what `signature`
takes. A query that returns only `meta.semantic_spaces` cannot be walked: derived's and the identity clusters' rows
return the path (steps 4.1, 4.3), and the time part's will (5.2). The RDF export builds each node's path as it walks
a view (step 4.4).

## What is recorded ✅

When an instance is turned into its `CreateDB` or `UpdateDB` form, every node below the head is given two values, written in its `meta`, so that a node can be placed and filtered without walking up the tree:

- **`meta.path`**: the nodes it is nested in, from the head down to the node that holds it. Each entry is a `PathEntry` (exported from `pangloss_models`), `{kind, type, id, field}`, and on a space a degree was entered on, `degree` ([above](#a-degree-entered-on-a-space-degree-)):
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

Each entry also has the node's `id`. Had `Doubt` a field marked `Degree()`, with `"unlikely"` entered on `D`, the entry
`space Doubt.contents` of `N`, `S2`, `R` and `W` would have `degree: "unlikely"`, and no other entry would. `S1` and `S2` are siblings and neither is on the other's path. `N` is in `Doubt`, the space outside it; `D` is in nothing.

## Storage ✅

- **Memgraph** stores `meta` as a map property, the path in it as a list of maps.
- **Neo4j** cannot hold a list of maps as a property: the path is JSON text, `meta.path#json`, with `meta.path_types` (the types on the path) flat beside it for a migration's rename. A read query gives the path through `Dialect.meta_entry(node, "path")`, which names the entry so that it is read back as the list on either backend ([Neo4j](neo4j-implementation.md)).
- **Migrations**: every operation that puts a node on a path, takes one off, or changes a name that is in paths ends with `recompute_contexts` for the heads it touched (which keeps the degree of each space's entry, read from the paths stored before): wrapping and unwrapping (in a reified relation or a space), `change_wrapper`, `literals_to_embedded` (and so `add_embedded`), a renamed relation, and a renamed class (the heads found by `meta_mentions`, which looks in the path) ([migrations](migrations.md)).
- Data stored before the path was recorded (2026-11-25) is not carried over: such a database is made again. There is no migration of it.

## What the interface shows ✅

The interface reads the path in `interface-core`'s `api/context.ts`:

- **A row of a list and an item's console** show the spaces the item is in (`wrappingSpaces`, the meta's `semanticSpaces`).
- **A nested document's own page** (`Item.tsx`, `ContextFrames`) has, beside "Contained in" and the head's chip, a band for each space and a frame for each document of the path after the head, outermost first, each linked (`contextPath`). A document's frame names its field that holds what follows, as a field is named on a page; the head's field is named beside "Contained in".
- **A chip of a nested item** (`ItemContents.tsx`, `SpaceBands`) has bands of the same, by name (`contextTrail`); no field is said there.
- **What the path says of it** ✅ (step 7.3), where an item is shown as a reference or a row outside the document
  that holds it: a small mark (`AssertionMark`, in `SpaceBands.tsx`), in derived's words and colours ("Denied",
  "Reported not", "Forbidden": rose; "Reported", "Prescribed", "Not said either way": amber), the degree in its title.
  Only where the walk says something a plain reading does not: nothing for what is asserted (`Not[Not[p]]`,
  `Known[p]`), nor for a plain space that leaves its contents uncommitted with no degree (`reported`, which the band
  names already), so a project that sets no option on its spaces nor a ground on its heads sees no mark (the walk
  starts from the head's ground: what a rumour with a degree holds is marked). Drawn by `ReferenceChip` and
  `ResultButton` given the item's `path`: a list page's rows, "search everything", what refers to an entity (a chip,
  or the head of a block), and once on a nested item's own page, beside "Contained in".

Reified relations, conjunctions and embedded objects on the path are passed over. `use_in_semantic_space_label=False` on a document class (exported as `useInSemanticSpaceLabel`) leaves a nested document of that class out of these trails; a class the interface's models do not know is kept. The flag is for display only: storage does not read it, and the path has every node. In the example, `S2`'s page shows "Contained in `F`" (field `statements`) and the bands `Doubt` and `Negative`; `R`'s shows those and the frame of `S2`, naming its field `people`.

**What kind of space a band is** ✅ (step 7.3b): over its colour, a faint pattern by what the class says of its
contents (denies: diagonal lines; forbids: both ways; prescribes: horizontal lines; a necessity: a grid; a
possibility: dots; a space that asserts, and a plain space, none, so a project that sets no option sees no change),
changed by a class (`InterfaceMeta(band=...)`) or a project (`InterfaceConfig(space_bands=...)`):
[interface-features.md](interface-features.md#what-kind-of-space-a-band-is-).

## Conjunctions

`Conjunction` subclasses work similarly as generic wrappers (`Causes[Statement, Statement]` has `cause` and `result` slots) and are likewise stored as nodes (with their slots such as `cause` and `result` as relations). A conjunction is on the path of what it holds (`kind: "conjunction"`, `field` the slot), but it is not a space and adds nothing to `semantic_spaces`. They are declared and generate models; see [Defining models](models.md#conjunction).

## Tests

- Pure, in `pangloss-models`: `tests/test_context_path.py` (the algorithm on plain objects, and the shapes that were wrong before 2026-11-25 on the models' instances: two single slots each in a space, a list after a single relation that holds a space, a bare result after a negated cause, a space inside a cause, a space's own path).
- Conformance, on both backends: `test_stored_path.py` (create, update, read back, listed and read alone), and after every conformance test a check that each nested node's path is its parent's path and its parent, by the edges alone (`conftest.paths_are_true`, `helpers.assert_paths_true`); `test_migrations_context.py` (a recomputation of what the models wrote changes nothing, the degrees entered on spaces included). `test_stored_path.py` also has a degree entered on a space: written, in the entries of what it holds, read back, changed and cleared by an update, found by `$spaces`.
- What a space says of its contents, pure, in `pangloss-models`: `tests/test_semantic_space_fields.py` (the options, inheritance, `Modal`), `tests/test_check_semantic_spaces.py` (each refusal by its message and its fix, the warning), `tests/test_space_contents_length.py`, `tests/test_space_export.py`, `tests/test_attribution.py`, `tests/test_degree_marker.py` (the checks of `Degree()`, the export, the degree in the path of an instance), the migration diff's cases (`test_migration_diff.py`) and the stubs (`tests/typestubs/test_space_meta_stubs.py`, `test_attribution_stubs.py`); in `pangloss-cli`, `test_check_command.py` (the diagnostics and fixes).
- The ground: pure, `pangloss-models/tests/test_ground.py` (the defaults by kind, inheritance, every refusal by its message, the fix, the export, no migration from a change).
- The walk: pure, `pangloss-models/tests/test_spaces_walk.py` (every row of the walk's table and of the normalising table, the two limits, the degree, what prescribes; the walk from the ground, `GROUNDED`; the cases written to `space_cases.json` and run again from the file alone; the paths the models give an instance); conformance, on both backends, `test_stored_signature.py` (the signature of each node from the path a query reads, from a view, from a nested document read alone or listed, and after an update that clears a degree; statements of a charter and of a rumour, whose a statement is read of the head by `grounded_by`, the head itself and an entity by `head=`).
- The interface: `api/context.ts`'s functions and `ContextFrames` in Vitest; the field said on a nested page in e2e (`test_keys_and_nesting.py`, `test_fields_and_wrappers.py`). The walk's port, `schema/spaces.test.ts` (every case of `space_cases.json`, `statusOf`, `markOf`); the mark and the degree beside a head, `components/AssertionMark.test.tsx` and `form/HeadDegree.test.tsx`; in a browser, `e2e/test_assertion_marks.py`. The pattern of a band, `schema/bandKind.test.ts`, `components/SpaceBandPatterns.test.tsx` and `e2e/test_space_bands.py`.
