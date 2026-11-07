# Interface hooks: the timeline in pangloss-dates, the derived section in pangloss-derived

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

## What is in core now (review)

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

## The hooks ("extension points")

There are already three in a module's manifest (`defineModule`): `components` for model slots and routes,
`collapseRules`, and `consoleActions`. Two new ones follow the same pattern. A third mechanism lets a project switch
off what a module adds.

### 1. `itemSections`: sections after the item's own contents

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

### 2. `incomingViews`: another way to show what refers to the item

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

### 3. `InterfaceConfig(disabled=…)`: not using what a module adds

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

## Python

- `Manifest` gets `item_sections` and `incoming_views`. `read-manifests.mjs` outputs `itemSections` and
  `incomingViews` (their keys).
- `InterfaceConfig.disabled`. `meta.py` exports `exported["disabled"]` (merged from all apps, in order).
- `problems()` reports an unknown disabled name.
- Tests go in `test_interface_modules.py` and `test_interface_config.py` (or wherever `merge` is tested).

## Translations

The UI keys (`incoming_*`, `derived_*`, `date_*`) stay in core's `ui.jsonc` for now, where the history, review and
dates modules' keys already are. Moving every module's keys to its own app's `translations/ui.jsonc` is a separate
change.

## Tests

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

## Order of work

1. Core hooks: types, `ModulesProvider` (with `disabled`), `useIncomingView`, `ItemSections`, and the generic
   `Fields`. Core tests.
2. Move the timeline to pangloss-dates and its tests.
3. Make pangloss-derived's interface module and move `DerivedSection`.
4. Python: manifest keys, `disabled`, check, and tests.
5. Docs (`interface-modules-implementation.md`, `dateable-plan.md`, `COVERAGE.md`), then e2e.
