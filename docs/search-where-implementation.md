# Typed search patterns: `Model.Where` 🚧

A plan (2026-11-01) for writing a structured search (see [Structured search](structured-search.md)) with a pydantic
class generated for each model, so that the SDK, an editor and a type checker know which fields a pattern can have,
which operators each takes, and what type its values are:

```python
Letter.search(
    Letter.Where(
        sender=Rel(is_=smith.id),
        date=Compare(lt=date(1600, 1, 1)),
        title=Text(contains="plague"),
        addressee=Person.Where(label=Text(contains="venice")),   # the class is the `type`
        any_of_=[Letter.Where(...), Letter.Where(...)],
    ),
    page_size=25,
)
```

## What does not change

- **The JSON, and the API.** A `Where` is a way of *writing* the pattern in Python: it dumps to exactly the JSON
  `POST /api/search` takes now. The route, `SearchRequest`, the interface and its TypeScript are not touched, and the
  per-model classes are not put in the OpenAPI schema (with every relation's targets nested in, it would be huge and
  cyclic). So the API is no more complicated than it is.
- **`check_match` is the one validator.** A `Where` turns into the JSON, the JSON goes through `parse_where` and
  `check_match` as it does now. Pydantic, when a `Where` is made, catches what the types can: a field that does not
  exist, an operator that does not fit the field's kind, a value of the wrong type. `check_match` still catches the
  rest (a relation's pattern of a type it does not allow at runtime, `$somewhere` inside a pattern, the limits).
- **Dicts still work**, and `Match` still works: nothing that is written now has to change.

The cost is in `pangloss-models` (the generation, a few hundred lines) and `typestubs.py`, and that there is one more
generated class per model to keep in step with `check_match`. That is kept in step by building both from the same
tables (`OPERATORS`, `kind_and_base`), and by a test that compares them for every model (step 4).

## The classes

### Operators, one class for each kind of field

In `pangloss_models.search_where`:

| Class | For | Fields (as in `OPERATORS`) |
|---|---|---|
| `Text` | `str`, `label`, `review_status` | `eq ne in_ exists contains starts_with` |
| `Compare[T]` | `int`, `float`, `Decimal`, `date`, `datetime` | `eq ne in_ exists gt gte lt lte between` |
| `Choice[T]` | `bool`, an enum | `eq ne in_ exists` |
| `Items[T]` | `list[...]` of any of these | `contains contains_any contains_all exists` |
| `Rel` | a relation, an embedded field | `is_ is_any exists through`, and `match` (a `Where`) |
| `AnyRel` | `$any`, `$mentions` | what `Rel` has, and `contains starts_with` (of the label) |
| `IncomingFrom` | `$incoming` | `where` (a `Where`: its class is the `type`), `field`, `through` (a `Where` alone will do, for any field) |

`T` is the field's type, so `date=Compare(lt="x")` is an error to pydantic (`Compare(...)` given to a field typed
`Compare[datetime.date]` is checked as one), and should be to a type checker: pyright checks the arguments of a
generic pydantic class; `ty` (0.0.90) does not yet, though it does those of `Text` and `Rel`, and the names of all. `is_` and
`is_any` take an id, or anything with an `id` (an entity, a reference view): `Rel(is_=smith)`. `through` takes the
wrapper classes or their names. Each class is `extra="forbid"`, and dumps to the dict of a condition.

### `Model.Where`, one for each model

Made by `initialise_models` for every `Document`, `Entity` and `Embedded` model (abstract ones too), next to `Create`,
`HeadView` and the rest:

- **A field for each field of the model that can be searched**, typed by its kind: `Text | None`,
  `Compare[datetime.date] | None`, `Items[str] | None`, and so on. Fields that cannot be searched yet (the ones
  `kind_and_base` refuses) are left out, so that a type checker says so.
- **A relation or embedded field** is `Rel | A.Where | B.Where | None`, for the root classes it can point at. A
  `Where` given directly is the pattern; `Rel(match=A.Where(...), through=[Negative])` is a pattern with the rest.
- **The `Where` classes do not inherit as the models do**: the fields of a generated class are put on it after it
  is made, and a subclass does not take those. A relation's options have its subclasses in them already, so the
  union of their `Where` classes is each class it can point at.
