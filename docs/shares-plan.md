# Shares: percentages that add up to 100

A conjunction whose members each have a share (how likely each alternative is), the shares kept to a sum
of 100: declared with primitives, offered ready-made by a small library app, edited with sliders that
give way to each other.

Built 2026-11-03 (uncommitted). Decisions (the user, 2026-11-03): primitives and a library type built from them; a share is 1 to 100;
the server refuses what does not add up to exactly 100; the others give way in proportion.

## Declaring it

```python
from pangloss_models import SumsTo
from pangloss_interface import Slider

class Probability(EdgeModel):
    percent: Annotated[int, Ge(1), Le(100), Slider()]

class Alternative[T](Conjunction):
    alternatives: Annotated[list[ViaEdge[T, Probability]], SumsTo("percent")]
```

- **`SumsTo(field, total=100)`** (`pangloss_models.validators`) is an `annotated_types.BaseMetadata`, so
  it is one of the field's `validators`: exported as `{"name": "SumsTo", "field": "percent", "total": 100}`
  as the others are, and not part of the migration snapshot. It is allowed only on a list relation whose
  options all have an edge model with an `int` field of that name (or a type variable with one,
  `list[ViaEdge[T, Probability]]`). Anything else is refused when the models are initialised. It works
  on any list relation, not only a conjunction's.
- **`Slider()`** (`pangloss_interface`) is a field marker, a new kind: what a literal field is annotated
  with to say how the interface edits it. It is allowed on an `int` or `float` field with a lower and an
  upper bound (`Ge`/`Gt` and `Le`/`Lt`), and is refused at export otherwise. Literal fields now have
  `markers`, and the export gives them as it does for embedded fields (`FieldMarker` is the base class,
  in `pangloss_models.markers`). `Slider` does not need `SumsTo`, and `SumsTo` does not need `Slider`.

## The server

The models that are written (`Create`, `Update`, `CreateDB`, `UpdateDB`) get a model validator,
`check_shares`, wherever a relation has `SumsTo`. It checks that the items' `edge_properties.<field>`
add up to `total`, and refuses the save otherwise ("the percent of alternatives add up to 90, not 100").
An empty list passes (there is nothing to share). Reading (`View`, `check-data`) is not checked.

## The library: `pangloss-library`

This is a new workspace package and app (`INSTALLED_APPS += ["pangloss_library"]`), with its own
migration `0001_initial`:

- `Likelihood(EdgeModel)`: `percent: Annotated[int, Ge(1), Le(100), Slider()]`
- `WeightedAlternative[T](Conjunction)`: `alternatives: Annotated[list[ViaEdge[T, Likelihood]], MinLen(1), SumsTo("percent")]`

Its names are not the demo's (`Alternative`, `Probability`), because model names are global. The
demo's `Alternative` keeps its own models and uses the primitives (adding `SumsTo` and `Slider`). The
library is not in the demo's `INSTALLED_APPS`: unused, it would only be a migration to apply. The e2e
project installs it (`Suspicion.suspects: WeightedAlternative[Person]`), so its migration is made and
applied in a new project there.

## The interface

- **Slider:** `LiteralEditor` draws an `int`/`float` field with the `Slider` marker as `<input type=range>`,
  bounded by the field's bounds, with the number beside it.
- **Giving way** is `schema/share.ts`, made of pure functions:
  - `apportion(weights, amount, min)`: integers, each at least `min`, adding up to `amount`, in
    proportion to `weights` (above `min`), with the remainders going to the largest fractions. If the
    weights are all at `min`, the amount is shared equally.
  - `adjust(shares, index, value, total, min)`: the one at `index` is set to `value` (kept within what
    leaves the others their `min`), and the others share the rest in proportion to what they had
    (60/30/10, first to 80: 80/15/5).
  - `added(shares, total, min)`: a new one gets `total / (n + 1)`, and the others share the rest in
    proportion (50/50, then a third: 33/33/34 by remainders).
  - `removed(shares, index, total, min)`: the others share the whole in proportion.
- **The form** applies them through a second form hook beside the binder (`createSharer(definitions)`,
  with the same `before`/`after` as `FormBinder`, composed with it by `composeBinders`). Each `set` and
  `remove` under a relation with `SumsTo` is one of these:
  - setting `[..., field, i, "edgeProperties", key]` (or `edgeProperties` as a whole): adjust
  - setting an item at the end of the list: added
  - replacing an item (an entity chosen for it): it keeps its share; if it had none (one there from
    the start), it is given an even share
  - removing `[..., field, i]`: removed

  So dragging one slider moves the others as it is dragged, and adding or deleting an alternative
  shares again. Shares that did not add up when loaded (old data) are made to add up by the first
  change.
- **The client check** (valibot): a list with `SumsTo` is red at the list if its shares do not add up,
  as the server would refuse it.

## Tests

- **pangloss-models:**
  - `SumsTo` is refused on a literal field, a single relation, options without an edge model, or an
    edge model without the field (or with it not an `int`).
  - It is exported.
  - `Create` refuses 90 and accepts 100, directly on a document and on a conjunction through a type
    variable.
- **Conformance:** a write is refused when the shares don't add up, and one that adds up is written
  and read back.
- **pangloss-interface (Python):** `Slider` is exported as a marker of a literal field, and refused on
  a `str` field or on a field without bounds.
- **interface-core (vitest):**
  - `share.ts`: proportions, minimums, rounding, all at the minimum, one alone is the total.
  - The sharer through `createItemFormState`: drag, add, replace, remove.
  - The valibot check.
  - The slider renders as a range with the bounds.
- **pangloss-library:** the models initialise and its migration has no changes left to make
  (`makemigrations --check` in a test).
- **e2e:** the demo's factoid form: add two alternatives (50/50), drag one to 70 (the other goes to 30),
  add a third, then delete one. Also recorded in e2e/COVERAGE.md.

## Found on the way

The validators of a generic wrapper's fields (`MinLen`/`MaxLen` on `Identification.target`,
`MinLen(1)` on `WeightedAlternative.alternatives`) were not checked by the server, only by the
interface: the builder gave them to the field as `metadata=`, which pydantic does not apply. They are
now given as the fields of any model's are (`map_validators_to_kwargs`), with a test for it
(`test_wrapper_field_validators.py`).

## Left out

- A lock on a share, so it does not give way.
- A "share equally" button.
- `float` shares (`SumsTo` wants `int`).
- `DerivedMeta(exclusive=True)` on the library's `WeightedAlternative`, which would make it depend on
  pangloss-derived.
