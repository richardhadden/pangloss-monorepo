# Comparison of statements (`pangloss-compare`) 🚧

Which statements tell of one event, and how they stand to each other: two reports that agree or disagree, an order
and what was done about it. **Being built** as phase 6 of [the build plan of semantic spaces and
comparison](spaces-and-comparison-plan.md#phase-6-pangloss-compare). Built so far: the package, what a
class says of its comparison (`CompareMeta`, step 6.1), its checks at `initialise()`, the readers of it, and the
verdict on two statements given as plain data (`maths.py`, step 6.2). Nothing is read of a database yet: the pairs
(6.3, 6.4), the judgements and the route (6.5) and learning from them (6.6) are in the plan.

An app: `INSTALLED_APPS += ["pangloss_compare"]`. It depends on `pangloss-core`, `pangloss-cypher`,
`pangloss-models`, `pangloss-dates` and `pangloss-learn`; pairs by vectors (6.4) will need `pangloss-vectors`, which
is optional (a dev dependency only).

## `CompareMeta` ✅

```python
from pangloss_compare import CompareMeta


class Birth(Statement):
    person: Person
    place: Place | None = None
    _compare_meta = CompareMeta(identifying=["person"], once_per="person")


class Transfer(Statement):
    given_by: Agent
    given_to: Agent | Identification[WeightedAlternative[Person]]
    _compare_meta = CompareMeta(identifying=["given_by", "given_to"], recurs=True)


class Fiction[T](SemanticSpace[T]):
    _compare_meta = CompareMeta(compared=False)        # what is inside it is not compared


class Expected[T](SemanticSpace[T]):
    _meta = SemanticSpace.Meta(fit="prescribes")
    _compare_meta = CompareMeta(orientation="before")  # what answers it came before it
```

A meta slot (`_compare_meta`, [meta slots](meta-slots.md)): a subclass has its parent's setting unless it sets its
own, which replaces it whole; a trait's counts for the documents that have it.

| Field | Default | On | Says |
|---|---|---|---|
| `identifying` | `()` | a class of documents | The fields whose entities say which event a statement tells of. A class with none is not compared |
| `once_per` | `None` | a class of documents | One of `identifying`: one event of the class for each entity in it (a birth for a person) |
| `recurs` | `False` | a class of documents | The same entities do this again and again (dues paid each year) |
| `compared` | `True` | both | `False`: on a class, it (and its subclasses, unless they set their own) is left out; on a space, the statements inside it are |
| `orientation` | `"after"` | a semantic space | Whether what answers a prescription of the space comes after it was prescribed (an order) or before (D5 of the plan) |

Negation and strength are not here: they come from the core's fields on the space (`logical`, `veridical`, `degree`:
[semantic spaces](semantic-spaces.md)).

**An identifying field reaches an entity**: directly, in a list, optional, or through wrappers (`InRole[Agent]`,
`ViaEdge`, an `Identification` of `WeightedAlternative`s). It is found as search reaches what is behind a wrapper
(`pangloss_models.search.leaf_classes`, through `reaches_an_entity`, the same test `Attribution(by=, to=)` uses): a
wrapper's own relations (`InRole.at`) are not on the way.

**A narrowed field counts as the field it narrows.** With `Making` saying `identifying=["made_by", "made"]` and
`MakingOfPicture.picture_made` narrowing `made` (`RelationConfig(subclasses_parent_fields=[FieldSubclassing("made",
field_on_model=Making)])`), `MakingOfPicture` inherits the setting, and `made` there means `picture_made`: the field
definitions of the subclass do not hold `made` (only pydantic's `model_fields` still do), but `picture_made` in its
place. A field narrowed twice counts as the first.

### The checks at `initialise()` ✅

On `ModelRegistry.after_finalise`, each a `PanglossMetaError` by the name of the class that says the setting (no
`fix=`: none of the add-ons' refusals names one):

- the slot on an entity, an edge model, a reified relation, a conjunction (anything but a class of documents, a
  trait, or a semantic space); a trait's setting on an entity that has it;
- on a semantic space, `identifying`, `once_per` or `recurs` (by name);
- on a class of documents, an `orientation` other than `"after"`; an `orientation` that is neither;
- `identifying` given as a string, or with something that is not a name in it;
- a name that is not a field of a class (not abstract, not generic) that has the setting, nor narrowed by one of its
  fields (with the nearest name); a field that is not a relation, or a relation that reaches no entity (only
  documents);
- `once_per` that is not one of `identifying` (with the nearest name); `once_per` with `recurs=True`.

A class that is not compared (no `identifying`, or `compared=False`) is not checked for its fields.

### The readers ✅

In `pangloss_compare.meta`, pure, after `initialise()`; a class may be given by its name:

- `compare_meta(model)`: the setting, or `None` where the class is not compared;
- `compared_classes()`: every compared class of documents (not abstract, not generic), by name;
- `identifying_fields(model)`: for each identifying field, the fields of the class whose values count as it
  (`{"made_by": ["made_by"], "made": ["picture_made"]}` for `MakingOfPicture`);
- `related(a, b)`: the same class, or one above the other (two siblings are not); `common_class(a, b)`: the more
  general of two related classes, else `None`;
- `space_compared(space)`, `orientation_of(space)` (a use of a generic space, `Fiction[Birth]`, has its setting; a
  class that is no space is a `ValueError`).

## The test models

`pangloss_testing.similar_models.declare(compared=True)` gives the compared classes their settings: `Birth` (once per
person), `Making` (once per thing made; `MakingOfPicture` inherits it), `Activity`, `Transfer` (recurs), `Attendance`,
`Order`, `Rule`; nothing on the spaces. The tests: `packages/pangloss-compare/tests/test_compare_meta.py` (no
database) and `tests/live/` (a factoid with a birth written and read back, on both backends in `run_tests.sh`).

## The verdict ✅ (pure; nothing calls it yet)

`pangloss_compare.maths.verdict(a, b, rules) -> Verdict`, with no database in it: two statements as plain data
(`Told`: class, entities by field, dates as spans of days, the walk's signature, head, source, and of what is
prescribed by whom, to whom and when) and each class's rules. It answers in this order: what each says of its
contents (the signature: asserted, denied, leaning for or against, prescribed); whether the contents are the same
thing (field by field; one event or two by `once_per`, else a logistic set by hand; of a prescription, the date is
a target and not evidence); and then the relation, by [the table](semantic-space-fields.md#contents-find-spaces-decide):

| Of | Relations |
|---|---|
| Two that describe | `agree`, `disagree` (with the fields), `two`, `contradiction`, `support`, `tension`, `compatible`, `at_odds` |
| A prescription and what came of it | `carried_out`, `carried_out_otherwise` (the targets missed: `late`, `early`, `different`, `in_part`), `done_not_carried_out`, `not_carried_out`, `breach`, `complied`, `permission_used`; each `reported` where the outcome is only reported |
| Two prescriptions | `compatible`, `conflict` (one flavour and authority), `orders_at_odds` |
| Either says nothing of it, or the classes are not related | `nothing` |

A verdict also says whether the two are within one factoid or one source, and a `strength` to order a list by (the
likelihood times how far each side commits, by its degree). What was settled in building it, and how it measures
on the planted world (99.9% of the planted pairs as the truth has them), is in
[the plan](spaces-and-comparison-plan.md#62-as-built-2026-11-27).
