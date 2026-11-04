# Typology pages: drag and drop, a live tree, inline labels, a new look

Plan of 2026-11-04 (module `pangloss_typology/interface`). The user's choices:

- **Hierarchy only.** Dragging changes where a type sits; siblings stay in the order of their labels. No server
  change.
- **A live tree.** A `live()` server function sends the tree whenever it changes, as the review feed does; a move or
  a new label is shown at once (optimistically), kept until the feed brings it back, and undone if the API refuses.
- **Inline label editing on the tree's rows only.** A type's own page keeps its form (every language, description).
- **Both pages restyled.**

## 1. Drag and drop (no "Move to…" list)

- Each row has a handle (⋮⋮) for someone who is logged in; the whole row is draggable, the handle shows that it is.
- Where a row is dropped on decides what happens (`zoneAt(offsetY, height)`):
  - its **middle half**: the dragged type goes **below** it (the row is ringed);
  - its **top or bottom quarter**: **beside** it, at its level (a line at the row's indent, above or below it).
    Beside a top-level type is the top level, so the "Drop here for the top level" strip goes.
- `dropTarget(nodes, dragged, over, zone)` (pure) gives the new supertype (`null`: the top) or `undefined` (not
  allowed: itself, its own subtypes, where it is now). Nothing is shown and nothing happens where it is not allowed.
- A drop is optimistic: the tree has the type in its new place at once.
- The "Move to…" select goes. It was the only way to move a type without a mouse: that is a gap now (noted in
  TODO, not built).

## 2. The live tree (`live()`)

- `src/poll.ts`: `pollTree({ fetchTree, every, signal, wait })`: asks for the tree every `every` ms and yields it when
  it is not what it yielded last; errors are thrown (the browser reconnects).
- `src/feed.ts`: `treeFeed = live(async function* (type) { "use server"; ... })`: on the interface's server, with the
  request's cookies (unpublished types), every `PANGLOSS_TYPOLOGY_POLL_MS` (default 3000).
- `src/state.ts`: `createTypeTree({ type, feed, api })`: a `createOptimisticStore` over the feed (`{ state, nodes }`),
  with the actions `move(id, to)` and `rename(id, label)`: each changes the store at once, calls the API, and waits
  (`until`, 15 s) for the feed to bring it back. A refusal rejects (the page shows why) and the store is the feed's
  again.
- Pure helpers in `tree.ts`: `withMove(nodes, id, to)`, `withLabel(nodes, id, label)` (both keep each level in the
  order of the labels, as the server does).
- e2e: the stack sets `PANGLOSS_TYPOLOGY_POLL_MS` short, like the review's.

## 3. Inline label editing (tree rows)

- A pencil button beside the label (logged in; shows on hover and focus). It turns the label into a text field with
  the label selected. **Enter** or leaving the field saves (`PATCH {label}`) if it changed and is not empty;
  **Escape** puts it back. While it is being edited the row is not draggable.

## 4. The look

- **Tree:** in line with the console bar (the page's own insets, as `Page`); an outline, not a stack of boxes: rows
  with no border, a hover tint, the children under a hairline indent guide; a chevron, the label, the number of
  subtypes in a small quiet pill; handle and pencil show on hover. Drop indicators in sky.
- **Item page:** a type's label is already in the console bar; under it the path, then sections with the core's
  section headings (uppercase, semibold, small); the labels as a definition list; "Edit labels" and the form's buttons
  with the core's `smallButtonClass` (`pg-button` has no style anywhere); subtypes and entities as hairline-separated
  lists with hover tints, not boxes.

## 5. Tests first

- `tree.test.ts`: `zoneAt`, `dropTarget`, `withMove`, `withLabel`.
- `poll.test.ts`: yields on change only, stops when aborted, throws errors.
- `state.test.ts`: optimistic move/rename, kept until the feed has it, undone on refusal.
- `TypeTree.test.tsx` (rewritten, feed mocked as in the review module): the tree from the feed; no select; drag
  zones (into, beside, refused places); a drop moves at once and calls the API; a refusal is shown and undone; the
  pencil, Enter, Escape, blur; not logged in: no handle, no pencil, not draggable.
- `TypeItem.test.tsx`: still passes (classes only).
- e2e `test_typology.py`: drag into, drag beside (to the top level), refused, live (a move made through the API by
  someone else shows without a reload), inline rename; the select tests go.

## As built (2026-11-04)

As planned, except:

- **The feed is opened in the browser only.** Rendered on the server, the store ran the feed there, sent "Loading…",
  and the browser never opened it after hydration. `TypeTree` now mounts the hierarchy after `onSettled`; until then it
  says "Loading…" (the first tree comes at once).
- **UI state is flushed before an action starts.** A signal written in the same handler as an action (`setOver`,
  `setEditing`) is held in the action's transition until it ends, which here is when the feed acknowledges it (up to
  15 s): the drop mark and the text field stayed. `flush()` before `move()`/`rename()`.
- In Vitest a drag must `settle()` after `dragstart`: Solid 2 does not show a written signal until it flushes, and a
  browser always has a task between the events.
- The item page's subtype rows: the label is the link, stretched over the row, so that the link's name is the label
  alone (the counts are beside it).
- Translations: `typology_edit_label`, `typology_label_of` added; `typology_move`, `typology_move_to`,
  `typology_top_level`, `typology_drop_top` removed (`ui.jsonc`).
- The module's `tsconfig.json` has the `node` types (`process.env` in `feed.ts`), as the review module's has.
- **Chips (later the same day):** each type in the tree is a chip, framed as a reference chip is (hairline, slate),
  with its number of subtypes as a segment at its end (only while they are collapsed) (`typology_subtype_count` as its title); no type tag, since every
  row is the same type. "Below this one" marks the chip (sky border and ring), not the row; the text field takes the
  chip's place inside the same frame. The rows also cancel `dragenter`, not only `dragover`: over the chip's link,
  Playwright's drag (and the spec) wants the drop allowed on entering.
- **Chip segments, adding types (later the same day):** the drag handle is the chip's first segment, the pencil and
  "add a subtype" (a branch down to the right, ↳+) its last. A type is made in a dialog (core `Modal`, the same
  `LabelsForm` as the type's page: default label, each language, description), never on a new page: from each chip
  (a subtype), from "Add a top-level type" above and below the tree, and from the console's New button (core
  `ConsoleProps.onNew`: a list page that makes its own new items gets a button calling it instead of the link to
  `/<type>/new`). The dialog stays open while the API makes the type, and says why if it does not; the type is then
  shown at once (optimistic until the feed has it) and its supertype opened. New route `POST /api/typology/{name}`
  (`{label, supertype?, description?, labels?}`, 201; 404 for a supertype not there, 409 for a language the typology
  lacks, 422 for an empty label), on `service.create`.
- **Type tags:** someone who is not logged in sees the type in front of each tree chip (`TypeTag`: the model's name in
  its kind's tint, as a reference chip has it) where someone logged in has the handle; a type's page shows its subtypes
  as chips too, with the tag, the label (the link) and their counts.
