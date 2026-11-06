# History in the interface: plan

**Status: built and tested 2026-11-04** (what differs from the plan is in "As built" at the end). The history package ([history.md](history.md)) can list, show, compare and restore
versions through its API; this is its interface: a button in the console of an item, a panel that slides out from the
right with the versions, the old version itself sliding out beside it, "Restore to this point" with a confirmation, and
a page that shows every version side by side with the differences marked.

## Decisions (the user's, 2026-11-04)

| Question | Decided |
|---|---|
| Data from before `pangloss_history` was installed | **`pangloss history baseline`**: records the current content of every head node that has no record at its current version (op `baseline`, who and when from its `meta`). Safe to run again. The panel says where history begins, and names the command when there is nothing |
| What the confirmation of a restore lists | **The later versions whose work is undone, then the changes field by field** (now → restored), and that nothing is erased: the history keeps them, so they can be restored again |
| Which pages | **The item page only** (a restore under a form with unsaved changes would be lost or overwrite them) |
| The side-by-side view | **A page, `/:type/:id/history`**, opened from the panel ("Compare all"). Oldest on the left, the current on the right (scrolled to it). Rows aligned by field and by the id of nested parts, with a placeholder where a version has nothing; each column marked against **the one before it**: green added, red removed, amber changed, words for text |

## Where it lives

As review: **an interface module of `pangloss_history`** (`pangloss_history/interface/`), with a console action and a
route. A project without the package sees nothing.

### Core: one side panel at a time

Review and history both slide out a panel from the right, below the console. Two open at once would lie on each other.
Core gets a small context, `SidePanelProvider` / `useSidePanel(name)`: one name is open at a time (or none), so opening
one closes any other. `ReviewAction` moves to it; history uses it. (A context, not a module-level signal, so that the
server does not share it between requests.)

## The API (additions to `pangloss-history`)

The stored content is the **write form** (snake_case keys, an entity referred to as `{id, type, label: null}`); the
interface's view reads the API's **read form** (camelCase, with labels). So:

- `GET .../history?summary=true`: each version also has `label` (its label then) and `changes`: the fields of the head
  node that differ from the version recorded before it, `{key, kind, count}` (camelCase key; `added` / `removed` /
  `changed`; how many changes under it). What the panel's condensed rows show.
- `GET .../history/{v}?view=true`: the content (upgraded, as now) in the read form: camelCase keys, the bookkeeping of
  the write form left out (`create_new`, `context_labels`, `db_labels`, `semantic_spaces`), and each entity reference
  given its label **as it is now** (restore refers to entities as they are now, too); one that is gone is marked
  `missing: true`.
- `GET .../history/contents`: every version with content, in the read form (labels looked up once for all), for the
  page that compares them.

The differences shown in the interface are computed in the browser, from two read forms, by the same alignment the
compare page uses, so the confirmation and the page agree.

### `pangloss history baseline`

