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

## Not in this build

Choosing a part to comment on, highlighting it; a review queue page; notices.

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
