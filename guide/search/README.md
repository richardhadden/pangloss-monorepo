# Searching

Three ways to find things, from simplest to most precise. All work on the server, over HTTP, and through the
[SDK](../sdk/README.md) with the same call.

| | For |
|---|---|
| `Model.list(search_terms=…)` | A page of everything of a type, by words in the label |
| `Entity.autocomplete(text, types=…)` | The entity someone is typing the name of |
| `Model.search(Letter.Where(…))` | "Letters from Smith to anyone in Venice before 1600": a pattern |

## Lists

```python
page = await Person.list(search_terms="charl", page_size=20, page_number=1)
page.results        # reference views: id, type, label, meta
page.count          # how many in all
page.next_page      # None on the last page
page.truncated      # True if a word matched more than SEARCH_HIT_LIMIT: there are more than `count`
```

Every word of `search_terms` has to occur in the label, at the start or in the middle of a word, in any case. Over HTTP:
`GET /api/Person?q=charl&page=1&page_size=20`. The list includes subtypes: `Statement.list()` has the `Activity` and
`Transfer` statements.

`deep_search=True` (`?deep=true`) looks further: it finds a document that has the words anywhere in the nodes inside
it, or a person through the documents that refer to them. It scans the text index, so it is slow on a large database (40
to 50 s on 640,000 nodes was measured before it was rewritten; now 0.1 to 2.4 s). The interface runs it only when asked.
A search that takes longer than `SEARCH_TIMEOUT_SECONDS` is a `504`. See [Deep search](../../implementation_docs/deep-search.md).

To go through everything: `pangloss_sdk.iterate(Person.list, page_size=100)`.

## Autocomplete

```python
await Person.autocomplete("smi")                             # Persons (and subclasses) whose label has "smi"
await Entity.autocomplete("smi", types=[Agent, Place])       # either
```

`GET /api/autocomplete?q=smi&type=Person&type=Place`. Only entities are found. Labels that **begin** with the text come
first, then by the text index's score, then alphabetically. A `type` that is not an entity type is a 422. Pages are
10 by default, at most 50. [Autocomplete](../../implementation_docs/autocomplete.md) has the rest.

## Structured search

A pattern written as JSON, compiled to one query on the server. Only names of fields in your models are used; values are
always parameters.

```python
from pangloss_models import Match

page = await Letter.search(Match(where={
    "sender":    {"is": str(smith.id)},                       # a relation to an entity, by id
    "date":      {"lt": "1600-01-01"},                        # a literal
    "title":     {"contains": "plague"},
    "addressee": {"type": "Person", "where": {"label": {"contains": "venice"}}},   # a nested pattern
}), page_size=25)
```

Over HTTP it is `POST /api/search` with `{"type": "Letter", "where": {...}, "page": 1, "page_size": 25}`.

### Written as Python: `Letter.Where`

