# Comparison of statements (`pangloss-compare`) 🚧

Which statements tell of one event, and how they stand to each other: two reports that agree or disagree, an order
and what was done about it. **Being built** as phase 6 of [the build plan of semantic spaces and
comparison](spaces-and-comparison-plan.md#phase-6-pangloss-compare). Built so far: the package, what a
class says of its comparison (`CompareMeta`, step 6.1), its checks at `initialise()`, the readers of it, the
verdict on two statements given as plain data (`maths.py`, step 6.2), stored statements read as that data with
the statements each is compared with by rule (`reading.py`, `pairs.py`, step 6.3), and a person's judgement of a
pair with the route `GET /api/compare/{type}/{ref}` (`models.py`, `judgements.py`, `compare.py`, `api.py`, step
6.5), learning from the judgements (`learning.py`, `fits.py`, `pangloss compare learn`, step 6.6), the pairs
through near entities (`near.py`, `?near=true`, step 6.4), what the user answered of what those left ("6.8": a
judgement never edited, camelCase field names, the check before a fit is used, and the rest, each below), the
section "Compared" of the interface (step 7.4, [below](#the-interface-)) and the page of two statements side by side,
where a judgement is recorded (step 7.5, [below](#the-page-of-two-side-by-side-)).

An app: `INSTALLED_APPS += ["pangloss_compare"]`, `requires = {"cypher"}` (it reads stored statements with Cypher of
its own). It depends on `pangloss-core`, `pangloss-cypher`, `pangloss-models`, `pangloss-dates` and `pangloss-learn`;
the pairs through near entities need `pangloss-vectors` (and a part that knows names), which is optional: it and
`pangloss-reconcile` are imported only when installed, and without them there are no such pairs.

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
`Order`, `Rule`; nothing on the spaces; and `StatementJudgement`, the project's class of judgement (below), reviewed
with `declare(reviewed=True)`. The tests: `packages/pangloss-compare/tests/test_compare_meta.py` (no
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
  (`grounded_by`), the entity in that field of the head (of several, the first by id: what "within the same source"
  and "sources differ" go by); **`sources`**, every entity in it (for showing: the route's `sources`).
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
The route calls the same in its own transaction (`pairs_in(tx, ...)`).

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
moved), an unpublished factoid and a reader not logged in, what is not compared, `naming` (the rule for other
entities, step 6.4) finding nothing below a suggestion not confirmed (until it is) nor in a space not compared,
nothing written (nodes, edges, `PGPending`), the budget and the work; `tests/test_compare_settings_rules.py` (the
setting, `rules()`).

## A person's judgement ✅

`pangloss_compare.EventJudgement` (`models.py`) is what a person says of a pair: an abstract document with

- `verdict`: `agree`, `disagree`, `two_events`, `carried_out`, `carried_out_otherwise`, `not_carried_out`, `breach`,
  `complied`, `permission_used`, `done_not_carried_out` (D7, widened by the user: each named as the relation of the
  maths it says, `two_events` the relation `two`). **Not checked against the kind of the pair** (`complied` may be
  said of an order, `agree` of a prescription and what was done): the interface is to offer only what fits. Where
  one does not fit, the entry's relation is still the person's, and nothing breaks: `settle` reads only whether it
  is an answer (`maths.ANSWERS`) of the pair's first statement;
- `fields: list[FieldName] = []`: the fields the two disagree on, or of what was carried out otherwise the targets missed.
  In a payload as a payload's keys are (`carriedOutBy`, `to_camel` of the field's name) or as Python's
  (`carried_out_by`), **stored by the name the verdict gives the field** (Python's; a narrowed field by the name of
  the field it narrows, `picture_made` as `made`), resolved when it is made against the two statements' classes
  (below), and given back by the route in camelCase;
- `note: str = ""`.

It has **no type parameter** (a top-level document cannot take one: [the plan, 0.5](spaces-and-comparison-plan.md#phase-0-as-found-2026-11-25)),
so the package names no statement class. The project declares its own class below it with the two citing fields,
by these names, the prescription first where one of the two is:

```python
from pangloss_compare import EventJudgement

class StatementJudgement(EventJudgement):
    statement: Cites[Statement]
    other: Cites[Statement]
```

At `initialise()` (`check_judgement_classes`, a hook of `ModelRegistry.after_finalise` registered when
`pangloss_compare.models` is imported, as the server and the CLI import every installed app's) each class below
`EventJudgement` that is not abstract must have `statement` and `other`, each a single `Cites[...]` that protects what
it cites (not a list, not `| None`, not a `Cites` with `protect = False`, which is never marked changed): a
`PanglossModelError` naming the class, the field and what to write. (No `fix=`: no add-on's refusal has one.) A cited
basis beside the citation, which an installed app may add to every `Cites` field, is allowed. The app ships
`migrations/0001_initial.py` (the abstract class and the index of its label) `0003_field_names.py` (`fields` a
list of `FieldName`, the models only) and `0004_verdicts.py` (the three verdicts added, the models only); the project's class is in the project's migrations.

A judgement is written by the **ordinary `POST /api/NAME`** of the project's class, logged in, as any document is
(any logged-in user may: call 6). Citing what is not a statement of the class the field allows (a factoid, an
entity, an id of nothing) is refused there by the citation check, a 422. A statement cited by a judgement is
protected as any cited document is: changing it needs `acknowledge_citations`, and marks the citation.

**What is checked when one is made** (`check_what_is_judged`, a `@before_create` of `EventJudgement`, run by every
write of the models; a `PanglossWriteRefused`, a 422 at the field): `statement` and `other` do not cite the same
statement (at `other`); each of `fields` is a field (pydantic's `model_fields`, its own name or `to_camel` of it) of
the class of one of the two statements as stored (read by their ids, one statement; at `fields`, naming each that is
not, as given, and the classes), and is written as `models.resolved` names it (the check replaces the write's
`fields`: the first of the two classes that has it, by the name `reading.Known.shape` gives it, an identifying or
narrowing field by the name it counts as, any other by its own; one named twice once). So `field2` comes back to a
`field_2`, `sourceUrl` or `source_URL` to a `source_URL`, `pictureMade` to `made`. What a citation does not name by
an id (a cited basis), or names that is not there, is left to the citation's own check; with no class to read (a
statement made in the same write), the names are only made Python's by pydantic's `to_snake` where they have a
capital, and are not checked.

**No class holds a judgement as a part of it** (`check_judgements_not_held`, at `initialise()`): a relation of any
class to a class of judgement as a document it contains (directly, in a list, or behind a wrapper's parameter, a
space's `contents`) is a `PanglossModelError` naming the class and the field: the judgement could never be updated,
so what holds it could never be saved again. Citing one is not holding it.

**A judgement is never edited** (`refuse_any_update`, a `@before_update` of `EventJudgement`): every update is
refused, whatever its path (the API's `PUT`, a 422; `Update(...).save()` in a script; pangloss-history's restore,
which writes an update), with why: a person who changes their mind makes a new judgement, which, being the newest,
decides, and the old one stays as the record of what was said. So "newest", who and when are the judgement's
creation and nothing else. Deleting one is as for any document. (So the mark "changed since cited" on a judgement's
citation is for good: a save of the judgement with it false would clear it, and there is none. A new judgement is
how a person says they have looked again.)

**The judgements of a statement's pairs** (`judgements.judgements_of(tx, id, others, see_unpublished=...)`, one
statement): the judgements citing `id` in one of the two fields and one of `others` in the other (either order is
the pair), from the citations of `id` by their indexed `target_id`, each with its id, class, `verdict`, `fields`,
`note`, who made it and when (the record of its head's creation, `createdBy` as `meta.createdBy` gives it), and
`changedSinceCited` (either of its two citations is marked changed: the mark `pangloss_cypher.citations` sets on
every citation of a statement changed with `acknowledge_citations`; a judgement is never saved again, so the mark
is for good).
Newest first, then by id. Its `fields` in camelCase.

**What the reader sees.** A judgement is shown only if the reader may see the judgement itself (`fragments.visible`
by its head: not deleted, and published unless the reader may see what is not). The statements it cites are never
a question: the ids asked about are those the comparison read as the reader in the same transaction, so a judgement
that cites a statement the reader may not see cannot match a pair the reader sees.

## The comparison and its route ✅

`await pangloss_compare.compare.compare(id, see_unpublished) -> Comparison | None`, in one read transaction: the
statement and its pairs (`pairs_in`), the verdict of each pair (`maths.verdict` with `rules()`, then `compare.settle`, which is `maths.settled` of what the entries say once people's judgements are in: a judged pair is never superseded, a person's answer tells as a statement does, a pair judged two events tells nothing;
over them), the judgements of the pairs, and the labels of the statements and their heads (one statement). None
where `pairs_in` gives no statement.

**A person's judgement overrides.** Where a pair has judgements, the newest decides the entry's `relation`
(`two_events` is the relation `two`) and `fields`; `how` is then empty (a judgement says which fields, not how) and
`reported` false. `workedOut` keeps what the maths said (`relation`, `fields`, `how`, `reported`) on every entry,
so both can be shown, and `judged` is the newest judgement's verdict (null with none). A judgement on a statement
changed since it was cited still overrides, with `changedSinceCited` on it. Each verdict of what came of a
prescription (`carried_out`, `carried_out_otherwise`, `not_carried_out`, `breach`, `complied`, `permission_used`,
`done_not_carried_out`) is an answer of the same standing in `settle`: it tells what came of the prescription, so a
report of the same one that no person judged is `superseded`, as the maths' own asserted relation of that name does
(all seven are `maths.ANSWERS`; the maths' `done_not_carried_out`, asserted, supersedes a report too). The rest of
the entry (`likelihood`,
`within`, `strength`, `superseded`, `first`, `second`, `common`) is the maths' whatever a person said. The pure part
is `compare.overridden`.

**The order** is of what the maths said: by `strength`, highest first, `two` and `nothing` last, then by the other
statement's id.

**Field names are camelCase** wherever the answer gives one as a value (`fields` and the keys of `how`, of an entry
and of its `workedOut`; a reason's `field`; a judgement's `fields`), as a payload's keys are (pydantic's
`to_camel`, `compare.json_name`). So does every other JSON of a judgement (its `GET /api/NAME/{id}`, a version in
pangloss-history): `fields` is a `list[FieldName]` (`field_names.py`), a `str` that is Python's name in Python and in
the store and `to_camel` of it in JSON, the way the framework gives a type its own JSON form (a pydantic core schema
with a serializer for JSON only, and a literal codec, format `field-name`, stored as text: the generated TypeScript
type is `string[]`). What JSON gives back is held as it comes: a client of the API (the SDK's models) holds the
camelCase names, which give the same JSON again and which the create check resolves (`to_camel` of each field is the
exact way back to it). A list's items and a create's answer are references and give no `fields`. **A reason's
`entity`** is `{id, type, label}` in a pair by rule as through near entities (the labels read in the same statement
as the statements').

`GET /api/compare/{type}/{ref}` (`api.py`): the comparison of the statement `ref` (its id) of the class `type` (its
own, or one above it: `/api/compare/Statement/{id}` answers as `/api/compare/Birth/{id}`), for any reader, as the
reader may see it (`backend.current().unpublished_visible()`, as the similar route has it). **A 404, the same for
each** (`There is no comparison of a {type} with id {ref}`): no class `type`, an entity class, an id of nothing or
of another class, a class that is not compared, a statement the reader may not see. An id that is not one is a
422, as at `GET /api/NAME/{id}`. It writes nothing. An answer (a birth told twice, and a person who said these are
two events):

```json
{
  "statement": {
    "id": "01a21c66-4ddc-…", "type": "Birth", "label": "Ada is born",
    "head": {"id": "01a21c66-4ddc-…", "type": "Factoid", "label": "a birth"},
    "sources": [{"id": "01a21c66-4d50-…", "type": "Source", "label": "the annals"}],
    "prescribes": false, "prescription": null, "says": "asserts"
  },
  "pairs": [
    {
      "other": {
        "id": "01a21c66-4de8-…", "type": "Birth", "label": "Ada is born, again",
        "head": {"id": "01a21c66-4de8-…", "type": "Factoid", "label": "a birth again"},
        "sources": [], "prescribes": false, "prescription": null, "says": "asserts"
      },
      "relation": "two", "fields": [], "how": {}, "reported": false,
      "likelihood": 1.0, "within": null, "strength": 1.0, "superseded": false,
      "first": "01a21c66-4ddc-…", "second": "01a21c66-4de8-…", "common": "Birth",
      "workedOut": {"relation": "agree", "fields": [], "how": {}, "reported": false},
      "found": "rule",
      "by": [{"field": "person", "entity": {"id": "01a21c66-4d4e-…", "type": "Person", "label": "Ada"}, "kind": "rule"}],
      "judged": "two_events",
      "judgements": [
        {
          "id": "01a21c66-58be-…", "type": "StatementJudgement", "label": "Two events: Ada is born and Ada is born, again", "verdict": "two_events",
          "fields": [], "note": "two Adas",
          "createdBy": [{"username": "ann", "kind": "user", "version": null, "date": null}],
          "createdWhen": "2026-11-27T09:46:39.169165+00:00", "changedSinceCited": false
        }
      ]
    }
  ],
  "more": false,
  "model": null,
  "near": null
}
```

`other` and `statement` carry what a chip needs (id, class, label, and the head's, for the link to the factoid),
whose claim each is (`sources`: every entity its head's ground names, `Told.sources`, each as `{id, type, label}`, by
label then id, an empty list where the ground names no one or the field is empty; read in the same statement as the
labels, so the budget is unchanged), whether it prescribes its contents (`prescribes`, the walk's `fit`: an order's
contents; the interface heads its section "Carried out?" by it) and, of one that does, what kind of prescription it
is (`prescription`, `maths.prescription`, from the signature the maths already has: `"permission"` where the innermost
modality is a possibility, else `"order"` where it is for its contents and `"prohibition"` where against them; null
where it prescribes nothing or leans neither way), and what it says of its contents (`says`, `maths.stance`:
`asserts`, `denies`, `for`, `against`, or `neither`, which says nothing either way): the page of two side by side
offers the verdicts that fit by these two, not by the relation the maths gives the pair.
A judgement gives its `label` too, for its chip.
`found` is `"rule"` for every pair here (the pairs through near entities are asked apart, `?near=true`, below);
`near` is null. `more`: some pairs were cut at
`COMPARE_MOST_PAIRS`. `model`: the fit of people's judgements the verdicts were worked out with (below), or null:

```json
"model": {"id": "4f0c…", "at": "2026-11-27T14:02:11.418000+00:00", "judgements": 20, "oneEvent": true, "answers": false}
```

The route is for any reader, and a fit is of every judgement, those a reader may not see too; so the counts
(`judgements`, `oneEvent`, `answers`) are given only to a reader who is logged in, and are null to another (`id` and
`at` to anyone; `fits.for_route(..., logged_in=)`, the request's `unpublished_visible()`). The verdicts are the same
for both.

**What it costs**: one read transaction; the statements of `pairs_of` (six or seven) and three more, the fit in use,
the judgements and the labels (no judgements are asked for a statement without pairs): 9 or 10, 6 alone, the same on both backends
(the budget in `tests/live/test_compare_route_live.py`). Not measured at size: the judgements' query starts from the
indexed `target_id` of the asked statement's citations, so it costs what that statement is cited.

**Tests**: `tests/test_compare_judgement_model.py` (the model and each refusal of its check, `fields` in camelCase
kept as Python's, the two write checks), `tests/test_compare_override.py` (the override, the order, newest first,
camelCase names and a reason's entity as a chip), `tests/live/test_compare_route_live.py` on
both backends (a birth told twice agrees, each statement's source and whether it prescribes, a gathering and its denial contradict, an order and what was done is
`carried_out` with the order first whichever is asked; strongest first; a judgement overrides and `workedOut` keeps
the maths; the newest of two wins, both listed with who and when, either order; changed since cited, from either
side; another class citing the same statements is no judgement; a judgement never edited (`PUT` and an update of
the models refused, nothing changed) and deleted; one citing a statement twice, or naming a field of neither
statement, refused; `fields` in camelCase, stored as Python's, given back in camelCase; an unpublished factoid's
statement and a reader not logged in; an unpublished and a deleted judgement; the 404s, of a visible statement of
another class too; nothing written, on the error paths too; the ordinary write refusing what is no statement, and a
write not logged in; the budget).

## Learning from judgements ✅

Step 6.6 (`learning.py`, pure; `fits.py`, what reads and writes; the same design as reconciliation's,
[reconcile.md](reconcile.md), "Learning from decisions"). Why the hand-set score is among the features, measured
before it was built: [the plan](spaces-and-comparison-plan.md#66-measured-before-its-brief-2026-11-27).

**What is learnt, from what.** Every judgement is read (as an admin: an unpublished one counts, a deleted one does
not), with the two statements it cites as they are **now** (`reading.read`). Only the newest judgement of a pair
counts (either order). Each is an example of one of two models, or left out and counted by why
(`learning.LEFT_OUT`: `older`, `changed` (a statement changed since it was cited: it may no longer be what was
judged), `unread`, `itself`, `not_compared`, `says_nothing`, `two_prescriptions`, `by_rule`, `not_the_thing`,
`not_learnt` (`done_not_carried_out`, which the rules decide before any likelihood is asked: of a pair done by another
or before it was prescribed it is `by_rule` already, of any other it is this), `other_verdict`):

| Model | Its examples | Yes | No | Its features |
|---|---|---|---|---|
| One event or two (`maths.ONE_EVENT`) | Two that describe, the logistic deciding (`maths.by_rule` None), neither saying nothing | `agree`, `disagree` | `two_events` | `maths.features` but `bias`, and `by_hand` (`maths.BY_HAND`: the log odds of the hand-set likelihood) |
| Does this answer that (`maths.ANSWERS_IT`) | A prescription and another, of the thing prescribed (`maths.answers`), by one of those it was prescribed to and on the right side of when (what another did, or what was done before, the rules settle: left out as `by_rule`) | `carried_out`, `carried_out_otherwise`, `not_carried_out`, `breach`, `complied`, `permission_used` | `two_events` | `maths.answer_features` but `bias`, and `by_hand` of `ANSWER_WEIGHTS` |

Each is fitted by `pangloss_learn.fit` (ridge 1) and compared, over five folds held out (`compare_calls`, seed 0),
with **the hand-set score**: how often the fit calls the judgement rightly, against how often the hand-set
likelihood does (a half or more is "yes"; `compare_calls(baseline=...)`), and on how many of the held-out judgements
the two call differently (`count_differences=True`, `CallsCompared.differ`). **The folds are dealt by the answer**
(`stratified=True`): the "yes" and the "no" apart, round the folds in turn, so every part a model is fitted on has
both answers wherever there are two of each or more (people rarely say "two events": dealt as they came, a part with
none could not be fitted, and the model was refused). With one answer only there is no model (`fit` says why); with
one of an answer, a part has none of it, and the model is fitted but not compared. Both options are
`pangloss-learn`'s, off unless asked for, so reconciliation gets what it did. The same judgements in any order give
the same models and the same comparison.

**When a fit is used.** Each model by itself, when it is of `COMPARE_LEARN_FROM` judgements or more (100; checked at
`initialise()`), was fitted and compared, and on the judgements held out was **not worse than the hand-set score by
more than chance**: refused only when the hand-set score is right more often by more than `COMPARE_LEARN_MARGIN`
(1.0; a number of 0 or more, checked at `initialise()`) times the square root of the number the two call
differently (`learning.Fitted.passes`, `CallsCompared.within`; only where they call differently can one be right and
the other not, and were each of those a coin toss the difference would spread by that root). `COMPARE_LEARN_MARGIN = 0`
is the earlier rule, right as often or more. A fit is written as a `PGCompareModel` (one for each fit, none deleted:
its signature, how many judgements were read and when the newest of them was made (`latest`), those left out by why,
each model as JSON or null with why, how many judgements each is of, the comparisons (`decisions`, `model`,
`baseline`, `differ`), the `margin` it was checked by, `one_event_used` and `answers_used`, `in_use`, and
`not_in_use`), and it is **in use** when one of its models passed or both; at most one fit is in use, and a fit none
of whose models passed is written, not in use, leaving the one in use before. Two runs at once may each unmark what
was marked and mark their own without seeing the other's: after a fit is put in use, a second transaction leaves
only the newest of those marked (`fits.SETTLE_QUERY`; the later of the two settlings begins after both writes and
sees both).

**A fit that would lose a model is not put in use**: where the fit in use (of today's signature: another is used by
nothing) has a model in use that the new fit's did not pass, the new fit is written, not in use, with why
(`not_in_use`: "the fit in use, …, has "Does this answer that" in use, which this one has not"), and `learn` says so
and how to put it in use (`--use ID`, which still can); `status` says it of the newest fit.

**Nothing new, nothing written** (as reconciliation's `learn`; there is no way to force it, as there is none there):
where the newest fit written, in use or not, is of today's signature, of as many judgements read, the newest of
them made at the same time, of as many examples of each model and left out for each reason, and of the same examples
(`examples_digest`, `learning.digest`: a hash of each model's examples, their features, answers and groups),
`learn` fits nothing, writes nothing, and says so ("Nothing new since the fit …"; the admin job's report the same).
A judgement is never edited, so one added or deleted changes the count or the newest; what its example is made of is
the two statements as they are now, so a cited statement edited (its judgement then `changed`), or two entities
merged (a pair through near entities now one by rule, or an example's features changed), is something new too. A
dry run still fits and compares, and says that a run would write nothing. A fit is of a **signature** (`learning.signature`): the features of both models, `maths.WEIGHTS`,
`maths.ANSWER_WEIGHTS` and each compared class's rules. Change any of them and a fit of before is used by nothing.
`structure.py` and `migrations/0002_models.py` make `PGCompareModel` unique by `id`, and indexed by it.

**The route uses it and says so**: `compare` reads the fit in use in its transaction (one statement); if it is of
today's signature, `maths.verdict(fitted=...)` is given the models of it that passed (`learning.as_fitted`), and the
other is by hand; `model` in the answer says which (`oneEvent`, `answers`). `workedOut` is what the verdict said
with it; a person's judgement still overrides.

**The commands** (`cli.py`) and the admin job (`admin.py`):

| | |
|---|---|
| `pangloss compare learn [--dry-run]` | Reads, fits, compares and writes the fit, in use past the check and unless it would lose a model; prints what it did, line by line (of each model, how many held out each called rightly and how many they call differently). `--dry-run`: all of it, writing nothing. With no judgement, or nothing new since the newest fit, nothing is fitted or written |
| `pangloss compare learn --use ID` / `--use none` | Nothing fitted: an earlier fit put in use through the same check (today's `COMPARE_LEARN_FROM` and `COMPARE_LEARN_MARGIN`; refused, exit code 1, with why, also when it is of another signature), or none |
| `pangloss compare status` | How many judgements there are and how many more `COMPARE_LEARN_FROM` asks for, `COMPARE_LEARN_MARGIN`; the fit in use, whether it is of today's signature, and of each of its models whether it is used, what its comparison found and what today's check says of it; and the newest fit, where it is not the one in use, with why |
| The admin job `compare_learn` (`dry_run` `no` or `yes`) | `learn`; its counts are the job's, its lines the report `learnt.txt` |

**Measured** (pure, `tests/test_compare_learning.py`, the planted world at 2,000 people): of the 31,459 pairs of
seed 2 the logistic decides, 67 mistakes by hand; fitted on 100 judgements of seed 1 drawn from those shown (a
hand-set likelihood of 0.2 or more), 23 to 40 over five draws (23 to 64 over twenty, one above 40); on 400, 23 to 26
(23 to 36 over twenty); without `by_hand` among the features, 513 to 8,222. The test's draw is the same whatever the
hash seed (it hung on the order of a set's entities before: with `PYTHONHASHSEED=4` it drew one of 74 mistakes; the
floor, 40, is kept). At 100 judgements the held-out comparison is close (by the hand-set score 93 to 98 of 100
right, by the fit 95 to 99): with "no worse" two of those five draws were refused though the fit halves the
mistakes on the world, which is what `COMPARE_LEARN_MARGIN` is for (not measured again with it).

**Not in this step** ⏳: the class defaults of the degree learnt from how often prescriptions of each kind were
carried out (the row's last sentence; it goes with phase 8's degree); any interface.

**A judgement of a pair through near entities** is never an example today: learning reads the two statements as
they are, with nothing read as anything else, so two that name different entities in their identifying fields have
none in common and the rules settle them (`by_rule`; of a prescription and another, `not_the_thing`). Once the two
entities are merged, the same judgement is of a pair by rule, and counts.

**Tests**: `tests/test_compare_learning.py` (which judgements are examples of which model, each reason left out by
name, the newest, any order, a fit as the verdict takes it, a fit worse than by hand and the margin, the folds dealt
by the answer, the signature, the planted floors), `tests/test_compare_fits.py` (the check with the margin, a fit
that would lose a model, nothing new, the route's `model` to a reader not logged in, the lines of `learn` and
`status`), `tests/live/test_compare_learn_live.py` and `tests/live/test_compare_learn_command_live.py` on both
backends (none; too few; a fit in use and the route answering with it, its counts null to a reader not logged in; a
worse one refused; a second in use and a refused one leaving it; another signature, of the weights and of the rules;
`use`; a dry run; changed since cited and older counted; a deleted judgement and an unpublished one; the admin job;
nothing new; an "answers" model in use, live, and a fit that would lose it written not in use, then `use`d; two runs
at once; the commands).

## Pairs through near entities ✅

Step 6.4, as the user decided it ([the plan](spaces-and-comparison-plan.md#64-the-entities-measured-2026-11-27-shown-to-the-user-before-building)):
the pairs the rule cannot find because the two statements name **two entities that may be one** (a person and an
unreconciled double), sought through the entities, not through the statements' own vectors (which find little:
[the first figures](spaces-and-comparison-plan.md#64-measured-2026-11-27-waiting-for-the-user)). `pangloss_compare.near`
and `compare.compare_near`.

**What is found.** For each identifying field (its root name) and each real entity X the statement names in it (as
`reading` reads them: no stand-in, nothing below a guess not confirmed, a merged entity as the one kept; an entity
of a class without vectors is not searched from), the entities X′ nearest X: `pangloss_vectors.nearest(of=X,
profile=COMPARE_PROFILE, types=..., k=COMPARE_NEAR_K)`, each scoring `COMPARE_NEAR` or more. `types` are the concrete
entity classes the fields that count as that root reach, in the statement's class and in each related class (the
walk of `reaches_an_entity`, search's `leaf_classes`); `asked` names those fields as `Model.field`, so that a class
that is another only by use is asked as `pangloss_vectors.by_use` says. Then the rule with X′ in X's place
(`pairs.naming`): statements of related classes naming X′ in the same identifying field, that the reader may see,
none in a space that is `compared=False`, none where X′ is only below a suggestion not confirmed, a merge followed
both ways (`absorbed_into`), less the statement itself and every pair by rule (asked in the same query, all of them).
Nothing through whom a prescription is to. At most `COMPARE_MOST_PAIRS`, before any verdict, **the places shared
among the near entities in turn** (`near.candidates`): one statement of each near entity X′ (of every identifying
field together), the nearest first (then by field and id; of each X′, its statements by id), then the second of each,
and so on, one already taken passed over, so a namesake nearer than the right one and named in many statements does
not take every place (`more`: some were cut).

**Not through an X′ that either statement names beside its X** (`near.not_both`: in any of its fields, or as its
source): a statement that names both is the best sign that they are two (Ada gives to her namesake; the namesake
gives to Ada). That reason is dropped, and the pair where none is left; one reached through another entity is still
given through that one. (Done after the cut, so a pair so dropped leaves its place empty.)

**The verdict** is `maths.verdict(statement, other, rules(), fitted=...)` with each X′ left read as the X it is near
(`near.substituted`; an X′ near two X as the nearer): in the other's fields, in its `prescribed.by`/`to`, and in the
source of either (so "sources differ" does not count, nor "within one source" fail, where the only difference is
X and X′: two accounts each by the one who did it). The head is a document, never an entity, and is read as it
is. A pair is
given **only where the relation is neither `two` nor `nothing`**: it reads "one event if X and X′ are one". "Once per"
stays certain, so a namesake's birth told otherwise is `disagree` (one birth told otherwise, if these are one person:
evidence against merging them).

**Judgements**: a person's judgement of such a pair is found and overrides as for a pair by rule (the same lookup by
the two statements). These pairs are never `superseded` and supersede nothing (`settle` is of the pairs by rule).

### The settings

Checked at `initialise()` with the app installed (`settings.py`):

| Setting | Default | |
|---|---|---|
| `COMPARE_PROFILE` | None | The profile of `pangloss-vectors` near entities are found by. None: reconciliation's (`pangloss_reconcile.settings.profile()`, `RECONCILE_PROFILE` or its choice) when `pangloss_reconcile` is installed; otherwise no pairs through near entities. Refused: not text; set while `pangloss_vectors` is not installed (among `INSTALLED_APPS` and importable); not a profile of `VECTORS_PROFILES`; a profile set here that weighs no part that knows names (a part of `pangloss_names`, told by its class, `NamePart`, not by any profile's or part's name: `settings.name_parts`). Reconciliation's choice is taken only where it weighs one; otherwise, as with no profile, there are no pairs through near entities (`near.state` `none`) and nothing is refused |
| `COMPARE_NEAR_K` | 5 | How many near entities each identifying entity is given. A whole number of 1 or more |
| `COMPARE_NEAR` | 0.6 | The least score (`Hit.score`) of a near entity. A number from 0 to 1. Only a floor: the score does not tell the right entity from a namesake ([measured](spaces-and-comparison-plan.md#64-the-entities-measured-2026-11-27-shown-to-the-user-before-building)); `COMPARE_NEAR_K` and the verdict decide |

### The route: `?near=true`

`GET /api/compare/{type}/{ref}?near=true` gives the same shape as without it, but `pairs` holds **only** the pairs
through near entities, and `near` says how they were sought. The interface asks for them apart, once the page stands:
each search costs 200 to 350 ms at 32,000 people (phase 8's figures), against 4 to 9 ms for the pairs by rule.
Without the parameter (or with `near=false`) the answer is the pairs by rule, as above, with `near` null. The same
404s; it writes nothing.

```json
{
  "statement": {"id": "01a2…", "type": "Birth", "label": "Ada is born", "head": {"id": "01a2…", "type": "Factoid", "label": "a birth"}},
  "pairs": [
    {
      "other": {"id": "01a3…", "type": "Birth", "label": "Ada is born, says another", "head": {"…": "…"}},
      "relation": "agree", "fields": [], "how": {}, "reported": false,
      "likelihood": 1.0, "within": null, "strength": 1.0, "superseded": false,
      "first": "01a2…", "second": "01a3…", "common": "Birth",
      "workedOut": {"relation": "agree", "fields": [], "how": {}, "reported": false},
      "found": "near",
      "by": [
        {
          "field": "person", "kind": "near",
          "entity": {"id": "01a0…", "type": "Person", "label": "Ada Lovelace"},
          "near": {"id": "01a1…", "type": "Person", "label": "Ada Lovelace"},
          "score": 0.86
        }
      ],
      "judged": null, "judgements": []
    }
  ],
  "more": false,
  "model": null,
  "near": {"profile": "who", "k": 5, "floor": 0.6, "state": "ok"}
}
```

Each reason: the field (its root name), the entity the statement names (`entity`) and the one near it the other
names (`near`), each with its id, class and label (for chips, and for a link to merging them), and the score. A
statement reached through several is one pair with every reason, nearest first. `near.state`: `ok`; `pending` (the
profile not built yet, or an entity with no vector yet) or `rebuild_due` (its vectors not of the dimension its parts
make today), as `nearest` answers, the worst of the searches (a search that is not ok gives nothing, the others
still do); `none`, no profile (`profile` null) or `pangloss-vectors` not installed. `model` is the fit the verdicts
were worked out with, as without `near` (null with `state` `none`).

**What it costs**: two read transactions of its own and a search between them for each identifying entity
(`nearest`'s own transaction). The first reads the statement and, in one statement, its label and its entities'
classes; the second the fit in use, the pairs by rule and the statements naming each X′ in one query (and the
merges), those read, their judgements and the labels. A birth: 3 transactions, 16 statements (6 of them the search);
a gathering of two people: 4 and 19 (the budget in `tests/live/near/test_compare_near_live.py`, the same on both
backends). Not measured at size: only the searches are, by phase 8.

**Tests**: `tests/test_compare_near.py` (each setting's refusal by its message, a profile that weighs no part of
names, reconciliation's choice taken and checked, the check at `initialise()`; the other read with X′ as X, in fields
and in what is prescribed; a source that is an X′ read so; no pair through an X′ a statement names beside X, and one
through two entities still given through the other; an X′ near two; a statement reached through two
entities; the statement itself and the pairs by rule left out, the cut, the places shared in turn across fields; `two` and
`nothing` not given, a namesake's birth told otherwise `disagree`, a gathering a century off not given; an order to a
namesake carried out; a judgement overriding), `tests/live/near/` on both backends, with the graph and name parts
and the profile `who` (two namesakes' births pair only so, both people in the reason, both ways; told otherwise;
a gathering a century off; a pair by rule not given again; never through a stand-in; a merged entity and a reference
a merge has not moved; an unpublished factoid and a reader not logged in; `pending` before a rebuild and `none` with no
profile, `rebuild_due` after the name part's dimension changed; `k`, the floor and the cut; a judgement overriding; nothing written, and the answer without `near` as
`compare` gives it; the budget), and `tests/live/test_compare_near_without_vectors_live.py` (vectors not installed:
`none`, no pairs, the same 404s).

### The route: `?other=ID` ✅

`GET /api/compare/{type}/{ref}?other=ID` (step 7.5, `compare.compare_pair`) gives the same shape with `pairs` holding
only the entry of `ref` with the statement `ID`, **found or not** and whatever `COMPARE_MOST_PAIRS` cut: what the maths
says of the two as they are (`maths.verdict`, the fit in use as for the others), `found: "asked"`, no reasons (`by`
empty), never `superseded`, and every judgement of the pair (either order), the newest overriding as anywhere. No
entry where `ID` is not a statement the reader may see of a compared class (the visibility of `reading.read`, as the
reader), or is `ref` itself. The same 404s for `ref`; with `near=true` too, a 422. It is for the page of two side by
side, which shows a pair the comparison does not find and lets it be judged: without it such a judgement could be made
and never shown. **What it costs**: one read transaction of at most seven statements (`reading.read` of the two, at most
four; the fit; the judgements; the labels), the budget in `tests/live/test_compare_route_live.py::
test_one_pair_is_given_whether_found_or_not`. A pair through near entities is not read with X′ as X here: the page
asks `?near=true` first.

## The interface ✅

Step 7.4 of [the plan](spaces-and-comparison-plan.md#phase-7-the-interface): the package's interface module
(`pangloss_compare/interface/`, its words in `translations/ui.jsonc`) adds an item section, `itemSections.Compared`,
after the contents of the page of a statement of a compared class, a head's or a nested one's. Which classes are
compared the interface learns from the export: the package adds `compared: true` to the `extras` of each such class
(`meta.definition_extras`, a function of `pangloss_models.hooks.definition_extras`), and the section asks the route of
those only, so the route's 404 for another class is never asked for. A statement of a compared class the route still
has no comparison of (a 404: one inside a space whose statements are not compared, `CompareMeta(compared=False)`) has
no section: nothing drawn, nothing logged, and the pairs through near entities are not asked.

- **The heading** is "Carried out?" where the route says the statement prescribes (`statement.prescribes`), else
  "Compared".
- **The rows**, in the route's order: the relation in words (a link to the page of the two side by side,
  `/compare/:type/:a/:b` by the nearest class both are: `pairHref` in `compared.ts`, the one place the address is
  made), the fields disagreed on ("on Town") or the targets missed ("(When: late)") by the fields' labels, "Reported"
  (the interface's own mark, `AssertionMark` with `status`), the other statement as a chip, "according to" each of its
  sources as a chip, "within the same source" or "document", and "Judged" by whom (the newest judgement; what the maths
  said in its title; "changed since it was judged"). The likelihood is the row's title only. `two` and `nothing` are
  not shown; the superseded are folded behind "N more, superseded", and **the pairs a person judged two events** behind
  "N judged two events" (each a button with `aria-expanded` and `aria-controls`, the rows in the element it controls);
  `more` is a line.
- **The pairs through near entities** are asked by themselves (`?near=true`) in the browser once the rest is drawn, in
  a boundary of their own, so the rest neither waits nor moves: under "If these are the same {class}", one group for
  each two entities (X and X′, the pair's first reason, the nearest; an entity whose class was not read, one deleted
  since, makes no group and no link), their chips and score (a bar and the figure, as "Similar" has it), "Compare, or
  merge" (the merge page of `pangloss_interface`, `/:type/:id/merge/:other`) for someone logged in, then the pairs as
  rows. Nothing is drawn where there is nothing to show nor say (`none`, `ok` with none, `rebuild_due` to someone
  logged out); `pending` and `rebuild_due` (to someone logged in) say so in a line. The section's `data-near-settled`
  says when they have come (or failed), for a test that waits on them.
- **Nothing to compare with**: a line, until the pairs through near entities say otherwise.
- Read again on login and logout; nothing in it writes.

### The page of two side by side ✅

Step 7.5: the module's route `/compare/:type/:a/:b` (`PairPage.tsx`; each row's relation links there). The page reads
`GET /api/compare/{type}/{a}` and takes the entry of `b`; without one, the pair by itself (`?other=b`, [above](#the-route-otherid-)),
and, in the browser only, `?near=true` (its searches cost far more: never on the server, never where the plain answer
has the pair; a failure of it is no failure of the page), whose entry is preferred once it has come. A pair the
section links is always in the plain answer or the near one (the same cut); one found by neither (typed in, or judged
where the comparison found nothing) has its judgements only in `?other=`. The two statements are read by the ordinary
`GET /api/{type}/{id}`, **each by its own class** (the route gives it: the nearest class both are may be none). All of
it is read again on login and logout; after a judgement is recorded or deleted, only the answer the pair's entry came
from.

- **Not found** (the interface's ordinary page): a class that is not compared, an unknown id or class, a statement
  the reader may not see (logged in through the dialog, the page appears without a reload), or one the route has no
  comparison of.
- **Above**, what is said of the pair: the relation in the words of the section's rows (a person's judgement where
  one overrides, also of a pair the comparison did not find), the fields, "Reported", "within the same
  source/document", the likelihood as a small figure, and, where a person judged it otherwise, what the maths worked
  out ("Worked out: no relation" of a pair it did not find). Of a prescription said to be carried out (or otherwise),
  **each target met or missed**, from what the entry itself says: missed, the fields the entry names (a person's
  judgement's, by the maths' word for that field where the maths says it too, else only "missed"; else the maths',
  `late`, `early`, `different`, `in part`); met, a field of the nearest class whose rows are filled and the same on
  both sides (the alignment's marks), never by default. None where the pair is said to be anything else. For a pair
  through near entities: "If these are the same {class}", the two as chips, their score and "Compare, or merge", as
  the section's group. Where nothing is said: "The comparison found no relation between these two"; the two are side by
  side all the same, and may be judged.
- **Side by side**: the prescription first where one is (the entry's `first`), else `a`; each column headed by its
  statement as a chip and "according to" its sources; the rows are core's `align` of the two on the fields of the
  nearest common class (`type`), with `{ pair: "place" }`: parts matched by an id both have (an entity both name),
  else by place, so two towns in one field are one row, the second marked changed; two entities of one class and label
  (namesakes) at one place are changed too, being two; parts of two types at one place (a wrapper beside a plain
  entity, two documents of different classes) one row, changed, with what each holds drawn on its own side. Each cell
  is marked as history's compare page marks a version (`CELL_TONE`, `ChangedValue`, now core's). Then, under "Fields of
  one of the two only", the fields the class of one has and the common one has not. The label is the head of each
  column, not a row.
- **"Your judgement"** (someone logged in only): **the verdicts that fit the pair** as one choice of several
  (`fittingVerdicts`, by what the route says of the two statements, not by what the maths made of the pair, so a pair
  the maths says `nothing` of can still be judged): of two that describe, agree, disagree, two events; of an order and
  what came of it, carried out, carried out otherwise, not carried out, done but not carried out, two events; of a
  prohibition, breached, complied with, two events; of a permission, permission used, two events (by `prescription`).
  None, with a line saying why: two prescriptions; one of the two says nothing either way (`says` `neither`) or
  prescribes something of no kind; the two of classes not related (no class both are). For `disagree` and
  `carried_out_otherwise`, which fields: the fields of the nearest class a person writes, as checkboxes by their labels,
  ticked as the comparison found them (`workedOut.fields`), sent in camelCase (`startingPoint`). A note. "Record" posts
  the project's class of judgement by the ordinary create, the prescription in `statement`: the class is the first by
  name of those below `EventJudgement` whose `statement` and `other` can cite the two classes (the package adds
  `judgement: true` to the `extras` of each such class, and the export's `cites` says what each field may cite); of two
  that describe, a class that cites them only the other way round is taken after, with the two swapped. With none, no
  controls and "The project declares no judgement for these statements". Its label is the verdict and the two
  statements' labels **in the project's default language** (`tDefault`), whatever the language of the one who records
  it: it is every reader's chip (a label template was not used: it cannot read a cited statement's label). A refusal
  is said as a refused save is: a red toast, and the message at the part it is about (`placeProblems`).
- **The judgements** of the pair, newest first (by creation, then by id, the greater first: the same rule as
  learning's `newest`): each its chip (to its own page), the verdict in words, the fields, the note, who (as the
  interface names users) and when, "changed since it was judged"; **Delete** for someone logged in (the API lets any of
  them delete a document; core's dialog, `DeleteItemDialog`, asks `/deletable` first, in the reader's language).
- **No edit of a judgement anywhere**: the package says a judgement is never updated (`hooks.not_updated`, exported as
  `updatable: false`); the item page then has Delete and no Edit, and its `/edit` says it is not changed once made
  (core's `canUpdate`).

Tests: the module's Vitest (`compared.test.ts`, `pairPage.test.ts`: the verdicts that fit, the class of judgement,
the targets, the rows; `ComparedSection.test.tsx`; run in a built project, `e2e/test_module_unit_tests.py`); core's
`alignPairs.test.ts` (the pairing by place); `e2e/test_compare.py` on the e2e project's `Account`, `Baptism`,
`Journey`, `Command`, `Prohibition`, `Permission`, `Fiction` and `PairJudgement` (the page from a row, the ten
verdicts each recorded on a pair it fits, the fields sent and shown, the section changed, a judgement deleted, no
edit, a pair with no relation, the near pair's page, a statement not compared); and
`e2e/test_dev_mode.py::test_the_compared_section_and_whose_claim_a_head_holds`.
