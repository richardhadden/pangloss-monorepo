# Comparison of statements (`pangloss-compare`) 🚧

Which statements tell of one event, and how they stand to each other: two reports that agree or disagree, an order
and what was done about it. **Being built** as phase 6 of [the build plan of semantic spaces and
comparison](spaces-and-comparison-plan.md#phase-6-pangloss-compare). Built so far: the package, what a
class says of its comparison (`CompareMeta`, step 6.1), its checks at `initialise()`, the readers of it, the
verdict on two statements given as plain data (`maths.py`, step 6.2), and stored statements read as that data with
the statements each is compared with by rule (`reading.py`, `pairs.py`, step 6.3). Still to come: pairs by vectors
(6.4), the judgements and the route `GET /api/compare/{type}/{ref}` (6.5), learning from them (6.6). Nothing of it is
on the API or in the interface yet.

An app: `INSTALLED_APPS += ["pangloss_compare"]`, `requires = {"cypher"}` (it reads stored statements with Cypher of
its own). It depends on `pangloss-core`, `pangloss-cypher`, `pangloss-models`, `pangloss-dates` and `pangloss-learn`;
pairs by vectors (6.4) will need `pangloss-vectors`, which is optional (a dev dependency only).

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

The rules each compared class gives the verdict, `pangloss_compare.rules.rules()`: `{name: maths.Rules(identifying,
once_per, recurs)}` of `compared_classes()`.

## Stored statements as plain data ✅

`await pangloss_compare.reading.read(tx, ids, see_unpublished=True) -> {id: Told}`, in a read transaction the caller
opens: each id that is a document of a compared class (a head, or nested in one) as the verdict takes it.

- **`classes`**: its class and the compared classes above it, nearest first (`("MakingOfPicture", "Making")`).
- **`fields`**: the entities of each relation field of the class that reaches an entity, identifying or not. What is
  behind wrappers counts for the field that holds them, followed only through the fields a wrapper holds what it is
  made for in (`held_fields()`: of every wrapper class, `pangloss_models.search.held_field_names`), so the place of
  an `InRole.at` is no participant. An identifying field is named as `identifying_fields` names it; any other by the
  name of the field it narrows in the most general compared class above it (`picture_made` as `made`), or its own.
- **Real entities only**: a stand-in (`hooks.stand_ins`: a document such as `Mention` is no entity, and no wrapper
  that is one, `MatchesCriteria`, is on the way), a relation the server computes, what is below a guess no person
  has confirmed (`hooks.unconfirmed_classes()`, the rule of `pangloss-reconcile`'s `reasons.unconfirmed`, written
  again here since that package is no dependency) and a deleted entity are left out; an entity merged into another
  is the one kept (`validate_write.survivors_of`, the chain followed to its end).
- **`dates`**: each field that holds a date of `pangloss_dates` itself, as its widest stored bounds (`Span`:
  `earliest_fuzzy`, `latest_fuzzy`, day numbers); a date only unknown, or with a bound not stored, gives none.
- **`signature`**: `spaces.signature` of the stored path, with the models' spaces and grounds; a head by its class.
- **`head`**: its head's id (its own, for a head). **`source`**: where the head's ground names whose claim it is
  (`grounded_by`), the entity in that field of the head (of several, the first by id).
- **`prescribed`**: where the walk says so, of the node holding the innermost space that prescribes (the path's entry
  of it names the field): the entities of the fields that field's `Attribution(by=, to=)` names, that node's date
  where it has exactly one date field, and the space's `orientation`. Where only the head's ground prescribes there
  is no `Attribution`: `by` is what the ground's `by` field names, `to` is empty, `at` the head's date as above,
  `orientation` `"after"`. The head itself, under its own ground, has `Prescribed()`.

Not given: an id of nothing, of an entity, of a document of a class that is not compared, of one the reader may not
see (`see_unpublished`, by the head), or of one any space of whose path is `CompareMeta(compared=False)`. At most
four statements for any number of ids: the nodes; the nodes that prescribe (only when some statement is
prescribed); the entities of every field asked of every node; the chain of merges (only when an entity found is
merged). Tested against what `tests/test_compare_maths.py`'s `statements_of` makes of the same payloads
(`tests/live/test_compare_reading_live.py`), and the verdict on the pairs read is the planted world's truth.

## Pairs by rule ✅

`await pangloss_compare.pairs.by_rule(tx, statement, see_unpublished=..., most=...) -> Pairs`: the stored statements a
statement (by its id, or a `Told` already read) is compared with. `Pairs.found` is a list of `Pair(id, by)`, `by`
its reasons, each `(field, entity, "rule" | "addressee")` (the field by the name it counts as, the entity as the one
kept); `Pairs.more` is true where some were cut.

| Part of the rule | |
|---|---|
| From what | The statement's identifying entities (its class's `identifying`), real entities only, as read above |
| `"rule"` | A statement of a related class (`related`: the same, or one above the other; compared, not abstract) naming one of them in the same identifying field, by the name it counts as (a painting's `picture_made` is a making's `made`), other than itself. Two statements of one factoid pair |
| `"addressee"` | Of a statement that is prescribed: also one of a related class naming one of `Prescribed.to` in any identifying field. No date is asked: an undated statement is never left out by "after it", the verdict judges the date |
| Seen | What the reader may see (`fragments.visible` by the head, `see_unpublished` the caller's), and none inside a space that is `compared=False` |
| Merged | An entity merged into another is found by both: what names the one absorbed and what names the one kept pair, either way (the ids absorbed into each from the merges' records, `PGMerge(survivor)`, then `merged_into`) |
| How many | At most `most`, those with the most reasons first, then by id. `COMPARE_MOST_PAIRS` (200, a whole number of 1 or more, checked at `initialise()` with the app installed: `settings.most_pairs`) is what `pairs_of` gives it |

**A statement that is not compared gives nothing**: an id of nothing, of a class without rules, one the reader may
not see, one inside a `compared=False` space are each an empty `Pairs`, as the other packages answer an item the
reader may not see with nothing for their routes to make a 404 (`pangloss_vectors.views.visible_item`,
`pangloss_reconcile.stored.stored_plan`). A `Told` given by the caller is taken as it is.

`await pairs_of(id, see_unpublished, most=None) -> (Told | None, {id: Told}, Pairs)` does all three in one read
transaction: the statement read (None where it gives no pairs), its pairs, and the statements paired with it read.
The route of 6.5 will call it.

**The query** is the shape measured at 2.7M nodes on both backends before it was built ([the
plan](spaces-and-comparison-plan.md#63-the-query-measured-before-the-brief-2026-11-27): 1.6 to 2.6 ms median on
Memgraph, 2.8 to 3.9 on Neo4j, for the statement's entities and the others together), two halves joined by `UNION`,
each starting at an entity by its id (a scalar, so the index is used): its forward edges back to a statement
directly, and an edge of a held field out of a wrapper followed up through the wrappers to the statement. The class
is tested after the match, as a property (`t.type IN $types`): in the `MATCH`'s `WHERE` Memgraph scans the label,
and an `OR` of labels after an `UNWIND` loses rows there. Then the head and the rule of what the reader sees.
`pairs_of` is one read transaction of six to seven statements (the budget in `tests/live/test_compare_pairs_live.py`,
the same on both backends), and the work it does is the same with two hundred other statements of the same classes
about (the `PROFILE` test in the way of `conformance/test_query_costs.py`).

**Tests**: `tests/live/test_compare_pairs_live.py`, on both backends: each part of the rule by name (the same field
and not another; a making and a painting, and a birth not; two of one factoid; the addressee; `most` and `more`), a
wrapper's own relation, a stand-in (a `Mention`, and the candidates a `MatchesCriteria` computes), a suggestion not
confirmed and then confirmed, a merged entity both ways (by a merge, and as a merge leaves an edge it has not
moved), an unpublished factoid and a reader not logged in, what is not compared, nothing written (nodes, edges,
`PGPending`), the budget and the work; `tests/test_compare_settings_rules.py` (the setting, `rules()`).