For each model with history (Documents and Entities that are not in `HISTORY_EXCLUDE`), each head node whose latest
record is missing or older than its version in the graph gets a record of what it is now: its edit view, validated as
its `Update`, made the write form (`_to_db_model()`), serialised as the listener does. `op = "baseline"`, `version` its
version, `who` / `at` the last change in its `meta` (or the creation). Paged through `Model.list`. `--dry-run` counts.
A restore of a baseline is an ordinary restore. A document inside another (a statement of a factoid) gets none: it is
written with the one it is in, whose record has it. (Until 2026-11-06 a baseline counted, and would have recorded, each
of those: the smoke test's dry run said 19,191 statements "would be recorded".)

## The module

```
pangloss_history/interface/
  package.json  tsconfig.json  vitest.config.ts  README.md
  src/index.ts                       manifest: consoleActions.History, components.HistoryPage, route /:type/:id/history
  src/api.ts                         types and calls (list with summary, one version as view, contents, restore)
  src/align.ts                       the alignment of several versions into rows; the change of each cell from the one before
  src/words.ts                       a word diff of two texts (LCS on words)
  src/changes.ts                     what a restore would change, as rows with a trail (from align)
  src/components/HistoryAction.tsx   the console button and the panel (versions, condensed)
  src/components/VersionDrawer.tsx   the old version, sliding out to the left of the panel; Restore to this point
  src/components/RestoreDialog.tsx   "Are you sure": the versions undone, the changes
  src/components/HistoryPage.tsx     the side-by-side page
  src/components/AlignedValue.tsx    a cell of the page (a value, marked)
```

### The button and the panel

A `ConsoleButton` with a clock-with-arrow icon, only for someone logged in (the API needs it) and when the item has
history (the list answers). The panel is the review panel's frame: fixed on the right below the console bar, `w-96`,
slate glass, a header with the icon, "History", **Compare all** and close; Escape closes it.

Versions newest first, each a condensed card:

- a version pill (`v7`), an icon of what happened (created, edited, restored from vN, deleted, undeleted, baseline),
  who, and when;
- the label, if it is not the one before;
- the fields that changed as small tags in the colours of the compare page (`Text`, `+2 Statements`, `−1 Places`);
- the current version is marked **Current**; a gap is a dashed row ("versions 4–5 were not recorded").

Clicking a card selects it, and the **version slides out** to the left of the panel (from under it): a drawer of the
same height, `w-[36rem]`, with its header (version, who, when; "upgraded to the models of now", and the problems if
any), the item as the item page shows it (`ItemContents` with the read form), and at the bottom, **Restore to this
point** (not for the current version, nor a delete). Clicking the selected card again, Escape, or closing the panel
closes it.

### Restore

The button opens a `Modal`: "Restore version 7?", then

1. **Undone**: the versions after it (vN, op, who, when), newest first;
2. **What changes**: the rows of the alignment of the current and the restored version that differ, each with its
   trail (`Statements › Activity "A coronation" › Places`) and old → new;
3. "Nothing is erased: the history keeps every version, and this restore can be undone the same way."

If the graph is at a version that was not recorded, it says that the changes since vM cannot be listed. **Restore**
posts with `If-Match` the current version; on success the item is read again (`revalidate`), the list is read again,
the drawer closes and a toast says "Restored version 7 as version 13". A 412 (changed meanwhile) or a 409 (the API's
problems) is a red toast, and the list is read again.

### The compare page

`/:type/:id/history`: the console (type, label, a link back to the item); then a box, scrolling sideways, of one column
per version, oldest on the left, each `w-[26rem]`, with a sticky header (version, op, who, when). If the graph is ahead
of the history (a gap at the end), a last column "Current (not recorded)" from the item's own read.

**Alignment** (`align.ts`): the versions are merged into one tree of rows. For an object, its model's fields in the
model's order; a list of objects with ids is the union of the ids, in the order they first appear; a list of entity
references, and a list of plain values, is one row (the cell shows its items, those added or removed marked); a nested
object (a document, a reified relation, a semantic space, an embedded object, an annotated value) is a head row and
its own rows, indented. Each row is a row of one CSS grid, so the cells of a row are the same height in every column.
Each cell is `absent`, `same`, `added`, `removed` (absent here, present before: a red placeholder), or `changed`,
against the column to its left; text that changed shows its words added and removed.

## Tests

- **Python** (`pangloss-history/tests`): the read form (keys, bookkeeping, labels, missing), the summary, the
  contents route; the baseline (unit: which nodes, the record) and, in the conformance suite against each backend,
  that a baseline is recorded for a node written before history was installed, is not repeated, and can be restored.
- **Core (vitest)**: `useSidePanel`: opening one closes the other; review uses it.
- **Module (vitest, in a built project)**: `align` (ids, order, placeholders, kinds, lists), `words`, `changes`; the
  panel (cards, current, gaps, condensed tags), the drawer (slides, restore button), the dialog (lists).
- **e2e (Playwright)**: the e2e project gets `pangloss_history`: the button; the list after edits; a version slides out;
  the restore confirmation lists the undone versions and changes, and the restore changes the page; the compare page
  (columns, scrolled to the right, marks); opening review closes history and the other way round; an item from before
  history was installed, then `pangloss history baseline`.

## As built (2026-11-04)

As planned, with these differences and additions:

- **The label is a row.** The exported models do not have `label` among their fields, so `align` puts it first for the
  item itself (a part's label is in its head); the summary lists a changed label first. Field names come from
  `useFieldName` (`names.ts`), which calls the label what the form does (`t("label", "Label")`).
- **No group rows.** A field with parts has no row of its own: the first part's head carries the field's name, in the
  column of names. An **entity referred to is a part too**, a row of its own matched by id (its chip), not a list in
  one cell: Marie taken out and Mary put in are two rows, red and green, as a split diff shows them. A list of plain
  values is still one cell.
- **What was taken out comes before what was put in its place** in the merged order of parts (`mergeOrder`).
- **The compare page** has a sticky column of names on the left (with a hairline and a shadow over the versions that
  scroll under it) and sticky headers; the box scrolls both ways, at most the height of the window. A removed cell shows
  the value it had, faded and struck through, on red hatching; an absent one is grey hatching.
- **After a restore** the panel asks for the versions again until the new one is there (it is recorded a moment after
  the write: up to ten times, 200 ms apart).
- **Escape** puts back the version that is out, then closes the panel; the dialog's Escape is its own.
- **Delete and undelete** are cards without a button (they have no content to show).
- The drawer is `z-10` under the panel's `z-20`, and slides from `translate-x-[calc(100%+24rem)]`, so it comes out from
  under the panel.
- Core: `useSidePanel(name)` (`interface-core/src/context/sidePanel.tsx`) keeps the open panel as an object of each
  caller, not a name, so the panel of the next page is closed without writing state when the last one goes. The context
  is optional (a test that renders one panel has none). `ReviewAction` uses it.

Tests: `pangloss-history/tests/test_history_view.py` (read form, labels, summary), new cases in `test_history_api.py`
and `test_history_cli.py`; `pangloss_testing/conformance/test_history_baseline.py` (on Memgraph and Neo4j: data written
before history, a baseline once, restored, a head node ahead of its history, the read form's labels); core
`sidePanel.test.tsx`; the module's `align.test.ts`, `words.test.ts`, `timeline.test.ts`, `HistoryAction.test.tsx`,
`HistoryPage.test.tsx`; `e2e/test_history.py` and `test_dev_mode.py::test_the_history_panel_and_page`
([COVERAGE.md](../e2e/COVERAGE.md)).

Not built: a version with blocking problems is shown with them and has no Restore, but there is no form to reconcile a
draft; the compare page shows every version at once (no paging, for an item with very many).
