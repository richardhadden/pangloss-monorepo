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
A search that takes longer than `SEARCH_TIMEOUT_SECONDS` is a `504`. See [Deep search](../../docs/deep-search.md).

To go through everything: `pangloss_sdk.iterate(Person.list, page_size=100)`.

## Autocomplete

```python
await Person.autocomplete("smi")                             # Persons (and subclasses) whose label has "smi"
await Entity.autocomplete("smi", types=[Agent, Place])       # either
```

`GET /api/autocomplete?q=smi&type=Person&type=Place`. Only entities are found. Labels that **begin** with the text come
first, then by the text index's score, then alphabetically. A `type` that is not an entity type is a 422. Pages are
10 by default, at most 50. [Autocomplete](../../docs/autocomplete.md) has the rest.

## Structured search

A pattern written as JSON, compiled to one query on the server. Only names of fields in your models are used; values are
always parameters.

```python
from pangloss_models.search import Match

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
from pangloss_models.search_where import Compare, Rel, Text

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
| relation, embedded object | `Rel(is_=…, is_any=[…], exists=…, through=[Negative], match=Person.Where(…))`, or the `Where` alone |

The `$` keys are fields with a trailing underscore: `any_of_=[Letter.Where(…), …]`, `all_`, `not_`, `any_` and
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

Relation conditions see **through** semantic spaces, conjunctions and reified relations, so `has_statement` matches a
statement inside `Negative[...]`.

### Order and visibility

`order_by`: up to three of `{"field": "label" | "year" | "when.sort_day", "direction": "asc" | "desc"}`, including fields of
embedded objects (a date's `sort_day`). Ties are ordered by label. A request that is not logged in finds no deleted and no
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

[Structured search](../../docs/structured-search.md) has the design, the limits, and what was measured on 640,000 nodes
(every search under a second; none needs more indexes than Pangloss makes).
