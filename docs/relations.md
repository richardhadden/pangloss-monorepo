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

Any other annotation is an error: `initialise()` raises `PanglossModelError` naming the model, field and type, rather than ignoring the field. In particular, a plain `dict`, `complex`, `bytes` and `UUID` are not supported, and nor are optional relations (`Person | None`); use a `list[Person]` for a relation that may be empty. Lists of embedded objects (`list[Date]`) and of annotated values are not supported either: a field has one of each.

`Annotated[..., DBField]` marks a field as a database-side field: it appears in the `CreateDB` model but not in the user-facing `Create` model. The `annotated_types` validators (`Gt`, `MinLen`, ...) are carried through to the generated models.

## Literal fields

Literal fields are stored as properties of the node (or edge) they belong to, rather than as nodes of their own.

| Type | Stored in Memgraph as | Notes |
|------|-----------------------|-------|
| `str`, `int`, `float`, `bool` | The same type | |
| `date`, `datetime` | Memgraph date / datetime | |
| `Decimal` | A string, e.g. `"1.10"` | Memgraph has no decimal type, and a float would lose precision. Strings are read back as `Decimal`, but cannot be compared numerically in Cypher |
| `Enum` (including `IntEnum`) | The member's value (a string or a number), as a plain property | Nothing to create; migrations change the values when a member's value changes or a member goes |
| `TypedDict` | A map | Every value must itself be a literal type or a list of one; may be nested, and may contain `NotRequired` keys |
| `list[...]` of any of the above | A list | |

Any of these can be written `X | None`.

### Optional literals

An optional literal (`number: int | None`) does not have to be given: it defaults to `None` in `Create`, `CreateDB`, `Update`, `UpdateDB`, `View`, `HeadView` and `ReferenceView` (for `reference_view_extra_fields`). A `None` value is **not written** to the database, so the property is absent from the node, and reads back as `None`.

Falsy values (`0`, `0.0`, `""`, `False`, `[]`) are values, and are written.

Similarly, a relation that is a list (`list[Person]`) defaults to an empty list in `View` and `HeadView` when it has no items, since an empty relation has no edges to read back. A single relation (`Person`) is required.

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

Each relation is stored as **two** edges: `(source)-[:field_name]->(target)` and `(source)<-[:reverse_name {reverse: true}]-(target)`. The reverse name defaults to a name derived from the field and can be set with `RelationConfig(reverse_name=...)` (lower-cased, spaces become `_`).

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
from pangloss_models.model_bases.configs import RelationConfig


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
- `allowed_type_names` / `excluded_type_names` restrict which child types are bound; `converter` transforms the value on the way down.

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
