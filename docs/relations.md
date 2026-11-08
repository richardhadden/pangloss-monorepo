# Relations and fields

## Field kinds

`initialise()` classifies every annotated field on a declared class (`initialise_models/initialise_field_definitions.py`) into one of these, available via `Model._meta.fields`:

| Field annotation | Definition class | Accessor |
|------------------|------------------|----------|
| A [literal type](#literal-fields) (and `X \| None`) | `LiteralFieldDefinition` | `.literal_fields` |
| `list[...]` of a literal type | `ListFieldDefinition` | `.literal_fields` |
| Another declared class, a union, `list[...]`, a trait, a generic | `RelationFieldDefinition` | `.relation_fields` |
| An `Embedded` class | `EmbeddedFieldDefinition` | `.embedded_fields` |
| `AnnotatedValue[...]` | `AnnotatedValueFieldDefinition` | `.annotated_value_fields` |
| `Annotated[T, DBField]` | marked `db_field=True` | |

Any other annotation is an error: `initialise()` raises `PanglossModelError` naming the model, field and type, and what to use instead where that can be said, rather than ignoring the field. In particular, a plain `dict` (use a `TypedDict`), `bytes`, `complex`, a pydantic model or a dataclass (use an `Embedded` or a `TypedDict`), a `Flag` enum and a union of literal types (`int | str`) are not supported, and nor is an optional list of relations (`list[Person] | None`: a `list[Person]` may already be empty). A list of embedded objects (`list[Date]`) is not supported either: a field has one. (A list of annotated values, `list[WithCertainty[str]]`, is: see [models.md](models.md#annotatedvalue).)

`Annotated[..., DBField]` marks a field as a database-side field: it appears in the `CreateDB` model but not in the user-facing `Create` model. Everything else a field is annotated with that pydantic acts on is carried to the generated models as it is: the constraints of `annotated_types` (`Gt`, `MinLen`, `Predicate`, ...), `StringConstraints`, `Strict`, the arguments of `Field(pattern=..., ge=...)`, and `AfterValidator` and the other functional validators and serialisers. Pydantic's shorthands (`PositiveInt`, `constr(max_length=3)`, `conint(ge=0)`, `StrictStr`) are these in `Annotated`, so they work too. Anything in `Annotated` that is none of these, and not one of Pangloss's own (`RelationConfig`, `DBField`, `SumsTo`, a `FieldMarker`, a description), is an error: what was written to do something must not be dropped in silence.

## Literal fields

Literal fields are stored as properties of the node (or edge) they belong to, rather than as nodes of their own. What is a literal, and how each is stored, is said once, in `pangloss_models.literals` (a registry of *codecs*; a package may add one with `register_codec`), and every other part asks it: the analysis of the fields, what is written, what the interface is told (`{"type": "str", "format": "uuid"}`), how a search compares a value, and what a migration sees as a change of storage.

| Type | Stored as | Notes |
|------|-----------|-------|
| `str`, `int`, `float`, `bool` | The same type | |
| `date`, `datetime`, `time` | The database's own types | A `datetime` with a timezone keeps its offset on both backends (tested); a naive one is naive |
| `timedelta` | A duration | Compared for equality only in a search (Neo4j does not order durations). Written in JSON as ISO 8601 (`P1DT2H30M`) |
| `Decimal` | A string, e.g. `"1.10"` | The databases have no decimal type, and a float would lose precision. Read back as `Decimal`; compared in a search as a number (`toFloat`, about 15 significant digits), so a `Meta(indexes=...)` of a `Decimal` field is refused: an index of the text would not be used |
| `UUID`; `AnyUrl`, `HttpUrl` and the other URL types; `EmailStr`, `NameEmail`; the `ipaddress` types and `IPvAnyAddress`; `Path`; `re.Pattern`; `Fraction` | A string | The export says the format (`uuid`, `url`, `email`, `ip`, `path`, `regex`, `fraction`), so the interface can check and show it. Read back as the type. Searched as text |
| `ByteSize` | An integer | format `bytes` |
| `Enum` (including `IntEnum`, `StrEnum`) | The member's value (a string or a number), as a plain property | Nothing to create; migrations change the values when a member's value changes or a member goes. A `Flag` is refused (a combination of members is a value no member has) |
| `Literal["a", "b"]` | The value | The values must be of one type (strings, whole numbers or booleans); the interface shows them as choices. The lightest fixed list; an `Enum` when the members need names |
| `TypedDict` | A map | Every value must itself be a literal type or a list of one; may be nested, and may contain `NotRequired` keys |
| `list[...]`, `set[...]`, `frozenset[...]`, `tuple[X, ...]`, `tuple[X, X]` of any of the above | A list | A set has no repeats and a tuple of a fixed length has that many items: the generated models and the interface see to it; the same list is stored. The items of a tuple must be of one type. `list[X | None]` is refused: a list holds values |

Any of these can be written `X | None`.

### Defaults

The default a class declares is carried to the generated models, as pydantic would have it: `count: int = 0`, `rank: int | None = 5`, `tags: list[str] = []` and `Field(default_factory=list)` all let the field be left out of a `Create` or an `Update`, and give it that value (a mutable default is copied, not shared). A default is a value like any other once written: it is stored. It is not part of the migrations' snapshot of what is stored, so changing one is not a migration; a *new* field with a default gives the nodes that exist that value, so `makemigrations` has nothing to ask.

### Optional literals

An optional literal (`number: int | None`) does not have to be given: it defaults to `None` in `Create`, `CreateDB`, `Update`, `UpdateDB`, `View`, `HeadView` and `ReferenceView` (for `reference_view_extra_fields`). (Here Pangloss is more lenient than pydantic, for which `int | None` without `= None` is still required.) A `None` value is **not written** to the database, so the property is absent from the node, and reads back as `None`. An optional list (`tags: list[str] | None`) is the same: left out, nothing is written, and `None` is read back, as against `[]`.

Falsy values (`0`, `0.0`, `""`, `False`, `[]`) are values, and are written.

Similarly, a relation that is a list (`list[Person]`) defaults to an empty list in `View` and `HeadView` when it has no items, since an empty relation has no edges to read back. A single relation (`Person`) is required.

### Optional relations and embedded objects ✅

A single relation or embedded object may be declared optional: `spouse: Person | None`, `about: Person | Place | None`, `by: ViaEdge[Person, Certainty] | None`, `in_role: InRole[Person] | None`, `born: Date | None`, `when: Date | DateRange | None`. As with an optional literal, it may be left out of a `Create` or an `Update` (or given as `None`), and it is `None` in every generated model when there is none. What is stored is what a single one stores, or nothing: one edge (and its reverse) to the target, or one node for an embedded object or a reified relation; when there is none, no edge and no node. An update that leaves it out removes what there was (an entity it pointed at is untouched). In the export the field is `"many": false, "nullable": true, "required": false`, and the interface's form starts it empty and lets it be removed.

`list[Person] | None` is refused: a list may already be empty (`[]`), so there is nothing for the `None` to say.

Migrations: `Person` → `Person | None` is a safe `AlterNullability` (nothing stored changes). `Person | None` → `Person` checks that every node has one, and fails saying how many have not (there is no default to give a relation or an embedded object: give each one first). `list[Person]` → `Person | None` is the `AlterCardinality` of any list becoming single (where there are several, `keep: "first"`), and `Person | None` → `list[Person]` needs nothing. (⏳ `list[Person]` → `Person`, required, does not check that every node has one.)

## Relation fields

A relation field's type determines what kind of value the generated model expects:

| Target | `Create` expects | Stored as |
|--------|------------------|-----------|
| `Entity` subclass | `Person.ReferenceSet`: `{"type": ..., "id": ...}` | Edge to the existing node |
| `Document` subclass | The target's own `Create` model, nested | New node, edge from the parent |
| `Trait` | A union of the `ReferenceSet`/`Create` models of all concrete implementers | As the concrete target |
| `A \| B` | Discriminated union on `type` | As the chosen target |
| `list[...]` | A list of the above | One edge per item |
| `SemanticSpace[T]`, `Conjunction[...]`, `ReifiedRelation[...]` | Their generated models | See [Semantic spaces](semantic-spaces.md) |

Each relation is stored as **two** edges: `(source)-[:field_name]->(target)` and `(source)<-[:reverse_name {reverse: true}]-(target)`. The reverse name defaults to a name derived from the field and can be set with `RelationConfig(reverse_name=...)` (lower-cased, spaces become `_`). It may not be the name of a field of the target or of one of its subclasses, nor `id`, `type`, `meta`, `urls` or `label`: `initialise()` refuses it, since the relation would replace that field in the target's view and its value would be lost.

Incoming relations (what points at an object) are analysed in `initialise_incoming_relation_definitions.py` and stored in `ModelFields.incoming_fields`; they feed the `HeadView` models.

## ViaEdge

`ViaEdge[Target, SomeEdgeModel]` adds an `edge_properties` field to the target's reference/create model, and writes those properties onto both the forward and reverse edges.

```python
class Statement(Document):
    was_carried_out_by: ViaEdge[Person, Certainty]


Statement.Create(
    label="...",
    was_carried_out_by={
        "type": "Person",
        "id": some_id,
        "edge_properties": {"level": 3},
    },
)
```

The generated variants are accessible as `Person.ReferenceSet._via.Certainty` (and `Action.Create._via.Certainty` for documents).

## RelationConfig

Attach options to a relation by wrapping the type in `Annotated`:

```python
from typing import Annotated
from pangloss_models import RelationConfig


class Statement(Document):
    person: Annotated[Person, RelationConfig(reverse_name="is_subject_of")]
```

| Option | Purpose |
|--------|---------|
| `reverse_name` | Name of the reverse edge |
| `subclasses_parent_fields` | Make this relation also fill a field of a parent/fulfilled class (see [Fulfils](#fulfils)) |
| `bind_to_child_field` | Copy a value from this object into fields of nested objects (see [Field binding](#field-binding)) |
| `validators` | Extra `annotated_types` validators |
| `description` | Description for the generated model |
| `default_reified_type` | For the interface, on a field whose options are all reified relations: the one (`InRole`, or `InRole[Agent]`) that an entity found by searching is put in (see below) |

### What the interface offers to add

The form shows the entities a relation can hold as a search at once, with a button under it for each of the
rest: `Agent | Identification[Alternative[ViaEdge[Person, Probability]]]` is a search for a group or a person,
and **+ Identification**. A relation with no entities to search for has a menu of its types.

When every option is a reified relation, `default_reified_type` makes the search the one for what that
reified relation holds (through a conjunction too: `Identification[Alternative[Person]]` searches for persons),
and a person found is put in it (an `Identification` holding an `Alternative` holding the person). The other
reified relations are buttons under it:

```python
class Activity(Statement):
    participants: Annotated[
        list[InRole[Agent]], RelationConfig(default_reified_type=InRole)
    ]
```

It must be one of the field's reified relations, and the field must hold nothing else, or the models do not
initialise. It is not part of the data (a migration does not see it).

## Field binding

Bind a field on the parent to fields on nested children, so the user only enters it once:

```python
class Action(Document):
    action_when: datetime.date


class Statement(Document):
    when: datetime.date
    action: Annotated[
        Action,
        RelationConfig(
            bind_to_child_field=[
                FieldBinding(
                    bound_field="when",
                    child_fields=["action_when"],
                    allowed_type_names=["Action"],
                )
            ]
        ),
    ]
```

- In `Statement.Create`, `action.action_when` becomes optional (`date | None`).
- A model validator on `Create`/`Update` copies the parent's value into children where the child field is unset.
- The binding recurses through intermediate objects and the semantic-space wrappers.
- The names are checked at `initialise()` (2026-11-08; a misspelt one used to be ignored, so the binding never applied):
  `bound_field` must be a field of the model (or `label`, `id`), each of `child_fields` a field of some model, and each
  type name the name of a model or of a class above one. The error says "Did you mean ...?", and the language server
  underlines the string.
- `allowed_type_names` / `excluded_type_names` restrict which child types are bound, **with the types below them**
  (2026-11-05): `allowed_type_names=["CreationOfPhysicalObject"]` binds a `CreationOfPainting` too, and one excluded
  excludes its subclasses. A child is bound if its class, a class above it or one of its traits is allowed (or none is
  listed), and none of them is excluded; so a child below both an allowed and an excluded type is not bound. The
  library's own bases (`Document`) are not names it is matched by. So narrowing or widening a child (↧/↥ in the
  interface) does not change whether a binding applies, as long as it stays below what is allowed. The builder makes a
  child's field optional by the same rule, and the interface's binder matches the same way (`binding_applies`,
  `class_names` in `model_bases/binding.py`; `applies` in `schema/binding.ts`). `converter` transforms the value on the
  way down.
- `child_fields` reach **the fields that stand for them** (2026-11-05): a binding into `object_created` gives a
  `CreationOfPainting` its `painting_created` (the field that subclasses it, directly or through `artwork_created`), and
  that field need not be given either. A value the narrower field cannot hold (an artwork bound to the painting
  created) is refused by its validation, naming the field; in the interface it is not given (and a field that was
  following the binding is emptied), and the field says why ("The thing is given to this from above, but cannot go
  here") until it is filled in or the value fits. (`fields_bound`, `bound_names` in `model_bases/binding.py`; `fieldsBound` in
  `schema/binding.ts`.) See [implied-types.md](implied-types.md), "Field bindings across a narrowed document".
- The value is validated as the child field's own type: a relation bound into a child (`ordered_to` into `given_by`) is
  a copy of its own, a new reified relation if it is one, not the parent's object.
- The child's value, given or bound, is stored on the child like any other (the binding is not data: a migration does
  not see it).

In the interface (the export has each relation's `bindings`), the form copies the parent's field to the bound fields of
what the relation holds as it is typed or chosen, and gives it to what is added under the relation. A child field that
is changed is the child's own: changing the parent's field again leaves it, while one that is empty, or still the value
copied to it, follows. Under a child that binds the same field itself (an order passed on, in an order), its own value
is given. A binding with a `converter` is left to the server.

The demo binds `Order.ordered_to` (who received the order) into the `given_by` of a transfer ordered, or the
`ordered_by` of an order passed on.

## Fulfils

A class declared as `Fulfils[Other]` supplies the fields that `Other` requires, so a single `Create` payload can produce both an `Activity` and a `PersonInPlace`.

```python
class PersonInPlace(Document):
    located_person: Person
    place: Place


class Activity(Document, Fulfils[PersonInPlace]):
    person_responsible: Annotated[
        Person,
        RelationConfig(
            subclasses_parent_fields=[
                FieldSubclassing("located_person", field_on_model=PersonInPlace)
            ]
        ),
    ]
```

`Activity.Create` gains `place` (inherited from `PersonInPlace`) with `person_responsible` standing in for `located_person`. When saving, `_to_db_model()` tries each fulfilable class and, if the data validates against its `CreateDB`, builds a combined model so the node carries both sets of labels and the extra edges are written.

A node that fulfils a class carries that class's labels (and so is found as one of them): when it is created, when it is nested in another document, and when it is updated (the labels follow what it holds then). Several classes can each fulfil different classes. Only a *relation* is optional through `Fulfils`: a literal that the fulfilled class requires is required of the fulfilling class too. Model generation is tested in `pangloss-models`; the Memgraph tests are `test_fulfils_writes.py` (the labels) and `test_write_subclassed_edges`. Migrations: [Database migrations](migrations.md).
