# Features of the interface, as built

Records of single features of the interface: what each does, where its code is, how it is tested and what it does
not do. Each was written as the plan of its feature and is kept as built. The architecture is in
[interface.md](interface.md); features with a page of their own are listed in [the index](README.md#the-interface).

| Feature | |
|---|---|
| [Collapsed reified relations and conjunctions](#interface-collapsed-reified-relations-and-conjunctions-view-only) | `InterfaceMeta(collapse=...)`: a one-item wrapper shown folded into its line (view only) |
| [Form validation](#form-validation-in-the-interface) | Checks in the browser when Save is pressed; what is wrong is shown at its field |
| [Unsaved changes and the stash](#unsaved-changes-and-stashed-items) | A form asks before it is left with changes; a new document can be stashed and taken up again |
| [Hooks for modules](#interface-hooks-the-timeline-in-pangloss-dates-the-derived-section-in-pangloss-derived) | `itemSections`, `incomingViews` and the rest: how a package adds to the item page without core knowing it |

## Interface: collapsed reified relations and conjunctions (view only)

Written 2026-11-03. **View only**: nothing changes in the API, the stored data or the edit form.

### What it is for

`Identification[Alternative[ViaEdge[Person, Probability]]]` takes two nested blocks to say "this is
probably Smith" in the common case. When a model allows it, the item page shows such a value as the person's chip
(with its edge properties, as now), followed by any filled-in own fields as labelled text (`IDENTIFIED BY Smith`).
A small tinted marker in the colour of the relation's type comes before the chip. Clicking it shows the whole
structure in place, and a fold button on the head bar collapses it again.

### Where the rule lives

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

### The built-in rule (`schema/collapse.ts`, `collapsedView`)

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

### Pieces

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

### Tests

- Python (`test_interface_meta.py`): export of `True`, of a reference, and of `False` overriding a parent; bad
  reference refused; the kind check. (`test_interface_modules.py`): a missing named rule is a problem.
- `schema/collapse.test.ts`: each condition of the rule; the named rule (true, false, missing).
- `ItemContents.test.tsx`: Identification→Alternative→Person shows only the chip, then with `identified by`
  text; two alternatives show the full blocks; expanding with the marker and folding with the head button.

## Form validation in the interface

Written 2026-11-02. An edit form (`ItemForm`, and the dialog that makes an entity from inside a form) is checked in
the browser when Save is pressed, before anything is sent. What is wrong is shown where it is: the name of the field
turns red, with what is wrong under it. A red toast says that the item was not saved. The API's own answer (a 422)
is shown the same way, so the box of problems at the top of the form is gone.

### Plan

1. **Schemas from the exported definitions** (`interface-core/src/schema/validation.ts`). The interface has no
   Pydantic: it has what `pangloss_models.export` writes (`ModelDefinitions`). From it, a
   [valibot](https://valibot.dev) schema is made for a model, as the form holds it:

   | Definition | Schema |
   |---|---|
   | `str` | `string`, with `MinLen`, `MaxLen`, `pattern` |
   | `int` / `float` | `number` (`integer` for an int), with `Ge`, `Gt`, `Le`, `Lt`, `MultipleOf` |
   | `decimal` | a number, or a text that is one (the form keeps a decimal as text) |
   | `date` / `datetime` / `uuid` | ISO date / date and time / UUID text |
   | `enum` / `literal` | `picklist` of the values (and their text: the pills write text) |
   | `typedDict` | an object of its keys, each required |
   | `list` | `array` of the item (with `itemValidators`), the length checks on the list |
   | annotated value | its model's fields, with `value` of the field's `valueType` |
   | embedded | by its `type`, one of the field's `types`, then that model's fields |
   | relation | each item by its `type`, one of the field's options (type variables bound as in the form): an entity is a reference with an `id` (and its edge model's properties); a document, reified relation, conjunction or semantic space its model's fields |
   | label | required on a Document or Entity with `requireLabel` |
   | anything unknown (`unknown`, a type variable of a literal) | accepted |

   Schemas are made lazily (`v.lazy`) and kept per model and binding of type variables, so a model that contains
   itself (a statement in a statement) is no problem. Objects are loose: the form holds keys the API only reads.

2. **What counts as empty** is what `cleanForSave` leaves out: nothing, null, `""`, `{}`, and an entity not yet
   chosen (`{ type }` without an `id`). An empty field is fine if it is not `required` (or is `nullable`); a required
   one says "required". Empty items of a list are left out when saved, so they are not checked and not counted.
   The form, not the cleaned body, is checked, so that the path of a problem is the path of the form.

3. **Problems** (`FieldProblem`: a path of the form, a code, and its numbers) are made from valibot's issues
   (`problemsOf` reads `type`, `requirement`, `expected`, `received`). The codes are few (`required`, `too_short`,
   `too_long`, `too_few`, `too_many`, `too_small` (`Ge`), `must_exceed` (`Gt`), `too_large` (`Le`), `must_be_under` (`Lt`), `not_whole`, `not_multiple`, `not_number`,
   `not_date`, `not_datetime`, `not_uuid`, `not_choice`, `wrong_type`, `type_not_allowed`, `invalid`, `server`),
   each a UI string (`invalid_<code>`), so they can be translated. A 422 of the API is read the same way
   (`serverProblems`): `body` and the names of models in its `loc` are left out.

3a. **Language** (valibot's [i18n](https://valibot.dev/guides/internationalization/)). The texts are the
   `invalid_<code>` slots of `ui.jsonc` (English and German; a project adds languages in its own `ui.jsonc`).
   Before each check, `useSaveChecks` gives valibot the messages of the page's language
   (`setValidationMessages(lang, say)`: one `setGlobalMessage(fn, lang)`, whose function says an issue by its
   code), and checks with `{ lang }`, so each problem's `message` is valibot's, in that language. If the
   language is changed while problems are shown, they are checked again and said in the new one. The codes do
   not depend on the messages: "required" is the only `custom` check, a type not allowed is `never`, and the
   patterns of a decimal and of a date and time are told apart by which `RegExp` they are. `@valibot/i18n` is
   not used: its texts are valibot's own ("Invalid length: Expected >=5 but received 2"), not the interface's,
   and they would be a second place to translate.

4. **Where they are shown.** Each row of a form (a field's name and editor; the title box) registers its path with
   the form's state. A problem belongs to the row with the longest path that it is under: a problem inside a part
   that has no rows of its own (a date in its own editor, a typed dict, an item of a list of texts) is shown at the
   field it is in, with the names of the keys between. The name of the row turns red, and the problems are listed
   under it. Changing a field takes its problems away. A problem that has no row is said in the toast.

5. **Save**: when the form has problems nothing is sent; a red toast says how many, and the first field with a
   problem is scrolled into view. The answer of the API is shown in the same way (a 422 by field; anything else in
   the toast). The amber notice of a 412 (someone saved meanwhile) stays where it is, since it has a button.

### Tests

- `schema/validation.test.ts`: each row of the table above, the empty rules, lists (blank items, lengths), nested
  paths through relations, semantic spaces, type variables, embedded types, edge properties, recursion, and that the
  issue paths are the form's paths; `serverProblems` with the `loc` of a discriminated union.
- `context/form.test.tsx`: problems belong to the nearest row, clear on change.
- `components/form/ItemForm.test.tsx`: Save with a missing required field sends nothing, shows a red toast, marks the
  field red and says why; fixing it and saving sends; a 422 is shown at the field; no box of problems.

### Limits

- Only what the export says is checked. A Pydantic validator written in Python (a `field_validator`, a
  `model_validator`) is not exported, so it is still only the API that says so (and that is shown at the field, too).
- `required` is `Create`'s: a field with a default, or declared `X | None`, is not required. If the `Edit` model of a type differs, the API's answer is the truth.

## Unsaved changes and stashed items

Status: ✅ built (2026-11-05).

Leaving a form with changes in it by accident loses them. The interface now (a) warns before a form with changes is
left, (b) offers to *stash* a new head document instead, keeping it in the browser to finish later, (c) shows what is
stashed beside the clipboard where another one of the same type could be made, (d) asks for a label before stashing
something that has none, (e) has a Stash button beside Save, and (f) turns Save off until there is a change to save.
When a stashed item is taken up again, the entities it refers to are checked against the database in one request
(`POST /api/references`): those that are gone are taken out (and listed), and labels are brought up to date.

### What counts as a change

`createItemFormState` keeps two plain copies beside the store being edited: the *baseline* (what the item is when
nothing is to be saved: the item as loaded, or a blank new one) and the *start* (what the form opened with: the same,
or the stashed item it was opened from). Two memos compare the store with them, each made comparable by
`cleanForSave` (what would be sent: so a field typed in and emptied again is no change, and an entity's label does
not count):

| | compared with | used for |
|---|---|---|
| `changed()` | the baseline | Save is on only when it is true (and nothing is being sent) |
| `edited()` | the start | leaving asks first; Stash is on |

A stashed item opened again has its baseline blank and its start the stash: it can be saved at once, but leaving it
untouched asks nothing (it is still stashed).

### Leaving

`ItemForm` takes `guardLeaving`, which it calls with a function the page calls before it is left:
`(leave) => boolean`, true if it may go now. The application's New and Edit pages give it to the router's
`useBeforeLeave` (core knows no router): when the form says no, the navigation is held, and the form's dialog decides
(`LeaveDialog`): *Stay*, *Leave without saving*, and, for a new head document that is not an entity, *Stash and
leave*, with a label field if the item has none. Cancel is a way of leaving too, so it asks the same. A save, a delete or a stash that worked lets the page go
without asking. Leaving the page altogether (reload, closing the tab, an address typed) gets the browser's own warning
(`beforeunload`), which can offer nothing more.

### The stash

`StashProvider` (core, `context/stash.tsx`) keeps the stashed items in local storage, per user
(`pangloss.stash.<username>`), shared by tabs, as the clipboard is. An entry is `{ key, type, label, value, when }`;
`value` is the form's whole item. Stashing an item that was opened from the stash replaces that entry; saving it
removes it.

The Stash button (beside Save, on the form of a new head document that is not an entity) stashes at once if the
item has a label, and otherwise asks for one (`StashDialog`); then the page goes to the list of the type
(`onStashed`).

Opening a stashed item is a link to `/<Type>/new?stash=<key>`. The New page reads the entry once settled (local
storage is the browser's: the server renders "Loading"), asks `/api/references` about every entity it refers to, and
opens the form on the result (`restoreStashed`). What is gone is shown above the form as chips.

### The bar at the bottom

`ClipboardBar` holds two sections side by side, of one height: the clipboard (where a form is on the page and there
is something on it, as before) and the stash (where the page has said what type it is about with
`stash.showFor(type)` — the list page and the New page — and there are stashed items of that type or its subtypes).
The arrow at the left folds the whole bar to its head line. Clicking a section's name shows all of it (it takes most
of the width, and grows taller); the other stays beside it.

### The API

`POST /api/references` `{"ids": [...]}` → `{"found": [{id, type, label}]}`: the entities with those ids that are not
deleted, in the order asked, with their labels as they are now. Up to 1000 ids; open to everyone, as autocomplete is.
It is `Entity.references(ids)` (`Person.references(ids)` keeps only people), bound by `initialise()` to the backend's
`references` (`pangloss_cypher.read_functions`), and to one request in the SDK. Tested in the conformance suite
(`test_references_live.py`).

### Not done

- An entity's form (page or dialog) cannot be stashed.
- An edit of an existing item is not stashed: leaving it only warns.
- The stash is in the browser: another browser does not see it.
- A card in the bar shows the item as it was stashed; only the form opened from it has the labels brought up to date
  (the entry itself is not rewritten until it is stashed again).

## Interface hooks: the timeline in pangloss-dates, the derived section in pangloss-derived

2026-11-05. Moves two pieces of the item page out of `interface-core` into the packages they belong to. Core gets
generic hooks that any interface module can use.

**Status: done (2026-11-05).** Everything below is built, with the tests listed under Tests.
- Core vitest: 290 passed.
- Module vitest (pangloss_dates 43, pangloss_derived 4, pangloss_history 29) all pass.
- pangloss-interface pytest: 160 passed.
- e2e: 140 passed.
- `pangloss interface check` on the demo is clean, and finds `pangloss_derived`.

Deviations from the plan:
- `IncomingEntry` is in `types/modules.ts`, not `schema/incoming.ts`, because a type the manifest uses belongs with it.
- The core tests use a made-up module (`offices`), not the dates one.

### What is in core now (review)

All of the timeline and all of the derived section are in `pangloss-interface`:

| Piece | Where (interface-core/src) | Lines | Belongs to |
| --- | --- | --- | --- |
| `Timeline` (the vertical slider with bars) | `components/Timeline.tsx` | 141 | dates |
| `IncomingTimeline`, `DatedRow` | `components/ItemContents.tsx` | ~130 | dates |
| The choice between by field and by date: `canDate`, `byDate`, `arranged`, `undatedByField` | `components/ItemContents.tsx` (`Fields`) | ~40 | core (generic) + dates (what counts as dated) |
| `isDateable`, `arrangeByDate`, `yearOfDay`, `yearSpan`, `yearOf`, `byYear`, `dateInWords` | `schema/dating.ts` | 137 | dates (`IncomingEntry` is generic) |
| `IncomingOrder` (`"field" \| "date"`), the console state, localStorage | `context/console.tsx` | ~60 | core, but generic rather than date-specific |
| The "Sort by date" toggle | `components/Console.tsx` (`IncomingOrderToggle`) | 25 | dates |
| `DerivedSection` (facts, "why", more pages) | `components/DerivedSection.tsx` | 290 | derived |
| Rendering it after the item | `interface-app/src/pages/Item.tsx` | 4 | core (generic) |
| Tests for all of the above | `dating.test.ts`, `ItemContents.test.tsx` (2 tests), `Console.test.tsx` (toggle), `DerivedSection.test.tsx` | — | follow their code |

`SectionBar` (the section heading bar) is a primitive that both use, and the item page's own layout can use it too. It
stays in core.

Core also knows the name of a Python trait (`"Dateable"`), the reference fields that pangloss-dates writes
(`dateSortDay`, `dateEndSortDay`, `dateText`), and the `_derived` key of pangloss-derived's view. After the move it
knows none of these.

### The hooks ("extension points")

There are already three in a module's manifest (`defineModule`): `components` for model slots and routes,
`collapseRules`, and `consoleActions`. Two new ones follow the same pattern. A third mechanism lets a project switch
off what a module adds.

#### 1. `itemSections`: sections after the item's own contents

```ts
itemSections?: Record<string, ComponentLoader>;   // given ItemSectionProps

interface ItemSectionProps {
  type: string;          // the item's own type
  id: string;
  item: Record<string, unknown>;   // as the API sent it
  model: ModelDefinition;
}
```

- Core gets a new component, `ItemSections` (exported). The generic item page renders it after `ItemContents`.
- Each section is drawn lazily, in the order of the modules, in its own `Errored` and `Loading` (as `consoleActions`
  are). Each section decides for itself whether to show anything.
- A module's own `itemPage` can render `<ItemSections …/>` where it wants them. A page that does not render it gets
  none.
- **pangloss-derived** gets an interface module (`pangloss_derived/interface/`) with
  `itemSections: { Derived: … }`. The module's `DerivedSection` reads `item._derived`.
  - As built (2026-11-07): the item page reads the item with `?extras=false`, so `_derived` is not on it; the section
    then reads `/api/derived/about/{Type}/{id}` itself. `ItemSections` renders each section in a `Loading` with no
    fallback, and the item page puts the contents and the sections in a `Reveal`: a section shows once what it
    reads has come, and not before what refers to the item is on show. An item that carries `_derived` (a module's
    page that read it whole) is shown from that.

#### 2. `incomingViews`: another way to show what refers to the item

By default, core shows what refers to an item grouped by the field it is in. A module can offer a view that takes some
of those items and shows them its own way, in a section after the item's fields:

```ts
incomingViews?: Record<string, IncomingView>;

interface IncomingView {
  /** Which of what refers to the item it shows (sync and small, as collapseRules are). The rest stays by field. */
  takes: (item: Record<string, unknown>, definitions: ModelDefinitions) => boolean;
  /** Shows what it takes, in a section after the item's fields (lazy). */
  component: ComponentLoader;          // given IncomingViewProps
}

interface IncomingViewProps {
  type: string; id: string; model: ModelDefinition;
  entries: IncomingEntry[];            // what it takes, in the order of the model's incoming fields
}
```

- **The state** (core, in the console's context) replaces `IncomingOrder`. `useIncomingView()` returns
  `{ chosen(), choose(name | undefined), offered(name), offer(name) }`.
- A view is named `app:name` (for example `pangloss_dates:ByDate`). The choice is remembered in localStorage
  (`pangloss.incomingView`). No choice means by field, the built-in view.
- **On the item's own page**, `Fields` offers each view that takes at least one of the entries, for as long as it does.
- If the chosen view is offered, `Fields`:
  - shows what the view does *not* take by field, in the `dl` as now;
  - renders the view's component with what it takes, after the `dl`.
- **The toggle is a `consoleAction` of the module that has the view** (no new hook). It reads `useIncomingView()`.
  It shows itself only when its view is `offered`.
- **pangloss-dates** gets:
  - `incomingViews: { ByDate: { takes: isDateable, component: ByDate } }`;
  - `consoleActions: { SortByDate }`;
  - `Timeline`, `ByDate` (was `IncomingTimeline` + `DatedRow`) and `dating.ts` (was `schema/dating.ts`, without
    `IncomingEntry`).
- Core exports what such a view needs to look like the rest of the page: `ItemValue` (gains `asChip`), `SectionBar`,
  `fieldRuleClass`, and `IncomingEntry` (moved to `schema/incoming.ts`).

#### 3. `InterfaceConfig(disabled=…)`: not using what a module adds

A project may want pangloss-dates' models without its timeline, or its own derived section instead of
pangloss-derived's. An app's `interface_config.py` can name contributions to leave out:

```python
config = InterfaceConfig(disabled=["pangloss_dates:ByDate", "pangloss_derived:Derived"])
```

- A name is `app:key`, where `key` is a key of `consoleActions`, `itemSections` or `incomingViews` in that app's
  manifest.
- The merged list is exported as `disabled` in the definitions. `ModulesProvider` leaves those out.
- A disabled view is never offered, so its toggle never shows.
- `pangloss interface check` reports a name that is not in any module's manifest.
- To *replace* a built-in contribution, a project disables it and adds its own in its own module, under any name.

`disabled` is only for what a module adds to every item page. Model slots (`itemPage`, `viewCard`, …) are already
chosen per model with `InterfaceMeta`.

### Python

- `Manifest` gets `item_sections` and `incoming_views`. `read-manifests.mjs` outputs `itemSections` and
  `incomingViews` (their keys).
- `InterfaceConfig.disabled`. `meta.py` exports `exported["disabled"]` (merged from all apps, in order).
- `problems()` reports an unknown disabled name.
- Tests go in `test_interface_modules.py` and `test_interface_config.py` (or wherever `merge` is tested).

### Translations

The UI keys (`incoming_*`, `derived_*`, `date_*`) stay in core's `ui.jsonc` for now, where the history, review and
dates modules' keys already are. Moving every module's keys to its own app's `translations/ui.jsonc` is a separate
change.

### Tests

- **Core**:
  - `ItemContents.test.tsx` tests the hook with a made-up module: a view that takes some entries. It is offered; when
    chosen, what it takes goes to its component and the rest stays by field.
  - `ItemSections` is tested with a made-up section, and with `disabled`.
  - The date tests leave core.
- **pangloss-dates module**:
  - `dating.test.ts` (moved);
  - `ByDate.test.tsx` (the two timeline tests, moved);
  - `SortByDate.test.tsx` (the toggle tests, moved from `Console.test.tsx`).
- **pangloss-derived module**: `DerivedSection.test.tsx` (moved).
- **Python**: the manifest keys, `disabled`, and the check.
- **e2e**: unchanged; the selectors are the same. Everything must still pass: the date toggle, the timeline, the drag,
  and the derived tests if any.

### Order of work

1. Core hooks: types, `ModulesProvider` (with `disabled`), `useIncomingView`, `ItemSections`, and the generic
   `Fields`. Core tests.
2. Move the timeline to pangloss-dates and its tests.
3. Make pangloss-derived's interface module and move `DerivedSection`.
4. Python: manifest keys, `disabled`, check, and tests.
5. Docs (`interface-modules-implementation.md`, `dates-implementation.md#dateable-documents-and-one-sided-date-ranges-plan-of-2026-11-05-built`, `COVERAGE.md`), then e2e.
