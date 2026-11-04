# Interface: collapsed reified relations and conjunctions (view only)

Written 2026-11-03. **View only**: nothing changes in the API, the stored data or the edit form.

## What it is for

`Identification[Alternative[ViaEdge[Person, Probability]]]` takes two nested blocks to say "this is
probably Smith" in the common case. When a model allows it, the item page shows such a value as the person's chip
(with its edge properties, as now), followed by any filled-in own fields as labelled text (`IDENTIFIED BY Smith`).
A small tinted marker in the colour of the relation's type comes before the chip. Clicking it shows the whole
structure in place, and a fold button on the head bar collapses it again.

## Where the rule lives

On the model, as `InterfaceMeta(collapse=...)`, inherited the same way as the other fields:

- `collapse=True`: the built-in rule (below). This covers `Identification` and `Alternative` without any code.
- `collapse=Collapse(blocking=[...], hidden=[...], when={...})`: the built-in rule with conditions on the
  model's own fields, by name (below). Declarative: exported as JSON, no app code.
- `collapse="<app>:<name>"`: a TypeScript predicate `(item, model) => boolean` in `collapseRules` of the app's
  interface module manifest (`defineModule({ ..., collapseRules: { name: fn } })`). It decides *whether* to
  collapse. *How* stays the same: one held item, then the other filled fields.
- `collapse=False`: turns off the setting a parent gives.

Only a `ReifiedRelation` or a `Conjunction` may set it (`export_definitions` raises otherwise). `pangloss interface
check` reports a named rule that no module provides.

We did **not** take the earlier approach of converting a Python `should_collapse` to JS with a transpiler. The
reasons: the truthiness of `[]`/`{}` differs between the languages, closures and imports do not carry over, it
depends on a forked transpiler, and the interface already has a place for app code that runs in the browser
(interface modules).

## The built-in rule (`schema/collapse.ts`, `collapsedView`)

A value collapses when all of these hold:

1. Its model has `collapse` set (and it is not shown as a chip of what refers to the item, `asChip`).
2. Its *held field* has exactly one item. For a reified relation that is `target`; for a conjunction it is its one
   relation field (a conjunction with several relation fields never collapses).
3. Every other filled field is a plain value (`literal`): text, a number, yes/no.
4. The held item ends as a chip: it is an Entity, or it collapses by these same rules (so `Identification`
   collapses only when its `Alternative` does too).

With `Collapse(...)`, also:

5. No field in `blocking` is filled.
6. Each field in `when` holds one of its values (`when={"role": ["author", "scribe"]}`; a single value is a list
   of one; an enum member counts by its value; `None` lets an empty field through). For a list field, every item
   must be one of them.
7. Fields in `hidden` are not shown beside the chip, and they do not count for 3 (a hidden date does not stop the
   fold). They are still there when it is opened with the marker.

`Collapse` is inherited whole (a subclass replaces it, the lists are not merged). `export_definitions` raises if it
names a field the model does not have, or the field that holds what it folds into. It is exported by the keys of the
fields: `{"blocking": [...], "hidden": [...], "when": {...}}`. Field defaults play no part.

A named rule replaces 3 to 7 with the predicate. 1 and 2 still apply, and other filled fields of any kind are
shown labelled after the held item.

## Pieces

| Where | What |
|---|---|
| `pangloss_interface/meta.py` | `Collapse`; `InterfaceMeta.collapse: bool \| Collapse \| ComponentRef \| None`; exported `collapse: true \| {blocking,hidden,when} \| {module,name} \| null`; kind and field-name checks in `export_definitions` |
| `pangloss_interface/modules.py`, `read-manifests.mjs` | manifest `collapseRules` keys; `problems()` checks `collapse` references |
| `types/models.ts`, `types/modules.ts` | `InterfaceMeta.collapse`, `CollapseRule`, `ModuleManifest.collapseRules` |
| `context/modules.tsx` | `collapseRule(reference)` lookup (`useModules()`) |
| `schema/collapse.ts` | `collapsedView(value, definitions, findRule)`: `{ held, extras }` or undefined, pure |
| `components/ItemContents.tsx` | the collapsed form, the expand marker, and the fold button on the head when expanded |
| demo `models.py`, `pangloss-library` | `Identification` (demo) and `WeightedAlternative` (library) get `collapse=True` |
| `ui.jsonc`, `interface-strings.md` | `collapse_show_whole`, `collapse_fold` |

## Tests

- Python (`test_interface_meta.py`): export of `True`, of a reference, and of `False` overriding a parent; bad
  reference refused; the kind check. (`test_interface_modules.py`): a missing named rule is a problem.
- `schema/collapse.test.ts`: each condition of the rule; the named rule (true, false, missing).
- `ItemContents.test.tsx`: Identification→Alternative→Person shows only the chip, then with `identified by`
  text; two alternatives show the full blocks; expanding with the marker and folding with the head button.
