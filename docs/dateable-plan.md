# Dateable documents, and one-sided date ranges

Plan written 2026-11-05 on branch `refactor-dates`. The decisions were made with the owner (answers below).
**Built the same day** (uncommitted); what differs from the plan, and what was found, is at the end.

## What was there

- `DateRange` had `earliest` and `latest`, **both required** `ExactDate`s: a range with one end could not be said.
- There was **no `Dateable`**. An earlier "no Trait classes" decision (calendar interface, second round) was about how the
  calendar draws a date (point or period: the date kinds already say that), not about a document mixin. So nothing is undone.
- Core: a trait already carries fields, `DBField`s and `@model_validator`s to the classes that use it (checked).
  A `ReferenceView` is read from every property of the node (`n{.*}`), so a property on the document node costs nothing
  to read. But a trait could not add `reference_view_extra_fields`, and the date is its own embedded node: `date.sort_day`
  is not a property of the document.
- Core refuses an optional embedded field (`ExactDate | None`).

## Decisions (owner, 2026-11-05)

1. **One-sided range**: `not_before` / `not_after` (`notBefore` / `notAfter` in the API, the TEI names) are each
   `ExactDate | UnknownDate`, and at least one is known. No core change. In the editor, "not known" is a **button** next to the
   end. It makes the end an `UnknownDate`, and pressing it again brings the date fields back: nobody has to choose a type.
2. **Sort day on the ReferenceView: a stored copy.** The trait's validator copies the date's sort days onto the document
   node when it is written (DBFields). Lists and incoming items read them as they are, and they can be indexed.
3. **The date text is worked out and stored too** (`date_text`). It uses no words, so it needs no translation: `1500`, `1500-03`,
   `1500-03-02`, `1500–1502`, `≥ 1500`, `≤ 1502`, `?`, `1500–…`, an EDTF date as written (`1500~`), `↻ 1500–1520` for a
   recurrence.
4. **Interface too**: an entity page can show what refers to it by date.
5. **Sorting: on the client for the entity page, on the server for lists.** The entity's head view already holds every
   incoming item, so the page sorts and filters them as it has them, with no reload. For paged lists (where the client does
   not have everything) the stored `date_sort_day` is indexed, so `Model.list` / `Model.Order` can order by it on the server.

## Changes

### pangloss-dates

- `DateRange.earliest/latest` become `not_before/not_after: ExactDate | UnknownDate` (the Julian and Gregorian families
  too). Refused if both are unknown. Bounds: from the known end to the floor or the horizon. A one-sided range sorts by its
  known end unless `sort_by` says otherwise (the midpoint of 1500 to `DATES_OPEN_END_YEAR` means nothing).
- New `pangloss_dates.dateable`:
  - `Dateable(Trait)`: `date: Date`, plus the DBFields `date_sort_day`, `date_end_sort_day` and `date_text`. They are
    filled by a validator from the date that is written, and added to the `ReferenceView` of every class that uses it.
  - `SingleDateable(Dateable)`: `date: ExactDate | DateRange | EDTFDate | UnknownDate` (something that happened once).
  - `PeriodDateable(Dateable)`: `date: Period | UnknownDate` (something that lasted).
  - A class may narrow `date` again (`date: JulianDate`, `Annotated[Date, SortDefault(...)]`). Because the traits are
    heritable, the labels are `:Dateable` (and `:SingleDateable` / `:PeriodDateable`), so a relation or a search can target
    "anything dateable".
  - `text_of(date)` gives the stored text (above), and `is_dateable(model)` says whether a model is dateable.
- Migration `0002`: rename the fields of `DateRange` and its families, and widen their types.
- Interface module: `DateEditor` writes `notBefore`/`notAfter` and has the "not known" button. `formatDate` reads the new
  names and says "not before 1500", "not after 1502".

### Core (pangloss-models, pangloss-cypher)

- `Trait.Meta(reference_view_extra_fields=[...])`: these fields are added to the `ReferenceView` of every class that uses the
  trait. A DBField may be one of them, because the reference view is read-only.
- Field markers (`SortDefault`) run **before** the class's own validators, so a validator that copies from a field sees
  the date as it will be stored. (Before this change they ran after, so the copy would have been out of date.)
- The export of a model has `traits` (the names of the traits it has; not schema data, so it does not touch migrations).
- An incoming item that reaches the entity through a wrapper (a reified relation) carries the holder's reference-view extra
  fields too, so a dateable statement shows its date there as well.

### Interface (pangloss-interface)

- On an entity's page, when any incoming item is dateable, a "By field | By date" switch is shown (the setting is kept in
  `?incoming=date`). "By date" shows one list ordered by `dateSortDay`. On the left is the date text and, under it, the
  field (as the key column now shows the field); on the right, the chip. Then come two sections: **Date unknown** (a dateable
  item whose date is `?`) and **Not dated** (items whose type is not dateable, grouped by field as now).
- A **year slider** on the right, sticky: two thumbs that narrow the dated list to a span of years. It runs on the client,
  over the items the page already has.
- e2e: `e2e/test_dateable.py`, and `e2e/COVERAGE.md`.

### Demo

- `Statement(Document, Dateable)` in place of `date: Date`. A migration adds the fields, and a `RunPython` fills them in for
  the statements that already exist.

