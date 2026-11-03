# Review in the interface: plan

**Status: built and tested 2026-11-03** (what differs from the plan is in "As built" at the end). The review package ([review.md](review.md)) has its API; this is
its interface: a button in the console of a reviewed document, and a panel that slides out from the right with the
status and the comments, kept up to date while the page is open.

## Decisions (the user's, 2026-11-03)

| Question | Decided |
|---|---|
| Where it lives | **An interface module of `pangloss_review`** (`pangloss_review/interface/`), with a new general extension point in core: **`consoleActions`** in a module's manifest. A project without the package sees nothing. |
| How the page hears of changes | **`live()`** (a Solid 2 server function that yields snapshots). Its generator runs on the interface's Node server, asks `GET /api/review/{id}` every few seconds with the reader's cookies, and yields only when the answer changed. No change to the Python side. |
| Which pages | **The item page and the edit page.** Review has its own API, so on the edit page it is independent of saving. |
| How much of the comments | **A conversation, a box to add one, resolve on each, and "show resolved".** A comment about a nested part shows the part's label as a tag; choosing a part is not in this build. |

## Core: `consoleActions`

A module's manifest may name components for the console of an item:

```ts
defineModule({
  name: "pangloss_review",
  components: {},
  consoleActions: { Review: () => import("./components/ReviewAction") },
});
```

Each is rendered (lazily, in a `Loading` of its own) at the right of the console of every item page and every edit
page of an existing item, before the page's own buttons, with `ConsoleActionProps`:

```ts
interface ConsoleActionProps {
  type: string;            // the item's own type
  id: string;
  model: ModelDefinition;  // its definition
  page: "item" | "edit";
}
```

It decides itself whether to show anything (review shows nothing for an entity, a class that is not reviewed, or a
reader who is not logged in). The `Console` gets the item as a new prop, `item?: { type; id }`, and `page`; the item
page passes them, and so does `ItemForm` when it edits an existing item. The manifest reader and `Manifest` in Python
learn the key (`console_actions`), so `pangloss interface check` lists them.

## The review module

```
pangloss_review/interface/
  package.json  tsconfig.json  vitest.config.ts  README.md
  src/index.ts                     the manifest
  src/api.ts                       types of the review API, and its calls (status, comment, resolve)
  src/feed.ts                      reviewFeed: live(async function* (id) { "use server"; ... })
  src/state.ts                     createReview(id): the store over the feed, and the actions (optimistic)
  src/components/ReviewAction.tsx  the console button (flag + count) and the panel
  src/components/ReviewPanel.tsx   status buttons, the conversation, the comment box
  src/**/*.test.ts(x)
```

### The feed (server function)

```ts
export const reviewFeed = live(async function* (id: string) {
  "use server";
  // the API on the server (PANGLOSS_API_URL), with the cookies of the request that opened the stream
  // GET /api/review/{id}?resolved=true; yield { reviewable: false } and stop on a 404 (or 401);
  // otherwise yield the detail when it differs from the last one, and wait PANGLOSS_REVIEW_POLL_MS (3000)
  // until the request is aborted (the page closed it)
});
```

All comments are fetched (resolved too), so that "show resolved" is a filter and does not open a new connection.
The interval is `PANGLOSS_REVIEW_POLL_MS` on the interface's server (default 3000 ms). A later improvement, if many
people have pages open: `broadcast()` to share one poller between the readers of a document, or a change feed in
the API.

The console is a portal, which the server does not render, so the feed is only ever opened by the browser (one
connection for each item page, in `ReviewAction`, which passes the state down to the panel).

### State and writes

`createReview(id)` is a `createOptimisticStore` over the feed (the pattern in Solid's docs for live
acknowledgements). Writes are `action`s that go to the review API directly (`POST /api/review/...` with `useApi()`):

- **Comment**: the comment is shown at once (an optimistic row, marked as being sent), the POST is made, and the
  action waits (`until`) for the feed to bring the comment back, with a timeout; a timeout is not an error (the
  next poll brings it).