Each document, entity and embedded model has a `Where` with a field for each of its fields that can be searched, so an
editor completes them and a type checker (with the stubs: `pangloss make-stubs`, or the SDK's) says when a field is not
there or the operator is not one it takes. It is the same search: it is made into the JSON above.

```python
import datetime
from pangloss_models import Compare, Rel, Text

page = await Letter.search(
    Letter.Where(
        sender=Rel(is_=smith),                                    # an entity, or its id
        date=Compare(lt=datetime.date(1600, 1, 1)),
        title=Text(contains="plague"),
        addressee=Person.Where(label=Text(contains="venice")),   # a nested pattern: its class is the type
    ),
    page_size=25,
    order_by=["title"],
)
```

| Field is | Written |
|---|---|
| text, `label` | `Text(eq=…, in_=[…], contains=…, starts_with=…, exists=…)` |
| number, date, datetime, `Decimal` | `Compare(gt=…, lte=…, between=(a, b), …)` |
| `bool`, enum | `Choice(eq=…, in_=[…])` |
| list of literals | `Items(contains=…, contains_any=[…])` |
| relation, embedded object | `Rel(is_=…, is_any=[…], exists=…, through=[Negative], edge=Certainty.Where(…), via=[…], match=Person.Where(…))`, or the `Where` alone |

`a | b`, `a & b` and `~a` are `any_of_`, `all_` and `not_` (of two `Where`s of the same class): `Letter.Where(title=
Text(eq="Bare")) | ~Letter.Where(sender=Rel(is_=john))`. The `$` keys are fields with a trailing underscore:
`any_of_=[Letter.Where(…), …]`, `all_`, `not_`, `any_` and
`mentions_` (`AnyRel(is_=…)`), `somewhere_=[Place.Where(…)]`, `spaces_=[Negative]`, and on an entity
`incoming_=[Letter.Where(…)]` (or `IncomingFrom(where=Letter.Where(…), field="sender")`). In a dict the keys can
be written as `SearchKey.ANY_OF` and the like (`pangloss_models.search`). A `Match` and the dicts still work, and
the two can be mixed.

### Conditions

| Field is | Conditions |
|---|---|
| text | `eq`, `ne`, `contains`, `starts_with` (not case-sensitive), `in: [...]`, `exists` |
| number, date, datetime, `Decimal` | `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `between: [a, b]`, `in`, `exists` |
| `bool`, enum | `eq`, `ne`, `in`, `exists` (an enum is compared as its value) |
| list of literals | `contains`, `contains_any`, `contains_all`, `exists` |
| annotated value | the conditions of its value, and `certainty` |
| relation to an entity | `{"is": id}`, `{"is_any": [ids]}`, or a nested pattern `{"type": …, "where": …}` |
| relation to a document | a nested pattern, or `{"exists": true}` |
| embedded object (a date) | `{"type": "JulianExactDate", "where": {"sort_day": {"between": [a, b]}}}` |

Several keys in one `where` must all hold. Combine with `$all`, `$any_of` (lists of `where`) and `$not`.

### Looking across the whole node or document

| Key | Means |
|---|---|
| `$any` | Some relation of this node: `{"$any": {"is": id}}` is any relation field pointing at `id`; `{"$any": {"contains": "plague"}}` is of the label (there is no text index over the other fields yet) |
| `$somewhere` | These patterns each occur **anywhere in the document** below this node |
| `$mentions` | The short form of the commonest `$somewhere`: an entity (by id) is mentioned anywhere in the document |
| `$spaces` | The node is inside these semantic spaces (`["Negative"]`) |
| `$incoming` | An entity by what refers to it: `[{"type": "Letter", "field": "sender", "where": {…}}]` (`field` can be left out: any relation that can point at it) |

With `pangloss-derived`, a document also takes `$derived_document` (`true`: written by a rule; `false`: not).

Relation conditions see **through** semantic spaces, conjunctions and reified relations, so `has_statement` matches a
statement inside `Negative[...]`.

To ask more of the way: `through` names wrappers the relation has to pass through, and a step of it can say what one
has to be; `edge` is of the edge that reaches what the relation points at, by the fields of its edge model
(`ViaEdge[Person, Certainty]`); `via` ([below](#a-relation-by-the-way-it-goes-via)) asks of any place of the way, in
order, whether it is an edge or a wrapper.

```python
# given by Smith, as an alternative of 60 per cent or more
Transfer.Where(given_by=Rel(
    is_=smith,
    through=[Through(WeightedAlternative, edge=Likelihood.Where(percent=Compare[int](gte=60)))],
))
# identified by Jones, whoever it is
Transfer.Where(given_by=Rel(through=[Through(Identification, where=Identification.Where(identified_by=Text(eq="Jones")))]))
# witnessed by someone with a certainty of 8 or more
Transfer.Where(witnesses=Rel(edge=Certainty.Where(value=Compare[int](gte=8))))
```

```json
{"given_by": {"is": "0194…", "through": [
  {"type": "WeightedAlternative", "edge": {"type": "Likelihood", "where": {"percent": {"gte": 60}}}}
]}}
```

An edge model and a wrapper each have a `Where` of their own values for this. A wrapper's `Where` can also ask which
its own relations are (`InRole.Where(role=baker)`: "in the role of baker", where the role is an entity), by `is_`,
`is_any` and `exists`. An edge knows which edge model it is of, so a condition by `Certainty` is about `Certainty`
edges only: an edge of another edge model is not found, even one with a field of the same name, and "has no note"
(`exists: false`, `ne`, `~`) means a `Certainty` edge with no note. A wrapper named in `through` or `via` is that
class or one below it.

#### A relation by the way it goes: `via`

`through` and `edge` make you know where a value is stored: on a wrapper (a node) or on an edge. `via` does not. It
lists the places of the relation's way, in the order the annotation nests them, and each place is either an edge
model or a wrapper. Other places may lie between; the order matters.

```python
class Doc(Document):
    person_involved: list[ViaEdge[InRole[Person], Certainty]]   # a sure edge into a role, then the person

# John, by an edge with a certainty of 8 or more, into a role that is the baker
Doc.Where(person_involved=Rel(
    is_=john,
    via=[Certainty.Where(value=Compare[int](gte=8)), InRole.Where(role=baker)],
))
```

```json
{"person_involved": {"is": "0194…", "via": [
  {"type": "Certainty", "where": {"value": {"gte": 8}}},
  {"type": "InRole", "where": {"role": {"is": "0195…"}}}
]}}
```

- Nothing has to be asked of an item: `via=[Certainty, InRole]` is "by a `Certainty` edge, then an `InRole`".
- Everything else in the condition (`is_`, a pattern, `exists`, `through`, `edge`) is about the same way. With
  `exists=False` it finds what has no relation by such a way.
- `$any`, `$mentions` and `$incoming` take it too: `IncomingFrom(where=Doc.Where(), field="person_involved",
  via=[…])`. In `$incoming` the order is still the order of the referring document's field.
- What cannot be: an edge model the field never has, a wrapper it never passes through, a wrapper left out by
  `exclude_wrappers`. Each is refused with a message that names the item (`person_involved.via.0`).
- Not yet: the search form does not offer `via`, and a derived rule cannot use it.

To leave wrappers out, for the whole search: `exclude_wrappers`. What a relation would reach only through one of them
is not found ("the transfers this person is named in, not those where they are one of several alternatives"):

```python
await Transfer.search(Match(where=Transfer.Where(given_by=maximilian), exclude_wrappers=["WeightedAlternative"]))
```

```json
{"type": "Transfer", "where": {"given_by": {"is": "0194…"}}, "exclude_wrappers": ["WeightedAlternative"]}
```

### Order and visibility

`order_by`: up to three of `{"field": "label" | "year" | "when.sort_day", "direction": "asc" | "desc"}`, including fields of
embedded objects (a date's `sort_day`). In Python, `search(..., order_by=["year", Factoid.Order(field="when.sort_day",
direction="desc")])`: `Factoid.Order` takes only what a `Factoid` can be ordered by, and so does a name, to a type
checker with the stubs. Ties are ordered by label. A request that is not logged in finds no deleted and no
unpublished document, whatever it asks; `published` and `review_status` are conditions too, with
[`pangloss-review`](../review/README.md).

### Indexes

Every class of document and entity has a label index. Fields you search often can ask for one:

```python
class Factoid(Document):
    _meta = Document.Meta(indexes=["year"])
    year: int
```

`pangloss makemigrations` / `migrate` make it.

[Structured search](../../implementation_docs/structured-search.md) has the design, the limits, and what was measured on 640,000 nodes
(every search under a second; none needs more indexes than Pangloss makes).