## Not done

- A trait-level `view_extra_fields` (only reference views).
- Server-side ordering in the entity page's head view (not needed: it has every item).
- Translating the stored `date_text` (it uses no words). The interface shows `≥`, `≤` and `?` as they are.

## As built (2026-11-05)

- The "By field | By date" choice is kept in `localStorage` (`pangloss.incomingOrder`), not in `?incoming=date`: interface-core has no
  router. It is remembered from one page to the next.
- A trait names its reference-view fields with a class variable, `reference_view_fields`. `Trait.Meta(...)` was not used, because a trait's
  own `_meta` clashes with the meta of the document that has it.
- **Found and fixed on the way:**
  1. Field markers (`SortDefault`) ran after the class's validators, so a copy taken from such a field was out of date.
  2. Models downstream of a cycle were made before the models they embed: a fix to the order of initialisation (`_order_cyclic`).
  3. `AlterEmbedded` called it lossy to widen one model to a union that still has it, so `migrate` asked for `--backup`.
  4. The interface showed fields that are only in the database: a reference became a block listing the copies, and the form offered
     them as inputs.
- The demo's `Statement` is `Dateable` (migration `demo_app` `0013`, with `fill_in_dateables`). The demo database has **not** been migrated:
  run `pangloss migrate` in `pangloss-demo`. That applies `pangloss_dates` `0002` (it renames the ends of the ranges) and `demo_app` `0013`.


## Second round: the order in the console, a timeline (2026-11-05)

The owner did not like the "By field | By date" switch in the page. Changes asked:

- **The choice goes in the console**: one toggle, *Sort by date* (pressed: sorted by date; not: grouped by relation; the
  owner asked for a toggle rather than two buttons), shown on an item's page when something that refers to it is dateable. The state is shared by the console and the page
  through the console context (`useIncomingOrder`): the page's `ItemContents` *offers* the choice while it has dateable
  items (as a `Console` registers itself), and the console shows the buttons while it is offered. Still kept in
  `localStorage`.
- **Sorted by date**, the page is: (1) the item's own values, with no header; (2) what refers to it that is not dateable,
  under the header **Undated**, grouped by field; (3) the dateable items in date order, the date **in words** on the left
  (with the field under it) and the chip on the right. Those whose date is not known come last, as "Date unknown".
- **Date in words**: what is stored (`date_text`) has no words, but is made to be read back: `1500-03-02`, `≥ 1490`,
  `1500–1502`, `1500–…`, `↻ …`. `dateInWords(text, words)` in interface-core says it with the `date_*` texts that are
  already in the core translations ("2 March 1500", "not before 1490", "1500 to 1502"). Nothing new is stored.
- **One range slider**: the two "From" / "To" sliders become one slider with two thumbs (two native range inputs on one
  track, so the keyboard, screen readers and Playwright's `fill` work as they did; still named "From" and "To").
- **A vertical timeline** (adapted from manmax-frontend's `VerticalTimeline`), sticky beside the dated items: a track of
  the years in the span the range slider chose, a thumb with the year beside it, and for each year with items a bar as long
  as its count (scaled to the year with most). Dragging the thumb (or the keys) scrolls the list to the top of that year:
  the dated items have a small heading per year (as in manmax), the scroll target. Scrolling the page moves the thumb
  (an `IntersectionObserver` on the headings, as in manmax), but not while it is being dragged.
- Styling: the project's slate colours, hairlines and `scroll-mt-28`, not manmax's greens; no CSS files.
- Cleared up: `IncomingOrderSwitch`, `YearSlider` and the `incoming_order` / `incoming_by_*` texts go.

Tests: vitest for `dateInWords`, the year groups, the range slider and the timeline (keys move it, a change asks to scroll),
and the console buttons; `ItemContents` tests for the three parts in order; e2e (`test_dateable.py`, `test_dev_mode.py`).

## Third round: sections as bars, no filter of years (2026-11-05)

- An item's page sorted by date has three sections, well apart: the item's **facts** (its own values and what refers to it
  that cannot have a date, with no heading), the **Timeline** (what has a date) and **Derived** (pangloss-derived). The
  last two have a heading that is a bar across the page, as the console is (`SectionBar` in `primitives`).
- The slider of years is gone: the timeline is enough to move about the years. It spans all the dated items.

## Fourth round: out of core (2026-11-05)

The timeline left `pangloss-interface` for `pangloss_dates/interface` ([interface-hooks-plan.md](interface-hooks-plan.md)).
Core has a generic hook, `incomingViews`, and no longer knows of `Dateable`, `dateSortDay` or `dateText`. The dates
module has the view `ByDate` (was `IncomingTimeline`), `Timeline`, `dating.ts` (was `schema/dating.ts`; `arrangeByDate`
now only splits dated from not known, since the view is only given what is dateable), and the button `SortByDate` (a
`consoleAction`; it was `IncomingOrderToggle` in `Console`). `useIncomingOrder` became `useIncomingView`
(`chosen`/`choose`/`offered(name)`/`offer(name)`), and the choice is kept in `localStorage` as `pangloss.incomingView`
(`pangloss_dates:ByDate`). A project can leave it out with `InterfaceConfig(disabled=["pangloss_dates:ByDate"])`.