- **Status**: the same, for the status; a refusal (403: `REVIEW_ALLOW_SELF_REVIEW` false and the reader made the
  document) reverts it and is shown in a red toast with the API's message.
- **Resolve**: the same, for the comment's `resolved`.

### The button

A `ConsoleButton` with a flag icon, coloured by status (unchecked: slate outline; errors found: a red flag;
checked: a green flag), and a small badge with the number of open comments when there are any. Its label (tooltip,
screen reader) says the status and the count. It toggles the panel (`pressed`).

### The panel

Fixed on the right, below the console bar, the height of the window, sliding in (`translate-x`) when the button is
pressed; Escape and a close button shut it. From the top:

1. The status: three buttons (Unchecked, Errors found, Checked), the current one pressed; who reviewed it and
   when. Pressing another changes it at once (its own API: nothing to do with Save).
2. The conversation: the comments, oldest first; the reader's own on the right, others' on the left (name, time,
   text, the part's label as a tag if it is about one, resolve). Resolved ones are hidden unless "show resolved"
   is on, and then shown faded. It scrolls to the newest as one arrives.
3. A box to write a comment, and Send (⌘/Ctrl+Enter sends).

## Tests

- **Core (vitest)**: `Console` renders the module actions of an item, with the props, before its own buttons, and
  none without an item; `ItemForm` passes the item when editing.
- **Python**: the manifest reader and `Manifest` keep `consoleActions` (`test_interface_modules.py`).
- **The module (vitest, in a built project)**: the button's colour/label/badge per status, nothing for a class
  that is not reviewed, the panel's conversation alignment, resolved filter, optimistic comment and status, the
  error toast; the state functions (merging, filtering).
- **e2e (Playwright)**: the e2e project gets `pangloss_review` and a reviewed `Statement`: the button and badge,
  changing the status (and the list's published state with it), adding a comment, resolving; **a comment added
  through the API by another user appears in the open panel without a reload** (the live feed); and the module's
  own vitest run in the built project. The dev-mode test opens the panel too.

## Third change (2026-11-03): references inline, documents only

**Decided by the user:** a reference to a part stays where it is written, not in an "About: …" chip over the box; the
text holds just `#<id>`, shown as a chip where the comment is read; and only documents can be referred to, reified
relations that are documents (`ReifiedRelationDocument`) included.

- Choosing in the `#` list replaces the `#words` with `#<id> ` (`withReference`); the box shows the raw id until it is
  sent. A comment may refer to several parts. A finished `#<id>` is not taken for a `#` being typed.
- Read, each `#<uuid>` in a comment's text is a chip in its place (`CommentText`, `PartChip`: the type, tinted as a
  document, and the label, shortened; a click shows the part on the page). A part no longer in the document is struck
  through, "(no longer there)". Before the parts are read, a chip shows the label the server kept (for the `targetId`)
  or the start of the id.
- The API still keeps one part per comment: the interface sends the **first** reference as `targetId`, so the server
  keeps its label at the time. A comment made through the API with a `targetId` and no reference in its text has the
  chip first.
- The parts offered (`partsOf`) are only nodes whose model is a **Document** or a **ReifiedRelationDocument** (any depth,
  through plain reified relations, conjunctions and spaces, which are not offered themselves). A chip is tinted by its
  part's kind. While the parts are still being read, Enter in the open list waits rather than making a new line.
- The chip over the box, and its strings `review_about` and `review_part_clear`, are gone; the button is "Refer to a
  part…".

## Not in the first build (built after it, below)

Choosing a part to comment on, highlighting it; a review queue page. (Notices by email are not planned here.)

## Second build (2026-11-03): comments on a part, the queue, self-review in the browser

**Decisions (the user's).** A part is chosen by typing `#` in the comment box (the user's idea; a dropdown was the
fallback): a list of the document's parts appears, type and label shortened. The queue is a page, `/review`, linked
from the navigation bar, read when it is shown (not live: going back and forth reads it again).

- **`#` in the box.** At the start or after a space, `#` opens a list over the box of the parts of the document: every
  node with an id inside it that is not an entity, an embedded value or what refers to it from elsewhere (`partsOf`, from
  the document as saved, read when the panel is first opened). Words typed after it filter (by label and type name, in
  any language; spaces allowed while something still matches, so the list closes once the text has moved on). ↑/↓ and
  Enter or Tab (or a click) choose; the `#words` are taken out of the text and the part becomes a chip, "About: Report
  section · Costs", with ✕. A comment is about one part (the API's `targetId`), so a second `#` replaces the chip:
  an inline token in a plain textarea could not be styled, and would suggest several. Escape closes the list and not the
  panel. A button beside Send ("About a part…", now "Refer to a part…") puts a `#` at the caret, for those who do not
  know it. (Superseded by the third change above: the reference is now inline.)
- **The part on the page.** The view page's nested blocks are now marked `data-item-id` as the form's are
  (`ItemContents`); choosing a part, or clicking a comment's "About: …", scrolls to it and lights it up. A comment about
  a part that is no longer in the document is struck through, "(no longer there)".
- **The queue** (`ReviewQueue`, the module's route `/review`; `pangloss_review/interface_config.py` adds the link
  "Review", for someone logged in). Status tabs (Unchecked first), a filter by type (the reviewed classes: a new route,
  `GET /api/review/types`), a table (status flag, type, label linking to the document, who made it, when it changed, who
  reviewed it, open comments), the oldest change first, 25 to a page with Previous / Next. Status, type and page are in
  the address. Needs a login (the login dialog otherwise).
- **Self-review in the browser.** The e2e project now has `REVIEW_ALLOW_SELF_REVIEW = False`; its reports are made by a
  third user, `ann`, and a test checks that checking one's own report is refused, undone and said in a red toast.

Tests: Vitest `parts.test.ts`, `Composer.test.tsx`, more in `ReviewPanel.test.tsx` (44 in the module), core
`ItemContents.test.tsx` (the marks); Python `test_meta_and_status.py` (the types, the nav link); e2e `test_review.py`
(15) and the dev-build test (the `#` list and the queue).

## As built (2026-11-03)

- **Modules' server functions had to be compiled.** The Solid plugin compiles `"use server"` only in `src/**` of the Vite root, so
  `vite.config.ts` now adds `../modules/*/src` and the `--link` roots to `serverFunctions.filter`. Without it `live()` gets a plain
  function and throws "live expects a server function reference".
- **The feed is opened with `invoke(reviewFeed, { signal }, id)`**, and `createReview` aborts it when its owner goes, or before a
  re-run: a generator waiting in `for await` for the next snapshot cannot be stopped from outside, so without the signal the stream
  (and the poll on the server) would stay open until the next change.
- **The poll is its own function** (`poll.ts`: `pollReview`), so it is unit-tested without a server; `feed.ts` only adds the request's
  cookies, the API's address and the interval.
- **A 401 later in the stream is thrown** (the access cookie ran out while the page was open): `live()` reconnects, and the store's
  `onstatus` asks the browser to refresh its cookies first (`POST /users/session/refresh`). A 401 on the first ask is "no review".
- **The username is read once in a memo** in `ReviewAction`: a prop is a getter, and reading the session in it from inside an action
  (no owner there) failed.
- **Errors**: a console action that fails is logged in the browser's console by `Console`; a refused write is logged and shown in a red
  toast with the API's message.
- **The e2e proxy streams** a response without a `Content-Length` (it used to read the whole of it first, so a live stream never
  arrived), and the e2e project polls every 300 ms (`PANGLOSS_REVIEW_POLL_MS`).

Tests: Vitest in the module (`poll.test.ts`, `state.test.ts`, `ReviewPanel.test.tsx`, `ReviewAction.test.tsx`: 29), in core
(`ConsoleActions.test.tsx`), Python (`test_interface_modules.py`), e2e (`test_review.py`: 8, and `test_dev_mode.py::test_the_review_panel`).
