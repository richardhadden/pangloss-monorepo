# Review: checking documents before they are published ✅

**Status: built and tested: the `published` flag, the package, the API routes, the commands, the guide ([guide/review](../guide/review/README.md)), and (2026-11-03) the interface: a review button and panel in the console of a reviewed document, kept up to date while the page is open ([review.md#the-interface-the-review-panel-and-the-queue-plan-of-2026-11-03-built](review.md#the-interface-the-review-panel-and-the-queue-plan-of-2026-11-03-built)). The queue page (`/review`) and comments on a part (`#`) were added the same day. Not built: notices by email.** The package is `pangloss-review` (`INSTALLED_APPS = ["pangloss_review"]`). The
decisions marked **(decided)** were made by the user; **(open)** ones are still to settle; the rest follow from how
`deleted`, meta slots and `pangloss-history` already work.

## What is wanted

- A head document can be checked by another user before it is published. A document that is not published cannot be
  seen (like one that is deleted), except by those who review or wrote it.
- Status: **unchecked** (the default), **checked, errors found**, **checked, no errors found** (which publishes it).
- Comments on a document: a list of (user, date, text), optionally about one of the documents nested in it.
- A project that does not install the package sees no difference: everything is published.

## `published`: the core part

`deleted` is not a model field. It is a property of the head node that the Cypher builders test
(`NOT coalesce(n.deleted, false)`, with a nested document taking its head's): `read_query`,
`list_query` (five places), `search_query` (three), `autocomplete_query` (all in `pangloss-cypher` since 2026-11-01, and the rule itself in `fragments`), `validate_write`,
`build_update_query`. `published` is the same kind of thing, so it goes in the same places:

- Stored on the head node as `published`. **No property means published** (`coalesce(head.published, true)`), so
  existing data and projects without review are untouched, and nothing needs migrating.
- Read, list, search, autocomplete and "what refers to this" skip a document that is not published, or nested in
  one, exactly as for `deleted`.
- Unlike `deleted`, some people must see them. **(decided)** A user who is logged in sees unpublished documents
  (in reads, lists and searches); a request that is not logged in does not. The ContextVar
  `pangloss_users.see_unpublished` says which (default `True`, so scripts, commands and tests see everything);
  the API sets it on every request (`dependencies.set_visibility`, an app-wide dependency: a valid token is
  `True`, none or a bad one `False`, and reading is still open). The Memgraph builders pass it as the query
  parameter `$see_unpublished`. A later `only` mode (the reviewers' queue) is the review package's, not the core's.
- New documents are written `published = false` **only when the review package is installed and the class is
  reviewable** (a listener on the write event, as history does, sets it in the same transaction); otherwise
  nothing is written, which is "published".
- An unpublished document may refer to published entities, and may be referred to by other unpublished
  documents; a published document refers to entities only, so nothing published points at it. (Documents are
  never the target of a relation, so hiding one hides no edge of anything else.)
- Entities are not reviewed (they are shared, and not part of any one document).

## The review state

On the head node (plain properties, so it can be filtered and indexed): `review_status` (`unchecked`,
`errors_found`, `checked`), `reviewed_by`, `reviewed_at`. `published` is `true` exactly when the status is `checked`
(set in one transaction with it). A status change is an event of its own and is written to the history of the
document if `pangloss-history` is there.

Which documents are reviewed is a meta slot on the class, `_review_meta = ReviewMeta(reviewable=True)` (meta slots
already exist for this), inherited. **(decided)** Opt-in: the default is not reviewable, so installing the package
changes nothing until models are marked.

## Comments

Memgraph properties cannot hold a list of maps, so a comment is a node, `(:PGReviewComment)` linked to the head
document, with `id`, `username`, `at`, `text`, and optionally `target_id` and `target_label`:

- `target_id` is the id of a nested document. Nested documents have ids, so a comment can name one. What the label
  of the part was **when the comment was made** is kept in `target_label`, so a comment still reads right if the
  part is later changed.
- If the part is later removed, nothing breaks: the comment is shown as being about a part that is no longer
  there ("orphaned"). Whether an id survives an update of the document has to be checked in the update builder before
  this is promised. **(to check)**
- A comment can be marked resolved (by anyone who can comment). Comments are not edited or deleted; a resolved one
  is just hidden by default.
- Comments belong to the head document and go with it when deleted; they are not part of the document's content,
  so they do not make a history version.

## Who may review **(decided)**

Permissions are not written yet (`implementation_docs/users.md`), and users have only `admin`. Anyone may check a document. The
setting `REVIEW_ALLOW_SELF_REVIEW` is **true by default**; set to false, a user may not check a document they
created or last edited (`PGCreation` / `PGUpdate`). A "reviewer" group is added when permissions exist.

## After a published document is edited **(decided)**

Editing does not change the review state: a document that was published and checked stays so. If the change is one
that should be checked again, the person who made it sets the status back (to `unchecked`, or `errors_found`),
which unpublishes it, as the status always decides `published`. (A later improvement: an "edited since checked"
marker in the queue, from the version number; not part of the first build.)

## API (under `/api/review`, added by the package)

| Route | |
|-------|-|
| `GET /api/review/queue?status=&type=` | Documents to check (unpublished, by status), newest first |
| `GET /api/review/types` | The classes that are reviewed (for the interface's filter) |
| `GET /api/review/{id}` | Status, who and when, and the comments |
| `POST /api/review/{id}/status` | `{status, comment?}`; refused for the author unless allowed |
| `POST /api/review/{id}/comments` | `{text, target_id?}` |
| `POST /api/review/{id}/comments/{cid}/resolve` | |

and `pangloss review queue|status|publish-all` commands (`publish-all` for a project that adopts review late: it
marks the reviewable documents there as `checked`).

## Not in this package

The interface is the package's interface module ([review.md#the-interface-the-review-panel-and-the-queue-plan-of-2026-11-03-built](review.md#the-interface-the-review-panel-and-the-queue-plan-of-2026-11-03-built)); still not built there:
comments shown next to the parts they are about (they are in the panel, and a click shows the part). Email or other notices.

## Build order

0. ✅ Ids of nested documents. An update deletes the tree under the head and writes it again, but a nested
   document in the `Update` must carry its `id` (required), so a part sent back with its id **keeps it**; a new part
   needs an id from the client; a part left out is gone. A comment's `target_id` is therefore stable as long as
   the client sends parts back unchanged (the interface does). This turned up a defect: the update **replaced all
   properties of the head node**, which would have published an unpublished document when it was edited, and lost
   the review state. `KEPT_PROPERTIES` (`published`, `review_status`, `reviewed_by`, `reviewed_at`) in
   `build_update_query.py` are now kept; tested in `test_unpublished_live.py`.
1. ✅ Core: `published` in the read, list and search builders with `$see_unpublished`, the API dependency, and `test_unpublished_live.py`. (Not filtered, on purpose: autocomplete and entities, `validate_write`, deletion's "what refers to this", which must still count an unpublished document.)
2. ✅ The package (`packages/pangloss-review`): `ReviewMeta` (slot `_review_meta`), `service` (`get_state`, `set_status`, `add_comment`, `list_comments`, `resolve_comment`, `queue`), the Memgraph side (`databases/memgraph/review.py`, `*_in_db` in `exposed_functions`), tests in `pangloss-memgraph/tests/test_review_live.py`. Two differences from the plan above: a new document is made unpublished by a **new core hook, `hooks.new_head_properties`**, called by the create query (a listener to `after_write` runs after the commit, so the document would have been visible for a moment); and the hook is installed when `pangloss_review.meta` is imported, which a model that is marked has done, so it works even if the app is not in `INSTALLED_APPS`. A document of a class that became reviewable later has no status and counts as published and checked.
3. ✅ (done, with the meta change below) The API routes, the commands, the guide page, settings (`REVIEW_ALLOW_SELF_REVIEW`).

## Reading the state: in the `meta`, and the comments apart **(decided)**

`published` (default true) and `review_status` (`null` unless review keeps one) are in `meta` of a head view, read
by the same query as the document (`build_read_query`), so a page can show "unchecked" without another request.
They are read only: `Create` and `Update` have no review fields, the create hook sets the state, and an update keeps
it (`KEPT_PROPERTIES`). A document of a class that became reviewable later reads `reviewStatus: null`, though
`GET /api/review/{id}` says `checked`. Comments are not in the view: `GET /api/review/{id}` has them. The reference view carries them too (`meta.published`, `meta.reviewStatus`: the list, search and queue queries fill them in), and a list can be filtered by them: `?published=` and `?review_status=` on `GET /api/<Model>`, `published=` and `review_status=` on `Model.list(...)`, in the SDK and the type stubs. The filter is applied to the head document after the visibility test, so a request that is not logged in finds no unpublished document whatever it asks. Structured search can too: `published` and `review_status` are conditions of a head document's `where` (see [structured search](structured-search.md#published-and-reviewed-built-with-pangloss-review)).
Tests: the parts that need no database are in `packages/pangloss-review/tests`; the rest, including the `pangloss review` commands run through their own event loop (`test_review_cli_live.py`), are in `pangloss-memgraph/tests` (`test_review_live.py`, `test_unpublished_live.py`).
**Writing with a status (decided later):** for data made outside the system and known to be right, `save(published=True)` (= `checked`) or `save(review_status=...)` on a Create or Update of the SDK, and the same in the in-process database module. Over HTTP it is `?review_status=` on the `POST`/`PUT` (an ASGI middleware of the review package, so the model routes are unchanged), in the core a ContextVar `hooks.requested_review_status`; `hooks.new_head_properties` (create) and the new `hooks.updated_head_properties` (update, applied after the kept properties in `build_update_query`) are what the package answers with. Ignored for classes that are not reviewed; refused with `REVIEW_ALLOW_SELF_REVIEW` false.
**And in the document itself (decided later):** `Create` and `Update` of every Document have an optional `review_status` (`unchecked`, `errors_found`, `checked`; `reviewStatus` in JSON), for a load in which each item has its own. It is a field of the base classes (`_DocumentCreateBase`, `_DocumentUpdateBase` and their DB forms), not stored as a field: the builders pass it to the same hooks (`hooks.requesting_review_status`), so the review package writes `published`, `reviewed_by`, `reviewed_at` as for any other way of asking, and what the document says wins over what the call says. Without review, or for a class it does not review, it is ignored. This makes it a reserved word in a way it already was (`RESERVED_PROPERTIES`). A `bulk-load` record is the fields of a `Create`, so a line can say `"review_status": "checked"`; a line that does not gets the default (`unchecked` for a reviewed class).
`publish-all` was dropped from the plan: a document with no status counts as published already.

## The interface: the review panel and the queue (plan of 2026-11-03, built)

**Status: built and tested 2026-11-03** (what differs from the plan is in "As built" at the end). The review package ([review.md](review.md)) has its API; this is
its interface: a button in the console of a reviewed document, and a panel that slides out from the right with the
status and the comments, kept up to date while the page is open.

### Decisions (the user's, 2026-11-03)

| Question | Decided |
|---|---|
| Where it lives | **An interface module of `pangloss_review`** (`pangloss_review/interface/`), with a new general extension point in core: **`consoleActions`** in a module's manifest. A project without the package sees nothing. |
| How the page hears of changes | **`live()`** (a Solid 2 server function that yields snapshots). Its generator runs on the interface's Node server, asks `GET /api/review/{id}` every few seconds with the reader's cookies, and yields only when the answer changed. No change to the Python side. |
| Which pages | **The item page and the edit page.** Review has its own API, so on the edit page it is independent of saving. |
| How much of the comments | **A conversation, a box to add one, resolve on each, and "show resolved".** A comment about a nested part shows the part's label as a tag; choosing a part is not in this build. |

### Core: `consoleActions`

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

### The flag in lists ✅

A list's row shows the review status at its right (`resultMarks: { StatusFlag }`, `ListStatusFlag`): from
`meta.reviewStatus`, which the list already sends, so no request of its own. An item inside a reviewed document has its
head's status. Someone not logged in sees none, as with the rest of review, and is only ever shown what is checked. A
document of a reviewed class written before the class was marked has no stored status, so no flag, though its item page
counts it as checked if it is published.

### The review module

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

#### The feed (server function)

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

#### State and writes

`createReview(id)` is a `createOptimisticStore` over the feed (the pattern in Solid's docs for live
acknowledgements). Writes are `action`s that go to the review API directly (`POST /api/review/...` with `useApi()`):

- **Comment**: the comment is shown at once (an optimistic row, marked as being sent), the POST is made, and the
  action waits (`until`) for the feed to bring the comment back, with a timeout; a timeout is not an error (the
  next poll brings it).
- **Status**: the same, for the status; a refusal (403: `REVIEW_ALLOW_SELF_REVIEW` false and the reader made the
  document) reverts it and is shown in a red toast with the API's message.
- **Resolve**: the same, for the comment's `resolved`.

#### The button

A `ConsoleButton` with a flag icon, coloured by status (unchecked: slate outline; errors found: a red flag;
checked: a green flag), and a small badge with the number of open comments when there are any. Its label (tooltip,
screen reader) says the status and the count. It toggles the panel (`pressed`).

#### The panel

Fixed on the right, below the console bar, the height of the window, sliding in (`translate-x`) when the button is
pressed; Escape and a close button shut it. From the top:

1. The status: three buttons (Unchecked, Errors found, Checked), the current one pressed; who reviewed it and
   when. Pressing another changes it at once (its own API: nothing to do with Save).
2. The conversation: the comments, oldest first; the reader's own on the right, others' on the left (name, time,
   text, the part's label as a tag if it is about one, resolve). Resolved ones are hidden unless "show resolved"
   is on, and then shown faded. It scrolls to the newest as one arrives.
3. A box to write a comment, and Send (⌘/Ctrl+Enter sends).

### Tests

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

### Third change (2026-11-03): references inline, documents only

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

### Not in the first build (built after it, below)

Choosing a part to comment on, highlighting it; a review queue page. (Notices by email are not planned here.)

### Second build (2026-11-03): comments on a part, the queue, self-review in the browser

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

### As built (2026-11-03)

- **Modules' server functions had to be compiled.** The Solid plugin compiles `"use server"` only in `src/**` of the Vite root, so
  `vite.config.ts` now adds `../modules/*/src` and the `--link` roots to `serverFunctions.filter`. Without it `live()` gets a plain
  function and throws "live expects a server function reference".
- **The feed is opened with `invoke(reviewFeed, { signal }, id)`**, and `createReview` aborts it when its owner goes, or before a
  re-run: a generator waiting in `for await` for the next snapshot cannot be stopped from outside, so without the signal the stream
  (and the poll on the server) would stay open until the next change.
- **The poll is its own function** (`poll.ts`: `pollReview`), so it is unit-tested without a server; `feed.ts` only adds the request's
  cookies, the API's address and the interval.
- **A 401 later in the stream is thrown** (the access cookie ran out while the page was open). A 401 on the first ask is "no review".
  *Corrected 2026-11-10:* `live()` does not reconnect after an error the feed's server throws: it passes it to the reader, so the
  review button failed after half an hour on a page and nothing more came (found by the first browser test of it,
  `e2e/test_changed_project.py`). `createFeedReader` (core) now does it, for every feed: on a 401 it asks for a new access cookie
  (`POST /users/session/refresh`) and opens the feed again; refused again at once, the reader is logged out and the error is passed on.
  (`onstatus` still asks for a new cookie when a connection drops and comes back by itself.)
- **The username is read once in a memo** in `ReviewAction`: a prop is a getter, and reading the session in it from inside an action
  (no owner there) failed.
- **Errors**: a console action that fails is logged in the browser's console by `Console`; a refused write is logged and shown in a red
  toast with the API's message.
- **The e2e proxy streams** a response without a `Content-Length` (it used to read the whole of it first, so a live stream never
  arrived), and the e2e project polls every 300 ms (`PANGLOSS_REVIEW_POLL_MS`).

Tests: Vitest in the module (`poll.test.ts`, `state.test.ts`, `ReviewPanel.test.tsx`, `ReviewAction.test.tsx`: 29), in core
(`ConsoleActions.test.tsx`), Python (`test_interface_modules.py`), e2e (`test_review.py`: 8, and `test_dev_mode.py::test_the_review_panel`).
