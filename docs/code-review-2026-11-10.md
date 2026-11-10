# Code quality review, 2026-11-10

Scope: redundancy, code that could be written once, and parts of the interface that could be one component. Branch
`code-review-3`, from `27149754`. The earlier review is [code-review-2026-10-31.md](code-review-2026-10-31.md).

This page lists what was changed (✅), what was found and left (⏳, with the reason), and what was measured.

**How it was checked.**

- `jscpd` (copy-paste detection) over the TypeScript and the Python of `packages/`; `vulture` over the Python; a scan
  for exported names nothing uses; a scan of every `<svg>` for the rules of an icon.
- I read the largest files of the interface and each place the tools named.
- The whole suite (`./run_tests.sh`: ruff, ty, the packages on Memgraph, Neo4j, the browser tests) was run on the
  branch **before** any change, and passed, so that a later failure would be mine.
- The built interface was measured before and after on the smoketest project (56,000 people, its own Memgraph on
  :7697): see [Performance](#performance).

## Summary

| # | Change | Kind | Lines |
|---|---|---|---|
| 1 | The record of migrations is written once, in `pangloss-cypher` | Python, duplication | −580, +350 |
| 2 | One poll loop and one server-side API client for `live()` feeds | interface, duplication | 4 copies → 1 |
| 3 | One reader of a feed for a store (`createFeedReader`), one `createInBrowser` | interface, duplication | 4 and 3 copies → 1 |
| 4 | `PageFrame`: the `main` of a page | component | 8 copies → 1 |
| 5 | `Pager`: Previous / Page n of m / Next | component | 2 copies → 1 |
| 6 | `CloseIcon`: the ✕ | component | 7 copies → 1 |
| 7 | `readableTime`, `firstParam` | interface, duplication | 6 and 5 copies → 1 |
| 8 | Nine icons had no `select-none` | rule of the look | |
| 9 | Two parameters nothing passes, removed | Python, dead code | |

In all: 66 tracked files changed (the docs and the skill among them), 1,321 lines out and 252 in, and 15 new files
(539 lines of code, 378 of tests).
Nothing a person sees or types has changed, with one exception said in §5 (the names of four translation slots).

## What was changed

### 1. The record of migrations is one implementation ✅

`pangloss_memgraph/.../migration_backend.py` and `pangloss_neo4j/.../migration_backend.py` each had the same 300
lines: `open_session`, `has_data`, `applied`, `lock`, `unlock`, `record`, `stored_progress`, `progress_saver`,
`apply`, `unapply`, `dry_run`. They differed in one thing, the name of the logger. The refactor that made
`pangloss-cypher` moved whole modules, and `tests/test_no_copies.py` compares whole modules, so a half-shared file
was not seen.

They are now `pangloss_cypher/migrations/record.py`. Each backend's `migration_backend` names them
(`from pangloss_cypher.migrations.record import apply as apply, ...`) and keeps what is its own: the constraints of
the record (`ensure_ready`), and for Memgraph the snapshots. Memgraph's file went from 485 lines to 204, Neo4j's
from 389 to 103.

- **The logger is still the backend's** (`pangloss.memgraph.migrations`, `pangloss.neo4j.migrations`), found from
  the database's dialect, so `docs/logging.md` and anyone who filters by name are not affected.
- I checked by script that the moved text is the old text, but for the logger and white space.
- New tests: `conformance/test_migration_record_log.py` (the lock is logged by the backend in use, at the levels the
  docs say; each backend's functions *are* the kit's), run on both backends. `test_no_copies.py` now also fails if
  a backend defines a function that the kit's record has.

### 2. A `live()` feed: the poll loop and the client ✅

Four modules (review, typology, users, admin) each had their own `pause()` and their own loop "ask every N ms,
yield what changed", and five places built "a client of the API that passes on the cookies of this request" by hand
(the four feeds and the application's `api.ts`).

Now in `interface-core/src/api/`:

- `pause(ms, signal)` and `pollChanges({ read, every, signal, wait })` (`poll.ts`);
- `createRequestApiClient(request)` and `serverApiUrl()` (`requestClient.ts`).

`typology/poll.ts`, `users/poll.ts` and `admin/poll.ts` are deleted, with the tests that tested the same loop three
times; core's `poll.test.ts` has those cases once (changed-only, the waits, an error is thrown, an aborted poll asks
nothing, and `pause`, which had no test). **Review keeps its own `pollReview`**: its rule (a 404, or a 401 on the
first ask, means "no review" and ends the feed) is review's, so it stays in review and uses only core's `pause`.

### 3. A store that follows a feed ✅

`review/state.ts`, `typology/state.ts`, `users/state.ts` and admin's `JobsSection` each had the same 15 lines inside
their store's generator: close the connection of the run before, abort on leaving the page, ask for a new access
cookie on a reconnect, do not pass on the error of an abort. It is subtle (the comments said so each time) and is
now `createFeedReader(open, api)` (`primitives/liveFeed.ts`), with a test of each of those four things
(`liveFeed.test.ts`); they had none of their own before. The same file has `createInBrowser()`, the signal "the
page has settled in the browser" that three components made by hand.

### 4. `PageFrame` ✅

`<main class={["w-full py-8", { "px-8": navPinned(), "px-20": !navPinned() }]}>` was written out in seven module
pages (calendar, history, typology, review, admin, users ×2) and was a component only in the application
(`interface-app/src/Page.tsx`), where a module cannot reach it. It is now `PageFrame` in core, and all of them use
it. (Not `Page`: core already exports a type of that name.) It lives in `context/navbar.tsx`, beside the state it
reads, for the reason in [what an extraction costs](#what-an-extraction-costs).

### 5. `Pager` ✅

The review queue and a user's page had the same pager. It is `Pager` (`page`, `pages`, `onPage`) in core, with a
test. **Its text is now four slots of core** (`pager_pages`, `pager_previous`, `pager_next`, `pager_page`) instead
of four of review and four of users with the same words: a project that had overridden `review_queue_next` or
`users_next` in its own `translations/ui.jsonc` must rename the key. `docs/interface-strings.md` says so.

### 6. `CloseIcon` ✅

The ✕ (`M6 6l12 12M18 6L6 18`) was drawn seven times: `Modal`, `NavBar`, `ItemForm`, `SearchPanel` (which had made
itself a local `RemoveIcon`), the history panel, the version drawer, the review panel. It is `CloseIcon` with a
`size` (`5`, `4`, `3.5`) that sets the stroke with it, which is the rule in the skill ("the line is the same weight
on screen") written down once. It shares a file with `Spinner` (`primitives/icons.tsx`).

### 7. `readableTime` and `firstParam` ✅

"A time in the language of the page, or as it came if it cannot be read" was written six times (the console,
history, review ×2, users, Zotero) and "the first, if a parameter is given twice" five times. Both are in
`schema/lookup.ts` and tested. History's `when` and Zotero's `readableTime` keep their names and call core's.

### 8. Icons without `select-none` ✅

The rule is that every icon has it. Nine did not: three in the calendar's bar, one in the month grid, one in the
history panel, two in `Clip`, two in `NumberInput`. Added.

### 9. Dead parameters ✅

`ModelRegistry.finalise(allow_cycles=...)` and `bases_for(embedded_base=...)` were read by nothing and passed by
nothing. Removed.

## Performance

Measured on the built interface (`pangloss interface build` + `serve`) of `pangloss-smoketest`, in Chromium, the
unchanged code and the changed code on the same machine one after the other. "Throttled" is 80 ms of latency and
8 Mbit/s; times are the median of five loads. `out` is logged out, `in` logged in.

| Page | Requests | JS on the wire (B) | All transferred (B) | Hydrated (ms) | Throttled load (ms) |
|---|---|---|---|---|---|
| out `/` | 49 → 49 | 134353 → 134950 (+597) | 193558 → 194134 (+576) | 57.9 → 60.3 | 930 → 944 |
| out `/Person` | 51 → 50 | 141912 → 142143 (+231) | 205805 → 205702 (−103) | 120.5 → 128.4 | 944 → 963 |
| out `/Person/:id` | 66 → 65 | 149367 → 149586 (+219) | 216386 → 216269 (−117) | 78.3 → 78.5 | 1091 → 1127 |
| out `/Factoid/:id` | 65 → 64 | 149367 → 149586 (+219) | 218300 → 218182 (−118) | 78.7 → 78.4 | 1110 → 1128 |
| out `/calendar` | 52 → 52 | 134240 → 134760 (+520) | 223540 → 224037 (+497) | 997 → 947 | 1374 → 1258 |
| in `/` | 49 → 49 | 134353 → 134950 (+597) | 193629 → 194203 (+574) | 56.7 → 58.2 | 922 → 928 |
| in `/Person` | 51 → 50 | 141912 → 142143 (+231) | 205870 → 205768 (−102) | 119.6 → 119.7 | 945 → 940 |
| in `/Person/:id` | 79 → 78 | 200702 → 200275 (−427) | 273198 → 272433 (−765) | 84.4 → 85.0 | 1079 → 1080 |
| in `/Factoid/:id` | 79 → 78 | 207773 → 207346 (−427) | 281019 → 280257 (−762) | 104.9 → 87.9 | 1091 → 1106 |
| in `/calendar` | 52 → 52 | 134240 → 134760 (+520) | 224229 → 224730 (+501) | 1202 → 861 | 1138 → 1246 |
| in `/Factoid/:id/edit` | 86 → 85 | 209456 → 208980 (−476) | 303391 → 302675 (−716) | 118.0 → 133.0 | 1126 → 1141 |
| in `/Factoid/new` | 62 → 61 | 168465 → 168694 (+229) | 233947 → 233842 (−105) | 86.7 → 86.7 | 1091 → 1043 |
| in `/review` | 53 → 54 | 132984 → 133696 (+712) | 198491 → 199503 (+1012) | 200.1 → 207.7 | 962 → 968 |
| in `/users/:name` | 52 → 53 | 132401 → 133049 (+648) | 196465 → 197402 (+937) | 67.5 → 67.9 | 938 → 944 |
| in `/Factoid/:id/history` | 56 → 56 | 144379 → 144838 (+459) | 222814 → 223265 (+451) | 2631 → 2644 | 2689 → 2716 |
| in `/OccupationType` | 55 → 54 | 155738 → 155408 (−330) | 218145 → 217475 (−670) | 307.5 → 311.1 | 1007 → 1010 |

All the client's JavaScript together: 1,253,954 → 1,250,794 bytes (gzip 330,487 → 329,309), in 112 files as before.
No page logged an error in either run.

**What this says, plainly.**

- **Times did not change.** Every difference in the two time columns is inside what the same build gives from one
  run to the next (the calendar's own figures moved by 300 ms between two runs of the unchanged code).
- **One request fewer** on the list, the item, the edit and the new-item pages and on a typology (the application's
  `Page.js` chunk is gone).
- **Not everything is better, and I could not make it so.** The home page, the calendar and the history page fetch
  about 0.5 kB more (0.3%), and `/review` and a user's page fetch one request and about 1 kB more (0.5%). The reason
  is the next section. If you would rather not pay that, the two cheapest things to undo are `Pager` (gives back the
  request on those two pages) and `PageFrame` for the module pages (gives back about 0.3 kB on the home page, and
  loses the request saved on the main pages).

### What an extraction costs

As the build stands (found on 2026-11-08: the Solid plugin makes every `lazy()` target an entry, and Rolldown puts
each module that the frame and a lazy entry share in a chunk of its own), **a new shared file is a new request**, and a very small file hardly compresses. My first build of these changes had
`CloseIcon.tsx`, `params.ts`, `PageFrame.tsx` each as a file: two more requests on every page. So:

- `CloseIcon` is in one file with `Spinner` (`icons.tsx`), which every page already fetched;
- `readableTime` and `firstParam` are in `schema/lookup.ts`, likewise;
- `PageFrame` is in `context/navbar.tsx`, likewise;
- `Pager` is a file of its own, because only two pages use it and putting it in a file of the frame would make
  every page carry it.

This is why the code moved into shared files costs a few hundred bytes on pages that did not have it before, though
the total is smaller. The measured fix for the chunking (grouping the frame's modules: 6 requests instead of 44)
would remove this cost and the reason for these placements; it is not applied, and is a decision of its own.

## Found, and left

Each is real duplication or a candidate component. None is changed, for the reason given.

| What | Where | Why left |
|---|---|---|
| `reasonOf(error)`: "the API's own words, or the error's" | 7 modules, the same three lines | Core has `useErrorText()`, which says more (its own words for 401, 403, 5xx). Using it changes what a person reads when a write is refused: your call. A plain `errorReason` in core would be the no-change version |
| `run_connected(ctx, fn)`: initialise the models, connect, run, disconnect | 5 add-on CLIs (calendar, zotero, typology, review, derived), and by hand in admin, rdf, history | The add-ons do not import `pangloss_cli`, and their tests pass a stand-in for the project, so a method on `Project` would break both. The generic home would be a function in `pangloss-core` that takes the project; small, but a new public name: ask first |
| The heading of a page (`h1` with a hairline under it) | 8 pages, one class string | A `PageHeading` in core is the obvious component. Left because of the cost above; do it with the chunking fix |
| `<Errored><Loading fallback="Loading…">` round a page's contents | about a dozen pages, of the modules and the application | Could be part of `PageFrame` (`<PageFrame loading>`). It changes where the boundaries are, which on the server is behaviour (`[SSR_BOUNDARY_WATERFALL]`): needs its own careful pass |
| The type chip in the calendar's month grid | `MonthGrid.tsx:29` against `ReferenceChip.tsx:66` | It is a smaller chip drawn by hand (0.6 rem), so not a `ReferenceChip`, which the rule asks for everywhere. Either `ReferenceChip` gets a `size`, or this is a said exception: a decision about the look |
| The tab of a semantic space, drawn twice | `Console.tsx` (`Wrapped`) and `SpaceBands.tsx` (`SpaceTabs`) | Nearly the same, with different rounding and lines for the bar. Merging them risks the half-pixel faults that took time to get right; needs screenshots at each depth |
| Fold buttons in a head bar, three times with the same label and title | `Head.tsx` | Inside one file; a local `FoldButton` would do. Low value, left for time |
| The storage listener and `newKey` | `context/clipboard.tsx`, `context/stash.tsx` | Two copies of ten lines; a third user would justify a `createStoredList` |
| `binding.ts`, `LiteralEditor.tsx`, `ItemContents.tsx`, `TypeMenu.tsx`: blocks of 7–17 lines repeated inside the file | core | Each is a pair; read, and none hides a bug |
| `SearchPanel.tsx` (1,573 lines) and `ModelFields.tsx` (1,332) | core | Long, but each is one lazy chunk on purpose, and splitting the file would not split the chunk. `SearchPanel`'s rows (`ConditionRow`, `IncomingRow`, `SpacesRow`…) could move to files beside it with no cost; not done because the branch `fix-search-form` is not merged and touches the same lines |
| The backends' `cli.py` (97 lines the same), `backend.py` (70), `initialise_database.py` (90), `setup.py`, `database.py` | `pangloss-memgraph`, `pangloss-neo4j` | The next thing to move into the kit after §1. `database.py` and `backend.py` are mostly lists of names passed on, which is how a backend is meant to look. The CLI commands are the same code calling different modules: a factory in the kit would do, but it is CLI surface on two databases and wants its own change |
| `databases/api` and `databases/api_sync` | `pangloss-sdk` | The async and the sync client, the same but for `await`. Known and usual; generating one from the other is the only cure |
| Exported and used by nothing | `colourTint` (core), `isRelation` (core), `CALENDARS` (calendar), `useModel` (core) | Public names a module or a project may use; `useModel` is in the docs. Not dead in the sense that matters |
| The same helper three times in the conformance tests | `test_migration_batches.py`, `test_migration_dry_run.py`, `test_migrations_relations.py`… | Tests read better with their set-up beside them |

One more thing, not code: **`pangloss-smoketest/.pangloss/interface/` is tracked by git** (322 files). It is the
generated copy that every command writes over, and it was stale. I built into it to measure and put it back as it
was. It should be in `pangloss-smoketest/.gitignore` and removed from the index.

## Tests

New tests, all passing:

| Test | What it holds |
|---|---|
| `interface-core/src/api/poll.test.ts` | the poll sends only what changed, waits as long as asked, throws an error, asks nothing when aborted; `pause` ends on time and at once on abort |
| `interface-core/src/api/requestClient.test.ts` | where the server looks for the API; the cookies of the request are passed on; none, none |
| `interface-core/src/primitives/liveFeed.test.ts` | a feed is passed on; leaving closes it without an error; a second run closes the first; a failing feed throws; only a reconnect asks for a new cookie |
| `interface-core/src/primitives/Pager.test.tsx` | no pager for one page; the text; the page asked for; the ends are disabled; it follows its props |
| `interface-core/src/primitives/icons.test.tsx` | the ✕ has the size, stroke and `select-none` of each size |
| `interface-core/src/context/navbar.test.tsx` | the frame's inset follows the pin |
| `interface-core/src/schema/lookup.test.ts` | `firstParam`; `readableTime` in two languages, both styles, unreadable and empty values |
| `pangloss_testing/conformance/test_migration_record_log.py` | the lock's log lines and their logger, on each backend; a backend's record is the kit's |
| `pangloss-cypher/tests/test_no_copies.py` (added to) | a backend does not define what the kit's record has |

Removed, because they tested a loop that is now core's and tested there: `typology/poll.test.ts`,
`users/poll.test.ts`, one test of `admin/jobs.test.ts`.

## Results of the suite

| Run | Before | After |
|---|---|---|
| ruff, ty, the skill's check, the stubs | pass | pass |
| packages on Memgraph | 3386 passed, 171 s | 3390 passed, 166 s |
| conformance on Neo4j | 587 passed, 75 s | 589 passed, 65 s |
| `pangloss-neo4j` | 166 passed | 166 passed |
| live tests of typology, calendar, dates, zotero, rdf on Neo4j | 26, 19, 12, 15, 36 passed | the same |
| browser tests (`e2e/`, the built interface and the dev build) | 226 passed, 507 s | 226 passed, 498 s |
| Vitest, core and application | 490 (56 files; run inside the packages run, the number worked out from the new tests) | 511 passed, 6 skipped as before (63 files: 21 new tests in 7 files) |
| Vitest, each module, in a built workspace | | calendar 25, dates 44, derived 5, history 29, library 2, review 54, typology 47, users 4, admin 3: all pass |
| `pangloss interface check` (types of every module, the layers) | | passes |

**One test failed on the first full run after the changes, and it was right to.**
`test_a_migration_that_is_not_atomic_is_made_in_batches` sets `DEFAULT_BATCH_SIZE` on the backend's
`migration_backend`; `apply` is now the kit's and reads the kit's constant, so the test's setting did nothing. The
test now sets `pangloss_cypher.migrations.record.DEFAULT_BATCH_SIZE`, and the backends no longer pass the name on
(a name that can be set to no effect is a trap). Nothing else read it. The runs in the table are after that fix; the
browser tests were run before it and do not touch it.

The `rdf` and `admin` modules are not in the smoketest project: `admin` was type-checked and tested by copying it
into the workspace; `rdf`'s interface was not changed.

## Not done in this pass

- Nothing was committed.
- The dev build (`pangloss interface dev`) was exercised only by the browser tests' dev-mode run
  (`e2e/test_dev_mode.py`, which passed); I did not click through it by hand.
- No screenshots were compared. The only markup that changed is `class` order on the ✕ icons, `select-none` on nine
  icons, and one `div` inside `main` on `/admin` (so that `data-testid="admin-page"` stays).