- **`label: Text`**; on a document, `published: Choice[bool]` and `review_status: Text`.
- **The `$` keys** as fields with a trailing underscore and the `$` name as alias: `all_`, `any_of_` (lists of the
  same class), `not_`, `any_`, `mentions_` (`AnyRel`), `somewhere_` (a list of any document's `Where`), `incoming_`
  (a list of `Incoming`, entities only), `spaces_` (semantic space classes or names, documents only). A model with a
  field of one of those names is an error when the models are initialised (none has one now).
- **`to_json()`** gives the dict of the pattern (the fields of the model, then the `$` keys); a `Where` nested as a relation's pattern is written
  `{"type": "<its class>", "where": {...}}`.

`published`, `review_status`, `somewhere_` and `mentions_` are only for the head node of a search, and `spaces_`
only for a document in one: they are on the one class, and `check_match` refuses them where they do not belong, as
it does now (see the decisions).

## Plan, in steps that each work alone

0. **The SDK checks a search before it sends it, and stubs have `search`.** `api` and `api_sync` call `check_match`
   before `POST /api/search` (the error is the same, raised locally). `operations_source` in `typestubs.py` has no
   `search` now: add it (taking `Match`, for now). Small, and of use without the rest.
   **Built:** `protocol.search(cls, match, ...)` checks the pattern (and gives it the class's `type` if it has none)
   for both clients; the stubs have `search`, and the SDK's `ty` check uses it.
1. **The `$` keys as an enum.** A `StrEnum`, `SearchKey` (`ALL = "$all"`, `ANY_OF`, `NOT`, `ANY`, `MENTIONS`,
   `SOMEWHERE`, `INCOMING`, `SPACES`), used by `parse_where`, `check_where` and the aliases of the `Where` fields
   in place of the strings written in each (and of `ANY_RELATION` and `ANY_IN_DOCUMENT`). As a `StrEnum` is a
   `str`, a dict can be written with them (`{SearchKey.ANY_OF: [...]}`) and dumps to the same JSON, and the strings
   are still taken. The model export (`export.py`) gives the interface the list, so its TypeScript has them as a
   type from the same place (with `types/models.ts` and its guard test updated).
   **Built**, but not through the export: the export is also what a migration snapshot holds, and the keys are the
   same for every project, so they would be in every snapshot. The interface has the type `SearchKey` in
   `interface-core/src/api/types.ts` instead, and `test_models_match_typescript.py` checks it against the enum, as
   it does `Colour`. `ANY_RELATION` and `ANY_IN_DOCUMENT` are gone (the Cypher and Neo4j compilers use the enum).
2. **The operator classes**, and `parse_where` taking them where it takes a `Condition` now (by their dump, so there
   is one path into `Condition`). Tests: each dumps to the dict it stands for; each refuses an operator its kind
   does not take; values are typed.
   **Built**, in a module of its own (`search_where.py`): the operator classes, `IncomingFrom`, and the bases of the
   generated classes (`Where`, with the combinators and `any_`; `DocumentWhere`, `EntityWhere` and
   `EmbeddedWhere`, with what each kind has). `parse_where` takes a `Where`, and any of the classes as a value in a
   dict, by `where_json`: so a dict may mix the two.
3. **One table of kinds.** Split `kind_and_base` into a function that says the kind and base of a field definition
   (or that it cannot be searched) without raising, used by both `check_where` and the generation, so that the two
   cannot differ about a field.
   **Built:** `field_kind(definition)` gives the kind and base, or the reason as a string; `kind_and_base` raises it.
4. **Generate `Model.Where`** in `ModelRegistry.finalise`, as `Create` is: first a class for each model with its
   literal fields, then the relation, embedded and `$` fields (they refer to each other's classes: `Person.Where`
   to `Letter.Where` through `incoming_`), then `model_rebuild`. With `defer_build=True`, so that a class's schema is
   only made when one is first used (the time of `finalise` is measured before and after, on the demo models).
   Tests:
   - for every model of the test and demo models, each field of `Where` has the kind `check_where` finds, and each
     operator class has the fields `OPERATORS` gives that kind (the guard against the two drifting apart);
   - the examples in `structured-search.md`, and the patterns of `test_search_match.py`, written as `Where`, dump to
     the same dict and `check_match` gives the same result;
   - cycles (an `Order` of a `Statement` that may be an `Order`) nest without limit.
5. **`search` takes a `Where`.** `search(cls, pattern: Match | Where | None = None, *, order_by=None,
   page_number=None, page_size=None)` in the Cypher backend (`read_functions.search`), the SDK's `api` and
   `api_sync`, and anything else that binds `search`. A `Where` of another class than the one searched is an error
   (call `search` on that class). One conformance test (`pangloss-testing`) searches with a `Where`, so every
   backend runs it.
6. **Stubs.** The `Where` classes are nested classes of the models, so `generated_classes` already finds them; what
   is needed: `TypeRenderer` writes `Compare[datetime.date]` and the like, the fields are written by their Python
   names (pyright and ty take the constructor's parameters from them, and `validate_by_name` lets them be used),
   and the stub's `search` takes `Letter.Where | Match`. `pangloss make-stubs` and the SDK builder (its async and
   sync stubs) both use `stub_for_module`, so both get them. Tests: `test_stub_source.py` for the source, and the
   SDK server's `typecheck` test with a usage file that searches with a `Where`, and one with a wrong field and a
   wrong operator that `ty` has to refuse.
7. **Docs, and the uses.** `structured-search.md` (a section on `Where`, the dict form kept as the JSON),
   `sdk.md`, `generated-models.md` (the list of generated classes), the guide/tutorial where it searches, and
   `pangloss-dates/query.py` and the tests where a `Where` reads better.

## Decisions (answered 2026-11-01: as recommended)

1. **The name.** Recommended: `Letter.Where`, as it is the `where` of the JSON. (`Letter.Pattern`, `Letter.Search`.)
2. **The `$` keys.** Recommended: fields with a trailing underscore (`any_of_`, `not_`), as above. Also possible,
   later and on top: `Letter.Where(a) | Letter.Where(b)` for `any_of`, `~w` for `not`, `&` for `all`.
3. **Keys only for the head node.** Recommended: on the one `Where`, checked by `check_match`. The other way is a
   `Letter.Search` (a `Letter.Where` with `published`, `review_status`, `somewhere_`, `mentions_`) for the head of a
   search, and `spaces_` only on the `Where` of a document used inside one: a type checker would catch more, at the
   cost of two classes for each document model.
4. **`order_by`.** Recommended: a keyword of `search`, so that a `Match` is not needed with a `Where`; `Match` still
   taken. A typed `order_by` (the fields that can be ordered by, as a `Literal`) can come later.
5. **The interface.** Out of this plan: it writes the JSON. TypeScript types for patterns, from the export, would be
   the same idea for it, and could be done after.
