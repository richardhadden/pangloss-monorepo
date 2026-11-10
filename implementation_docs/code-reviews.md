# Code reviews and refactorings

Four passes over the code, condensed: what each found, what was done, the decisions and traps that still matter,
and **what is still open**. The full reports (with the probes, the line numbers of the time and every table) are in
the history of the repository, before 2026-11-10: `docs/code-review-2026-10-31.md`, `docs/code-review-2026-11-10.md`,
`docs/initialise-models-cleanup.md` and `docs/interface-refactoring.md`.

| When | What |
|---|---|
| [2026-11-10](#2026-11-10-redundancy-branch-code-review-3-) | Redundancy: code written several times, components drawn several times |
| [2026-11-02](#2026-11-02-the-interface-against-solid-20-idioms-) | The interface against Solid 2.0 as it is meant to be written; the release candidate's traps |
| [2026-10-31](#2026-10-31-pangloss-core-and-pangloss-memgraph-branch-code-review-2-) | `pangloss-core` and `pangloss-memgraph`: bugs, tests that did not test, the copied backends |
| [2026-10-22](#2026-10-22-initialise_models-one-builder-for-the-generated-models-) | `initialise_models`: five copied builders made one |

## Still open

| What | Where | Why it is open |
|---|---|---|
| `ensure_user` is an autouse fixture | `packages/pangloss-memgraph/tests/conftest.py` | Every test of the package, pure unit tests included, needs Memgraph and runs in the serial `db` group |
| `reasonOf(error)`: "the API's own words, or the error's" | 7 interface modules, the same three lines | Core's `useErrorText()` says more (its own words for 401, 403, 5xx), so using it changes what a person reads when a write is refused: the user's call. A plain `errorReason` in core would change nothing |
| `run_connected(ctx, fn)`: initialise the models, connect, run, disconnect | 5 add-on CLIs (calendar, zotero, typology, review, derived); by hand in admin, rdf, history | The add-ons do not import `pangloss_cli`. Its home would be a function in `pangloss-core`: a new public name, so ask first |
| The heading of a page (`h1` with a hairline under it) | 8 pages, one class string | A `PageHeading` in core; do it with the chunking fix (see [the cost of a shared file](#the-cost-of-a-shared-file)) |
| `<Errored><Loading fallback="Loading…">` round a page's contents | about a dozen pages | Could be part of `PageFrame`, but it moves the boundaries, which on the server is behaviour: needs its own careful pass |
| The type chip in the calendar's month grid is drawn by hand (0.6 rem) | `MonthGrid.tsx` | Not a `ReferenceChip`, which the rule asks for everywhere. Either `ReferenceChip` gets a `size` or this is a said exception: a decision about the look |
| The tab of a semantic space, drawn twice | `Console.tsx` (`Wrapped`), `SpaceBands.tsx` (`SpaceTabs`) | Merging risks the half-pixel faults that took time to get right; needs screenshots at each depth |
| `SearchPanel.tsx` and `ModelFields.tsx` are each over 1,300 lines | core | Each is one lazy chunk on purpose. `SearchPanel`'s rows could move to files beside it at no cost |
| The backends' `cli.py`, `backend.py`, `initialise_database.py`, `setup.py` are largely the same | `pangloss-memgraph`, `pangloss-neo4j` | The next thing to move into `pangloss-cypher`. The CLI wants a factory in the kit, as a change of its own |
| `databases/api` and `databases/api_sync` | `pangloss-sdk` | The async and the sync client, the same but for `await`; generating one from the other is the only cure |
| `pangloss-smoketest/.pangloss/interface/` is tracked by git (322 files) | | It is the generated copy every command writes over. It should be ignored and removed from the index |
| Small repeats left on purpose | fold buttons in `Head.tsx`; the storage listener in `clipboard.tsx` and `stash.tsx`; helpers of the conformance tests | Low value; a third user would justify sharing |

`colourTint`, `isRelation`, `useModel` (core) and `CALENDARS` (calendar) are exported and used by nothing here: they
are public names for modules and projects, not dead code.

## 2026-11-10: redundancy (branch `code-review-3`) ✅

Looked for code written more than once and for parts of the interface that could be one component, with `jscpd`,
`vulture`, a scan for unused exports and a reading of the largest files. The whole suite passed before and after.

| Change | Was |
|---|---|
| The record of migrations (`open_session`, `applied`, `lock`, `record`, `apply`, `unapply`, `dry_run`, …) is `pangloss_cypher/migrations/record.py`; each backend keeps its constraints, and Memgraph its snapshots. The logger is still the backend's | 300 lines the same in each backend |
| `pause` and `pollChanges` (`interface-core/src/api/poll.ts`); `createRequestApiClient` and `serverApiUrl` (`requestClient.ts`). Review keeps its own `pollReview`, whose rule (a 404 ends the feed) is review's | 4 poll loops, 5 hand-made clients |
| `createFeedReader(open, api)` and `createInBrowser()` (`primitives/liveFeed.ts`) | 4 and 3 copies |
| `PageFrame`, the `main` of a page (in `context/navbar.tsx`) | 8 copies |
| `Pager`. Its text is four slots of core (`pager_pages`, `pager_previous`, `pager_next`, `pager_page`): a project that overrode `review_queue_next` or `users_next` must rename the key | 2 copies |
| `CloseIcon`, with a `size` that sets the stroke (in `primitives/icons.tsx`, with `Spinner`) | 7 copies |
| `readableTime` and `firstParam` (`schema/lookup.ts`) | 6 and 5 copies |
| Every icon has `select-none` | 9 did not |
| `ModelRegistry.finalise(allow_cycles=)` and `bases_for(embedded_base=)` removed | passed by nothing |

`tests/test_no_copies.py` in `pangloss-cypher` compares whole modules, which is why a half-shared file was not seen;
it now also fails if a backend defines a function the kit's record has. A trap found: a test set
`DEFAULT_BATCH_SIZE` on the backend's module, which after the move did nothing; the backends no longer pass that
name on (a name that can be set to no effect is a trap).

### Measured

On the built interface of `pangloss-smoketest` (56,000 people), in Chromium, before and after, the median of five
loads on 16 pages:

- **Times did not change**: every difference was inside what one build gives from run to run.
- All the client's JavaScript: 1,253,954 → 1,250,794 bytes (gzip 330,487 → 329,309), in 112 files as before.
- One request fewer on the list, item, edit and new-item pages; one more, and about 1 kB more, on `/review` and a
  user's page (`Pager`); about 0.5 kB more on the home page, the calendar and the history page.

### The cost of a shared file

As the build stands (the Solid plugin makes every `lazy()` target an entry, and Rolldown puts each module that the
frame and a lazy entry share in a chunk of its own), **a new shared file is a new request**, and a very small file
hardly compresses. So a new shared helper goes into a file every page already fetches (`icons.tsx`,
`schema/lookup.ts`, `context/navbar.tsx`), unless only a few pages use it (`Pager`). The measured fix for the
chunking (grouping the frame's modules: 6 requests a page instead of 44) would remove this cost; it is not applied.

## 2026-11-02: the interface against Solid 2.0 idioms ✅

A review of `interface-core`, `interface-app` and the modules against the `solidjs-v2` skill and the v2 docs.
Sixteen findings; all done but two that were tried and put back. Raised to rc.21 on 2026-11-06.

The rules it was checked against (they are the rules for new code):

1. **Derive, do not relay.** A signal written from an effect that reads other state is a copy one flush late. Use a
   memo, a function, or a writable derivation (`createSignal(() => props.value)`).
2. **Ask again with `refresh(source)`**, not a counter a memo reads only to depend on it.
3. **A mutation is an `action`**: `yield` the request, then `yield refresh(source)`; catch a failure in the generator
   and put it in state. A busy flag is `createOptimistic(false)`.
4. **The DOM after a write: `flush()`, then read.** Not `setTimeout` or `queueMicrotask`.
5. **Effects are for what Solid does not own** (the document, storage, a library). A measuring effect is a
   `createRenderEffect`.
6. **`Show` narrows with a function child**, not `when={x()}` and then `x()!`.
7. **A read in a component's body is a one-time capture**: say so with `untrack`.

Kept as they are, on purpose (do not "fix" them):

| Where | What looks wrong | Why it stays |
|---|---|---|
| `pages/Item.tsx`, `Track` | An effect relays the item into a signal, for the console outside the boundaries | A console inside the boundaries was tried: when `Errored` goes to its fallback the content's portal stays, so an item gone after logging out left its console in the bar |
| `TypeMenu.tsx`, `TypeChooser` | `setTimeout` to open the box | With `flush()` the box is drawn during the click that opens it, and the same click then counts as outside it and closes it |
| `List.tsx`, `Results` | Pages fetched from an effect; a row measured in a `queueMicrotask` | The rows on show are a fact of the window; a memo for each page would put a `Loading` round every row. A ref runs before the element is in the document |
| `Edit.tsx`, `ScrollToNested` | `requestAnimationFrame` after `onSettled` | The scroll needs the layout |
| `RequireLogin.tsx` | An effect opens the login dialog | A command to the app's dialog, not a copy of state |
| `Problems.tsx`, `useSaveChecks` | `untrack` round the apply of an effect | Without it the development build warns `STRICT_READ_UNTRACKED` |
| Storage read in `onSettled` (`navbar`, `translations`, `clipboard`, saved searches) | | So that the first render in the browser is the server's |

Traps of the release candidate, found on the development server (2026-11-06):

- **An `<option>` whose text is a child expression, followed by a `<For>` of options**, hydrates wrongly (the browser
  counts the expression among the children, the server does not). Write the text as a property:
  `<option value="" textContent={label} />`.
- **A prop that is elements, read twice**, makes the elements twice. Read it once: `children(() => props.buttons)`.
- **A function child of `<Show>` that reads `chosen().component` in its body** warns; use `<Dynamic>`.
- **`onCleanup` runs on the server** for each pass of a boundary: one that writes a signal must be registered in the
  browser only (`isServer`).
- A `<For>` over objects made anew each time needs `keyed`.
- The built server replaces an error not marked safe with "Internal Server Error" before the page's `Errored` sees
  it: `ApiError` is marked (`markSafeError`).
- The item page still says `SSR_BOUNDARY_WATERFALL` on the development server when two or more `lazy` components
  are rendered: that is the development server's own (`useModules().preloadItemPage(type)` starts the imports with
  the request).

The browser tests fail on any warning of the development build (`e2e/conftest.py`, `development_warnings`), except
those listed in `KNOWN_IN_DEVELOPMENT`.

## 2026-10-31: `pangloss-core` and `pangloss-memgraph` (branch `code-review-2`) ✅

Read all of core and the main modules of the Memgraph backend, ran the tests, ruff, `ty`, `vulture`, a scan for
tests with no assertion, and probe tests against the test database. Every finding but one was closed by 2026-11-01.

| # | Finding | What was done |
|---|---|---|
| 1 | The JSON log format did not redact secrets in double quotes (it redacted after `json.dumps` had escaped them) | Redacts before dumping; a redacted value keeps its quotes |
| 2 | A list search put the user's words into a regex: `(` was a 500, `.` matched everything | Uses `search_words`, as autocomplete does |
| 3 | A `Settings(...)` that failed validation replaced the global `SETTINGS` with a broken object | Assigned only once valid |
| 4 | `test_lock` passed with the lock removed (its writers conflicted anyway) | Rewritten with writes to different nodes |
| 5 | `exposed_functions` bound to `Database.default` when imported, so import order mattered | Resolved by the database refactor ([database-abstraction.md](database-abstraction.md)) |
| 6 | The two backends were about 3,000 identical lines | `pangloss-cypher` (the same refactor) |
| 7 | The visibility `WHERE` was pasted 8 times; the join to the creation record differed between list branches | One helper, one behaviour (the refactor) |
| 8 | Dead code and leftovers | Deleted |
| 9 | Fixtures cleared the database only on teardown; a persistent `/tmp` volume; a typo in a setting's name | Fixed, **except `ensure_user` autouse** (open, above) |
| 10 | Tests with no assertion, or that checked less than their names said | Given assertions or deleted |
| 11 | `pytest-asyncio` as a runtime dependency; 18 files unformatted; bugbear not run | Fixed; `ruff format --check` and `ruff check --select F,B` are in `run_tests.sh` |

Worth knowing still:

- The coverage floor (`fail_under` in the root `pyproject.toml`) measures `pangloss_models` only.
- The bulk-load commands are tested in a subprocess, so coverage cannot see them: tested, not measured.
- `ty` passes on the query-building code with many rules turned off there, so it says little about it.

## 2026-10-22: `initialise_models`, one builder for the generated models ✅

`pangloss_models/initialise_models/` makes `Create`, `CreateDB`, `Update`, `UpdateDB`, `View` and the rest for every
declared model. Five of its parts were the same code five times, it wrote to pydantic's `model_fields` in 65 places,
and it had bugs that followed from the copying.

| | Before | After |
|---|---|---|
| The five builders | 5 modules, 2,907 lines | `builder.py` (one implementation), `kinds.py` (what differs, as data: a `ModelKind` each), `common.py`, five short entry points |
| Known bugs | 14 | 0 |
| `model_fields` written directly | 65 places | one function (`set_field`) |
| Line coverage of the module | 79% | 93% |

How it was done, which is the way to change this code again:

- **A snapshot of everything `initialise()` makes** for a "kitchen sink" of models of every kind
  (`test_generated_models_snapshot.py`, `kitchen_sink.py`, `snapshots/generated_models.json`). The old code's output
  was the baseline, and the new builder made the same bytes. `UPDATE_SNAPSHOTS=1` writes a new one: do that only on
  purpose, and read the difference.
- **Each known bug was first a strict `xfail` test.**
- `test_cross_kind_properties.py` gives every kitchen-sink model samples and checks what must hold between the five
  models (nothing given is lost, the same fields, a round trip through the aliases). It found four more bugs.
- Differences between the kinds that look accidental are kept, as fields marked `quirk:` in `kinds.py`.

Decisions that stand (2026-10-22 and 23):

- **The edge model of `ViaEdge[InRole[Person], Weight]` is the relation to the wrapper only**, not passed down to
  the wrapper's targets. A wrapper that wants properties on its own relations declares them.
- **A class that `Fulfils` another is both only if it holds every field of it**, whatever their kind: fulfilment
  makes literals, embedded objects and annotated values nullable too, not only relations.
- In `Update`, what a wrapper holds of its own is offered as `Update` and `Create`, as everywhere else (it used to be
  always read as new).
- **Bindings do not fill a wrapper's own fields** in any kind (they reach the documents it holds). Left, pinned by
  `test_bindings_reach_what_a_generic_holds_but_not_its_own_fields`; changing it would be a feature.
- Optional literals in `CreateDB` and `UpdateDB` are `X | None`. The database models carry no field descriptions.
  Union order is a convention (`Create` first in the database models; reference first for clients), and
  `test_union_order.py` would catch a change that made it matter.
- Reserved field names: `id`, `type`, `meta`, `urls`, `create_new`, `db_labels`, `context_labels`,
  `semantic_spaces`, `edge_properties`. `label` is not reserved.

Measured, so as not to try again:

- **Sharing the models made for a generic** (`InRole[Person]` used twice makes two sets of classes) saves 7 to 14%
  of `initialise()` and changes nothing in the OpenAPI schema (pydantic merges the duplicates). Not worth what it
  changes.
- **`initialise()` is mostly pydantic's `model_rebuild`.** Since 2026-11-06 a class is rebuilt once, at the end
  (`model_tools.rebuild` only notes it while the models are put together): on 96 classes (1,512 generated) 4,562
  rebuilds became 1,663 and `initialise()` went from 11.3 s to 3.2 s. Measuring under `tracemalloc` slows this
  code about four times.

Not done: the old type-checker ignore comments outside `builder.py` have not been pruned, and
`build_relation_options` (`initialise_field_definitions.py`) is as it was.
