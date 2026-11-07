# Smoke test: fixes (progress log)

Fixing what `PROBLEMS.md` lists, in order of severity. Started 2026-11-06 on branch `full-smoke-test-fixes`.
Committed and pushed: `fa58588`, `482a9f8`, `23c9f32` (everything down to "Smaller items"), then `04c58e4` (the
interface: Solid rc.21, `/api` from its own server, the development build's messages) and `0f4594f` (#10, #11, #24,
#31, #16/#25, #13, #36 and the rest). Where a section below says "Not committed yet", it was written before those
two. See "The last full run" for what was tested. This file is kept up to date as the work goes, so that it can be picked up again: the state of each
problem, what was changed, how it was checked, and what is still to do. Numbers (#n) are those of `PROBLEMS.md`.

## State

| # | Problem | State |
|---|---|---|
| 1 | No SDK with `InterfaceMeta` or `pangloss_library` | **Fixed**, tested, proven on a clean client. Docs not written |
| 32 | Stubs do not type-check outside the monorepo | **Fixed** (it blocked #1: the SDK build type-checks its stubs). Docs not written |
| 2 | A long search word is a 500 | **Fixed** on both backends, conformance test |
| 3 | Autocomplete loses entities (1,000 hits) | **Fixed**, conformance test, measured |
| 20 | Derived section crashes past 25 facts | **Fixed** (the cause was not the 25 facts), checked in the browser, docs and skill updated |
| 26, 33 | Writes superlinear in document size | **Fixed** on both backends: 200 statements 134 s -> 0.3 s; conformance test; documented |
| 5, 21 | Calendar: thousands of open-dated documents on every day; 21 MB page | **Fixed** on both backends: month page 21-26 MB -> 0.45 MB, a day 2.2 s -> 0.15 s; tests, browser, docs. **One judgement call to confirm** (unknown dates left out) |
| 29 | Typology: generic DELETE marks a type in use | **Fixed** on both backends (all three parts), tests, checked on the smoke server, docs. **One judgement call to confirm** (same-named siblings refused) |
| 15, 22, 28 | An entity's view inlines every reverse relation | **Fixed** (committed after fa58588): whole read 0.8-1.3 s -> 0.6-0.8 s; limited read 0.32 s; page 5.2 s -> 2.4 s. Both backends, tests, browser, docs. By-date view of everything is on request, still heavy |
| 6 | `Annotated[int, Ge(1)] \| None` refused | **Fixed**, test |
| 7 | `new-project` writes port 7687, which the tests wipe | **Mitigated**: a comment in the template; the tests stop at a database of more than 20,000 nodes. A small project on 7687 is still not protected: for the user to decide |
| 8 | `users create admin` only says "Aborted" | **Fixed**: the username is an argument, as in the other commands; test |
| 9 | Open-ended period refused without naming the setting | **Fixed**: the message names `DATES_OPEN_END_YEAR` / `DATES_EARLIEST_YEAR`; test |
| 34 | Neo4j: log flooded with notifications on a new database | **Fixed**: the "unrecognized" class is off in the driver; test, and checked on a Neo4j |
| 30 | `check-data` floods the terminal with slow-read warnings | **Fixed**: the threshold is raised while it reads many at once; conformance test, both backends |
| 35 | `history baseline` counts nested statements | **Fixed** (the count; conformance test, both backends). Its speed is not changed |
| 10 | Query parameters snake_case only; unknown ones ignored | **Fixed**: either case, on every route; an unknown one is a 422 that lists those the route has. Tests (unit, and live for review and derived); checked on the smoke server |
| 11 | 422 messages for union fields are enormous | **Fixed**: `loc` is the path in what was sent, the union member is in `model` (short), a long `input` is left out: 4,152 -> 1,113 bytes for the same request. Tests; checked on the smoke server |
| 12 | `interface serve` on its own cannot log in | **Fixed**: the interface's server passes `/api` on (`--api-url`, `--no-api-proxy`), and says so when the API is not there. The browser tests all go through it. **A decision taken** (it was open in `docs/interface.md`): to confirm |
| 24 | A running server is not told the database was migrated | **Fixed**: the server looks (every 10 s, before a write, after a failure) and answers 503 "restart the server" once a migration it did not have is applied. Tests; tried on the smoke database |
| 16, 25 | Zotero: a first sync restarts from zero; one failed item and no version is stored | **Fixed**: the version is stored as the sync goes (items in the order of their versions); a failed item holds only itself back and is tried again; a database being migrated postpones the sync. Tests; tried on the real library |
| 13 | `initialise()` takes 11-12 s | **Fixed**: 3.2 s. The schemas made while the models are put together are no longer made; all 1,297 are as they were. Tests |
| 36 | `squashmigrations` does not fold a rename or an added field | **Fixed**: the comparison that decides it took the order of the indexes for a difference (220 -> 218 on the smoke project); one migration named alone works. Tests |
| 23 | Every page is ~256 KB | **Measured, not changed**: 154 KB on the built interface, 30 KB gzipped, 144 KB of it the texts of the language. For the user to decide |
| (user) | The development server's `SSR_BOUNDARY_WATERFALL` and `SERVER_WRITE` | **Fixed**, after raising Solid to rc.21 (which changed neither): both gone, and three more of the kind found and fixed. The browser tests now fail on them |
| (found) | The built interface says "Internal Server Error" for an item that is not there | **Fixed**: `ApiError` is marked safe to show. Tests, browser |
| 31 | `/openapi.json` is 2.5 MB and its first request takes 4.9 s | **Fixed** as far as it goes: it is made in a thread, so the server answers other requests meanwhile (it answered nothing); 104 KB on the wire since gzip. The first asker still waits 4.8 s |
| 27 | Load: one worker, 479 req/s; a person read queues | **Measured again, not changed**: 450 req/s, the same latencies. One Python process is the limit; `pangloss run` has no `--workers`. For the user to decide (background tasks would run in each) |
| 14 and the Design items (17, 18, 19) | | Not started |

**Second run (2026-11-07, branch `more-smoke-test-fixes`):** `PROBLEMS.md` #37-45.

| # | Problem | State |
|---|---|---|
| 37 | `initialise()` crashes (`AttributeError: Create`) on an embedded model with a relation under a `FieldBinding` | **Fixed**: the embedded model's class is made when first asked for; test; the smoke models initialise with `engraved_by: Person` |
| 38, 39 | Deep documents: "Maximum call stack size exceeded" in the browser; one request hangs the production server | **Fixed**: a block five deep starts folded, view and form, and what is in it is made when it is unfolded; the 61-deep factoid opens in 0.15-0.3 s on both builds, unfolds to the bottom (13 unfolds, 30-120 ms each), no errors, no hang; Vitest; `?show=` opens the way to its part |
| 40 | Nested documents squashed to one character a line | **Fixed** (as far as 61 levels): the rows of fields measure themselves by what they are in (container queries): under 28rem the name goes above the field and the indents shrink; under 24rem the indents all but vanish, and a floor of 14rem keeps the fields readable, each level stepping out of the one above (a staircase the page scrolls for). Seen in screenshots at 61 deep |
| 41 | Reading a deep document is quadratic in its depth (`convert_from_database` re-walks each subtree) | **Fixed** (the time): the converter walks once and marks what it has done; 61 deep 1,020 ms -> 73 ms, 1.13 M converter calls -> 13,400. The size (every nested `meta.semanticSpaces`) is not changed |
| 42 | Adding a subclass to a wrapped type is "LOSES DATA", 33 KB migration text | **Fixed**: a wrapper is compared by what it holds; the change reads "now also document:Death, semanticSpace:Negative holding Death", safe; test |
| 43 | Page 1 of an abstract class costs in proportion to its size | **Measured, not changed**: 73k statements, count 114 ms (76% the lookup of each node's head), the page 263 ms in all (the rest the sort by id); grouping the lookups by head would gain at most 2.4x on the count. For the user |
| 44 | A list search for text with no letters is slow and finds nothing | **Measured, not changed**: "finds nothing" is right (no Person label has a 1); the time is the text index's: `.*1.*` matches thousands of distinct terms (every year), 65,819 hits in 261 ms, where `.*of.*` is one term, 58,689 hits in 41 ms |
| 45 | `/api/search` for a class only ever nested answers `count: 0` | **Fixed**: a 422 that says what holds it and shows the `$somewhere` search to make; test; the interface's list page does not offer the search form for such a class |

## What was done

### #1 The SDK (High)

The cause was wider than the report said. Five things stopped a build, found one after the other:

1. **`pangloss_interface` in the models.** How a model is shown is not data, so the SDK ignores it:
   - `pangloss-sdk/src/pangloss_sdk/no_interface.py` (new): stand-ins for `InterfaceMeta`, `Collapse`, `Slider`,
     `Colour` that take anything and keep nothing (the real ones, where the interface is installed).
   - `pangloss-sdk-server/.../sources.py`: a shipped module (and its stubs) has `from pangloss_interface import ...`
     pointed at the stand-in; nothing else in the file changes. `closure.py` no longer refuses the import, but refuses
     `import pangloss_interface` and names that are not for models (`NavLink`), saying which.
   - `pangloss-library/.../models.py`: imports the interface optionally (as dates, typology and zotero do);
     `pangloss-interface` is no longer a dependency of `pangloss-library` (a dev dependency; `uv.lock` regenerated).
2. **`pangloss_review.meta` imported `pangloss_users`** at module level (server-only). Now imported inside the one
   function that needs it.
3. **The clean-client check** counted the head models of packages (`ZoteroBacked`, `DateCharacterisation`) as "the
   client has it, the server does not". `check.py` now compares them with the server's too.
4. **The stubs did not type-check** (#32, below).
5. **A typology's types have a label for each interface language**, read from the server's settings, which a client
   does not have (the demo failed on this). New general hook: `pangloss_core.settings.model_settings` (names of
   settings the models are made from) and `model_setting()`; `ClientSettings.MODEL_SETTINGS`; the SDK's manifest
   carries the values (`model_settings`) and `connect()` / `connect_offline()` give them to the client's settings.
   `pangloss-typology` registers `INTERFACE_LANGUAGES` and `DEFAULT_INTERFACE_LANGUAGE`.

Checked: `pangloss sdk build` works in `pangloss-smoketest` and in `pangloss-demo` (0.8). `smoke_scripts/sdk_client.sh`
makes a new environment with only the client side (no interface, FastAPI, database driver), clones the SDK from the
running API, and `sdk_client.py` reads, searches, writes a person and a factoid with a date and a type, reads back and
deletes: all pass. Tests: `pangloss-sdk-server/tests/test_no_interface.py` (new, 10).

**Found, not fixed (a decision):** the SDK's `requires` lists only `pangloss-sdk`, not the add-on packages the models
import (`pangloss-dates`, `-calendar`, `-typology`, `-review`, `-derived`, `-library`, `-zotero`), and those
distributions depend on FastAPI and `pangloss-api`. The client script installs them with `--no-deps`, which works.
A proper answer needs the add-ons' server dependencies to be an extra, or the model parts split out.

### #32 Type stubs

- **Stubs for the packages' own models**: `python -m pangloss_testing.framework_stubs` (new) writes
  `pangloss_dates/{models,julian,gregorian,dateable}.pyi`, `pangloss_calendar/models.pyi`,
  `pangloss_library/models.pyi`, `pangloss_zotero/models.pyi`; `--check` is run by `run_tests.sh`. Ruff leaves them
  alone (`extend-exclude`), ty ignores their unused `type: ignore` comments (`pyproject.toml`).
- **`Typed[RoleTypology]`**: `Typed` is generic for a checker. The entity a typology makes is now an attribute of the
  typology's module (`from app.models import RoleType`), declared in the stub, and `RoleTypology.Type` is typed;
  fields of that type are `list[RoleType.ReferenceSet]`, not `Any`. `Typology.Type` is `ClassVar[Any]` in the base.
- **`Var[Agent]`** (a rule variable of a trait): `search_where.variable_classes` adds a declared class above what a
  relation holds, if everything of that class is something the relation holds.
- **A model called `Order`** clashes with the generated `Order` class (typed `order_by`) inside it: `get`, `list` and
  `search` were untyped. The stub now names the model by an alias in those (`_pg_model_Order`). The demo has one too.
- **A document with `create_directly=False`** has no `save` on its `Create`; the SDK's usage check asserted one.
- `Trait._meta` is a `ClassVar` (a class with a trait and a `_meta` of its own was an error to a checker).
- `typestubs.py`: a model the source has no class for (made at run time by something the module declares) is written
  at the end of the stub (`Stubifier.made_class`).

Checked: `ty check pangloss-smoketest/smoke`: 1,748 diagnostics before, no errors now (223 warnings of unused
`type: ignore` in the generated stub remain). The demo's and the smoke test's stubs were made again.

### #2, #3 Search

- `pangloss-cypher/autocomplete_query.py`, `read_functions.py`: autocomplete passes `SEARCH_HIT_LIMIT` to the text
  index, as the list does.
- Memgraph `dialect.py` (`LONGEST_WORD = 40`) and Neo4j `schema.py` (`LONGEST_WORD = 256`): the pattern of a word is
  cut at the longest word the index keeps. (Measured: Memgraph's index keeps a word of 39 characters and not one of
  40, so a label's word of 40+ characters cannot be found by it at all. Neo4j had the same 500, from Lucene.)
- Conformance tests in `test_autocomplete_live.py` (2 new), passing on both backends.

Measured on the smoke database (337k nodes): `q=Ubiquitous&type=Person` 1 found (was 0), `House of` 1,500 Families
(was 0), `House` 1,500 (was 501), `Codex` 2,500 (was 1,000); 7-70 ms. A single letter (`q=a`, 23,869 people) takes
0.25-0.31 s. A word of 500 characters: 200 with nothing found, on lists and autocomplete.

### #20 Derived section

The report's guess (the "and N more" button of a class with more than 25 facts) was wrong: the section still failed
with the button taken out. The cause is how a module's section was mounted, and how long the page takes to hydrate.

- `interface-core/src/components/ItemSections.tsx` put each module section (a lazy component) in a `Loading` of its
  own. The server renders the section in place. On the super-person's page (7.8 MB, about 4.7 s to hydrate) the page
  re-ran its list of sections while the section's boundary was still waiting to be resumed, and removed the server's
  `<section>` from the document (traced: `reconcileArrays` -> `Element.remove`, at 4.7 s). The boundary was then
  resumed and hydrated the removed nodes: Solid does not walk a node that is not connected, so the `<dl>` it wanted
  was the comment before it (`node.setAttribute is not a function`). On a small page hydration is over before any of
  this, which is why only the super-person showed it.
- **Fix**: no `Loading` round a section; its code is waited for with the page's, as a module's card is (the date
  cards on the same page always hydrated). The `Errored` stays. One interface test waited too little for the new
  timing (`ItemContents.test.tsx`).
- **Price**: where a page is made in the browser (not server-rendered), it shows when the sections' code has arrived.
- The other `Loading`s round lazy module components (`incomingViews` in `ItemContents`, console actions, new-item
  parts) were left: an incoming view is only chosen in the browser, and the others are in small parts of the page.
  The trap is in the skill (`references/interface.md`) and in `docs/interface-modules-implementation.md`.

Checked: the super-person's page in the dev interface, logged in: the "Derived" section is there with its two "and N
more" buttons, no console errors (`/tmp/pgstubs/derived_probe.py`); an ordinary person's page has no errors;
`npm test` in the interface's `js` (330 pass) and `npm run typecheck`. **Not checked**: the production build
(`pangloss interface serve`), e2e. No e2e test was written: it needs a page slow enough to hydrate.

### #26, #33 Writing a large document

Measured first (`smoke_scripts/write_phases.py`, new): all of the time was the database running **one statement with a
clause for every node and edge** (160 statements: 2,985 clauses, 26.9 s in Memgraph; validating and building the query
took 10 ms). The database's time for a statement grows about with the cube of its length, on both backends.

- `pangloss-cypher/render_write.py` rewritten: a write plan is now **a few statements, each over a list of rows**
  (`UNWIND $rows`), run in order in the same transaction by `write_functions.run_statements`: the head; one `MERGE`
  over the nodes of the document (their labels a list in each row: `Dialect.labels_from`, new, the one place the two
  databases differ); new entities and URLs if any; one statement over the edges, with a `FOREACH` for each pair of
  edge names the write has (neither database takes the type of an edge from a row in a form both accept). Three
  statements for an ordinary document; their texts do not depend on the size. Each answers how many rows it wrote,
  and fewer than it was given stops the write.
- `build_update_query.py`, `write_functions.py` (create and update both use it). The plan (`write_plan.py`) and all
  the checks are unchanged.
- First tried: a statement for each set of labels and each pair of edge names (17 for an ordinary factoid). As fast
  for large documents, but a round trip each; given up for the three-statement form.

Measured on the smoke database, through the API (`scaling.py`, `large_update.py` (new), `ingest_factoids.py`):

| One factoid of | Before | Now |
|---|---|---|
| 10 Deaths | 58 ms | 47 ms |
| 40 | 527 ms | 75 ms |
| 80 | 3,681 ms | 152 ms |
| 200 mixed | 134,537 ms | 289 ms |
| 200, update dropping 50 | 59,000 ms | 276 ms |
| 1,000 | - | 1.1-1.5 s (update dropping 250: 1.0 s) |

Ordinary factoids are as before or a little better: one at a time p50 23-24 ms (was 23); eight at once 58-62 a second,
p50 121-129 ms (was 53 a second, 124 ms). Neo4j, in the database alone: 160 statements 51-54 ms (was 49-52 s, and one
try in three a 500), 1,000 in 0.42 s. (Figures taken while another test run was going were slower and are not used.)

Checked: the conformance suite, 529 on Memgraph and 529 on Neo4j; a new conformance test
(`test_update.py`, a register of 400 entries written, read in order, updated to 200: about a second, and it fails over
30 s); `test_create.py`'s test of the query text now says the texts are the same for a document of any size.
Documented in `docs/large-data.md` ("Writing a large document"), `docs/memgraph.md`, `docs/overview.md`,
`docs/database-abstraction-plan.md` and the skill.

**Left**: for 1,000 statements the time is now validation (0.5 s) and reading back (1 s), not the write. The report's
#14 (writes of ~500 ms while another writer is busy) is a different thing (the text index at commit) and not touched.

### #5, #21 Calendar

Measured before, on the smoke database (`/api/calendar/...`, March 1500):

- A day: 5,829 hits, 2.1 MB, 2.2 s. 5,673 of them state a range of a century or more. By kind (all date fields):
  **7,084 are a plain `UnknownDate`** (a statement whose date is "not known": it ran from the first year to the last,
  and was marked `stated` on every day), about 900 are periods with an open or unknown end, 120 recurrences.
- A month: the same 5,680 as `spanning` (drawn as bars: the 21 MB page), 93 `roughly`, no day had a hit of its own.
- Every view asked the database once **for each date field of each class** (some 60 queries here): that was the 1-2 s.

What changed (`packages/pangloss-calendar`):

1. **A date that is only "unknown" is not on the calendar** (`graph.NOT_UNKNOWN`). It says nothing of when. A period
   or a range with one unknown end still is: it says when it started, or ended. **This is my judgement and changes
   what the calendar shows: for the user to confirm.** (To undo it, take `NOT_UNKNOWN` out of `graph._dated`; the
   unknown dates would then be among the covering periods only if they were periods, which they are not, so they
   would be back on every day.)
2. **A long period that covers all of what a page shows** (it starts before the first day and ends after the last, and
   states `CALENDAR_LONG_DAYS` days or more, 366 by default: `graph.COVERS`, `settings.long_days`) is not listed on
   the day or drawn across the month. The day's and the month's answers have how many there are (`covering`), and
   they are read a page at a time from the new `GET /api/calendar/covering?first=&last=&page=&page_size=`
   (`graph.covering_between`, `service.covering`, `CoveringReport`; 50 a page, at most 500). A long period that starts
   or ends in what is shown, and a short one that covers it, are shown as before. The year and the list of years count
   without the covering periods.
3. **One query for all the date fields** (`graph.dated_between(fields, ...)`: the `Class.field` names are a
   parameter) instead of one for each.
4. **Interface** (the module in `pangloss_calendar/interface/`): new `Covering.tsx`, used by `DayView.tsx` and
   `MonthPage.tsx` (`MonthFoot`): "Long periods that include this day (33)" / "Long periods over the whole month (33)"
   with a **Show them** button that reads the first page, then "and N more"; each row is the field, a `ReferenceChip`
   and the days stated. Nothing is asked of the API until the button is pressed. `api.ts` has `getCovering`; four new
   slots in `translations/ui.jsonc` (en, de, fr).

The user's idea was to stream results into the loaded page. With the long periods out of the page there was nothing
left to stream: the server-rendered pages are now small. The covering periods are the part that "streams" (on
request). If a project has thousands of dates that begin or end in one month, the month would grow again: not seen
here, and `MONTH_LIMIT` (20,000) with `truncated` is still the only bound on that.

Measured after, same database:

| | Before | Now |
|---|---|---|
| `GET /calendar/day/...` | 1.1-2.2 s, 2.1 MB, 5,829 hits | 0.13-0.15 s, 55 KB, 149 hits + `covering: 33` |
| `GET /calendar/month/...` | 1.9 MB, 5,680 spanning | 0.12 s, 38 KB, 0 spanning, 93 roughly, `covering: 33` |
| `GET /calendar/year/...` | 1.4 s | 0.06 s |
| `GET /calendar/years/...` | - | 0.75-1.05 s |
| `GET /calendar/covering` | - | 0.03-0.04 s |
| Month page (HTML) | 21-26 MB, did not render | 451 KB, 0.2 s; in the browser 443 KB of DOM |
| Day page (DOM) | 12 MB | 551 KB |

(The 33 are the periods that are left once the 7,084 unknown dates are out: the "5,673 of a century or more" were
nearly all unknown dates.)

Checked:

- `uv run pytest packages/pangloss-calendar`: 60 passed on Memgraph; the live tests on Neo4j
  (`PANGLOSS_TEST_BACKEND=neo4j uv run pytest packages/pangloss-calendar/tests/live`): 19 passed. Three new tests in
  `tests/live/test_calendar_service_live.py`: an unknown date is in no view (and a period with an unknown end is);
  long covering periods are counted, paged, ordered, read by the route, and governed by `CALENDAR_LONG_DAYS`; a day is
  one query for all fields.
- The module's Vitest (25 passed, two new in `DayView.test.tsx`) and `tsc`, run in the smoke project's workspace.
- In a browser on the dev build of the smoke project (`/tmp/pgstubs/calendar_browser.py`): month and day load, the
  section shows 33, the button reads them, no console or page error.
- e2e: the `dated` fixture has a reign from 1490 to 1510; new
  `test_calendar.py::test_long_periods_over_a_day_or_a_month_are_counted_and_shown_when_asked_for`, and a step in
  `test_dev_mode.py::test_the_calendar`. `uv run pytest e2e/test_calendar.py
  e2e/test_dev_mode.py::test_the_calendar`: 13 passed (the built interface and the dev build).
- Docs: `docs/api.md` (the rows and the new route), `docs/calendar-implementation.md` (fifth round, as built),
  `guide/calendar/README.md` (`CALENDAR_LONG_DAYS`, reading, the pages), `docs/status.md`, `e2e/COVERAGE.md`.

### #29 Typology

Three things in the one item.

1. **The entity's own `DELETE /api/OccupationType/{id}` marked a type in use for deletion** (as it does any entity
   that is referred to) and left it in the tree, on 620 people and in every search. The typology's rule is to refuse.
   - New general hook, so the core still knows nothing of typologies: `Protection(delete_refused=...)`
     (`pangloss_models/protection.py`), an async function of the model and the id that gives the reason the model
     cannot be deleted, or `None`. The API asks it before a delete (409 with the reason, nothing changed) and in
     `/deletable` (`pangloss_api/routes/models.py`). `protection_of` keeps the nearest one of a class's parents.
   - The typology gives its types one (`typology.delete_refused` -> new `service.why_not_deletable`, which
     `service.delete` now uses too, so there is one rule).
   - The interface needed nothing: its Delete dialog asks `/deletable` and shows the reason.
   - Python is not stopped, as for the rest of `Protection`: `RoleType.delete(id)` is the plain delete,
     `RoleTypology.delete(id)` the rule.
2. **A second root type called "Merchant" was accepted.** `service.create`, `service.update` (a new label) and
   `service.move` now refuse a type of the same name (ignoring case) beside the others below one supertype, or at the
   top level (`service.check_no_namesake`). `load` already took the label under a supertype for the type. The same
   name under different supertypes is allowed. **My judgement; for the user to confirm.** Not checked: a type written
   as a plain entity (`POST /api/OccupationType`, `Type.Create(...).save()`), and `merge` (how two that exist are
   made one).
3. **The CLI only took the entity's name.** (The report says the API took `OccupationTypology`: it did not, it was a
   404.) Both now take either name: `Typology.named(name)`, used by `api.py` and `cli.py`; the 404 lists what is known.

Checked:

- `packages/pangloss-api/tests/test_protection.py`: new test of the hook (409, nothing deleted, `/deletable`, a
  subclass keeps it); 5 passed.
- `packages/pangloss-typology`: three new live tests (the entity's delete refuses and marks nothing, a free leaf is
  deleted; namesakes; either name): 57 passed on Memgraph, the 26 live tests on Neo4j.
- On the smoke server (`smoke_scripts/typology_delete.py`): `DELETE` of Merchant -> 409 "Merchant has subtypes
  (Banker, Cloth merchant, ...)", still not marked; of Banker -> 409 "Banker is in use by ... and 615 more"; a second
  root Merchant -> 409; `/api/typology/OccupationTypology/tree` -> 200; `pangloss typology tree OccupationTypology`
  prints the tree.
- Docs: `docs/api.md`, `docs/meta-slots.md`, `docs/typology-implementation.md`, `guide/typology/README.md`, the
  skill's `references/modelling.md` (the slot's row).

Left as the smoke test made them, in the smoke database: Banker is still `markedForDeletion: true`, and there are
two root types called Merchant (merge them with `OccupationTypology.merge`).

Also found while checking: `uv run ty check` had two errors in `packages/` from the earlier fixes
(`pangloss_sdk_server/typecheck.py`, a test of `Typed[int]`) and failed on the smoke project (three loose driver calls
in `smoke_scripts/`, 231 unused `type: ignore` in its generated stubs). Fixed the first two; the others have
overrides in `pyproject.toml`. `uv run ty check` now passes.

### #15, #22, #28 An entity that thousands of documents refer to

Committed after `fa58588` (the commit "Smoke test fixes: an entity that thousands of documents refer to").

Measured before (the "super-person", 3,927 references in 83 fields; `smoke_scripts/read_phases.py`): finding the
6,799 reverse rows takes 14 ms; reading the properties of every node of every chain 480 ms; who made each 160 ms;
and 2,863 of the rows were thrown away in Python afterwards (a narrowed relation is stored under both names).

What changed:

- **The query** (`pangloss-cypher/read_query.py`, `build_fetch_incoming_query(cls, id, allowed, *, field, skip,
  limit)`): it works out each row's field name itself, keeps only what the models show
  (`read_incoming.shown_relations`), sorts by the label of what refers, counts each field, and cuts each field
  **before** reading any properties. `read_incoming.fetch_incoming_relations` returns `(items by field, counts)`.
- **Storage operations for the API** (like `check_deletable`: not bound to the models, not in the SDK):
  `get_entity_with_some(cls, id, incoming_limit)` -> `(HeadView, counts)`;
  `get_incoming(cls, id, field, skip, limit)` -> `IncomingPage`. `Entity.get` still returns everything (as the user
  said: the API for API use can return large documents), faster, and its incoming fields are now in label order.
- **API** (`pangloss-api/routes/models.py`): `GET /api/NAME/{id}?incoming_limit=N` (adds `incomingCounts`) and
  `GET /api/NAME/{id}/incoming/{field}?page=&page_size=` (one more read route for each entity class; an entity named
  by a URL keeps its own query string).
- **Interface** (`interface-core`): `getItem(..., {incomingLimit})`, `getIncoming`, `INCOMING_SHOWN = 25`,
  `INCOMING_PAGE = 100` (`api/fetch.ts`); the app's `itemQuery` asks with the limit; `ItemContents.tsx` has
  `MoreIncoming` ("and N more" after a row, reads the next hundred) and `ReadAllIncoming` (above a module's view of
  the references, such as by date: "N more refer to this and are not read yet", **Read them all**). Three new slots
  in `translations/ui.jsonc` (en, de, fr). The modules needed no change.

Numbers (smoke database, the super-person):

| | Before | Now |
|---|---|---|
| `GET /api/Person/{id}`, whole (1.86 MB) | 0.8-1.3 s | 0.6-0.8 s |
| `?incoming_limit=25` (0.99 MB) | - | 0.32 s |
| `?incoming_limit=10` (0.42 MB) | - | 0.19 s |
| `/incoming/{field}`, 50 items | - | 0.06 s |
| The page, dev build (#22) | 5.2 s, 29,507 elements, 105,716 px | 2.4 s, 16,045 elements, 61,050 px |
| The page with 10 of each (not the default) | - | 1.25 s, 7,339 elements, 30,072 px |
| By date (#28) | 3.5 s, 47,069 elements, on choosing it | 2.2 s and 25,413 elements with what the page has; **Read them all**: 5.3 s (78 requests), then 47,791 elements |

**For the user to decide:** 25 or 10 of each field (25 keeps a typical entity whole; 10 halves the heavy page
again). And #28 is only half fixed: the by-date view of everything is as heavy as it was, now on request; making it
light needs the view itself to page or to draw only what is on screen (not done).

Checked:

- Conformance: `test_read_incoming_paged.py` (4 tests) and a new test in `test_api_models.py`, on Memgraph and
  Neo4j; the whole conformance suite on Memgraph after the query change (530 passed); `pangloss-api` (166).
- Interface: `npm test` (333 passed, 3 new in `ItemContents.test.tsx`), `npm run typecheck`, `check:layers`.
- e2e: new `test_lists_and_items.py::test_an_entity_that_much_refers_to_...` (30 statements and 27 dated
  appointments: the rows, the button, the by-date notice); it and `test_dateable.py` pass (15).
- In a browser on the smoke project's dev build (`/tmp/pgstubs/super_browser.py`): the numbers above, a row read
  from 25 to 40, no console or page error.
- Docs: `docs/api.md`, `docs/large-data.md` (new section with the measurements), `docs/interface.md`,
  `e2e/COVERAGE.md`, the skill (`references/architecture.md`).

`./run_tests.sh` in full passed after it (2026-11-06, exit 0): all packages on Memgraph (2,839); on Neo4j the
conformance suite (535), `pangloss-neo4j` (165) and the add-ons' live tests (72); e2e (166).

### Smaller items (#6, #7, #8, #9, #30, #34, #35)

Done after the commit `482a9f8`, and committed together ("Smoke test fixes: smaller items"). `./run_tests.sh` in full
(2026-11-06): every test stage passed (Memgraph 2,846; Neo4j conformance 537, `pangloss-neo4j` 166, add-on live tests
72; e2e 166), and the stub check failed, rightly: `pangloss_dates/models.py` had changed (#9) and its shipped stub had
not been written again. Written again (`uv run python -m pangloss_testing.framework_stubs`); the stub check, ruff, `ty`,
the dates tests and the SDK builder's tests pass after it. The full script was not run a second time.

- **#6** `Annotated[int, Ge(1)] | None`: `initialise_field_definitions.with_optional_lifted` reads it as
  `Annotated[int | None, Ge(1)]` (pydantic keeps the constraint with the member of the union, where the definitions
  did not look). Also a `Field(ge=1, description=...)` in the `Annotated`, and `DBField`. Test in
  `pangloss-models/tests/initialisation/test_initialise_field_definitions.py`; `pangloss-models` 938 passed.
- **#8** `pangloss users create [USERNAME]`: the username is taken as an argument (as `set-password`, `make-admin`
  and the rest take it) or `--username`; what is missing is asked for in the function, in order (an option that
  prompts does so before click refuses an unexpected argument: hence "Username: Aborted."). Test in
  `pangloss-cli/tests/test_users_commands.py`; `docs/cli.md`. (Emails at `.test` are still refused: that is the
  email validator's rule for special-use domains, left alone.)
- **#9** A period (or a range) that starts after `DATES_OPEN_END_YEAR` with an end that is ongoing or unknown now
  says: "it starts after 1600, and an end that is not known or has not come is taken to be by the end of that year
  (the setting DATES_OPEN_END_YEAR): set DATES_OPEN_END_YEAR to a later year"; the same for an unknown start before
  `DATES_EARLIEST_YEAR`. `pangloss_dates/models.py` `_spanning`. Test in `test_dates_models.py`; the dates package
  212 passed; `guide/dates/README.md`.
- **#34** `Neo4jDialect.driver_options` also disables the `UNRECOGNIZED` class of notifications (label, type or
  property that no data has yet). Checked against a Neo4j: a query naming an unknown label and property gets two
  notifications with a plain driver, none with Pangloss's options. Test `test_neo4j_driver_options.py`;
  `docs/neo4j-implementation.md`.
- **#7** The template's settings now say, at the port, that Pangloss's own tests empty the database on 7687. And
  the tests refuse to run (exit 3) against a database with more than 20,000 nodes
  (`pangloss_testing.live.refuse_to_empty_real_data`, used by the live fixtures and by e2e's wipe;
  `PANGLOSS_TEST_WIPE=1` goes ahead). This would have protected the smoke database (337,000 nodes) but **not a
  small project**: telling a small project from test leftovers needs a marker the tests leave, or the tests on a
  port of their own. Both change how the test database is used: for the user to decide. Tests:
  `pangloss-testing/tests/test_testing_wipe_guard.py`.

- **#30** `check-data` (and the read-back of `migrate`) reads sixteen items at once, so each read waits for the
  others and takes hundreds of milliseconds: a Cypher backend warned of nearly every one. For the length of the
  check the backend's slow threshold is 10 s (`pangloss_models.migrations.check.reading_many_at_once`, which sets
  `Database.slow_query_threshold` if the backend has one, as a bulk load does), and is put back after. Conformance
  test in `test_migration_dry_run.py`, on both backends.
- **#35** `pangloss history baseline` took the documents inside others for head nodes (`getattr(item,
  "is_head_node", True)` looked on the item, and the flag is in its `meta`): the dry run's "19191 would be recorded"
  were the statements of the factoids, and a real run would have written a record for each.
  `pangloss_history/baseline.py` `is_head`. Conformance test in `test_history_baseline.py`, on both backends.
  **Not changed: its speed** (6 minutes for 93,000). It reads every head node to learn its version, as a list does
  not give one: making it fast needs the version in the list, or one query for all the versions.

### The rest of Low (#10, #11, #12)

Not committed yet (after `23c9f32`).

- **#10 Query parameters.** `pangloss_api/query.py` (new):
  - `QueryNames`, a middleware added last (so outermost, outside what the installed apps add): the names of the
    query string are put in snake_case before the request is routed; a value is never changed, and a query string
    with no capital in a name is passed on as the very same bytes.
  - `known_parameters`, a dependency of every route of the app: a parameter that is not among those the route and
    its dependencies declare is a 422 in FastAPI's own shape (`type: unknown_parameter`, `loc: ["query", name]`,
    and a message that lists the names the route has).
  - An entity read at one of its URLs (`GET /api/Person/http://example.com/people?id=5`) keeps its query string as
    it is: it is the URL's (a path with `/http:/` or `/https:/` in it is neither renamed nor checked).
  - For a route that reads parameters it does not declare: `@checks_own_parameters` and
    `refuse_unknown_parameters(request, also=...)`, both exported from `pangloss_api`. `pangloss-derived`'s list of
    facts uses them (a field of the class as a parameter). `pangloss-review`'s middleware, which reads
    `review_status` on a write, now takes the parameter out of the query string (and reads it in either case).
  - Tests: `pangloss-api/tests/test_query_parameters.py` (new, 4); `test_review_live.py` (conformance:
    `?reviewStatus=checked` on a POST, and an unknown one refused); `test_derived_api_live.py` (a misspelt field
    refused with both kinds of name listed; `ruleType`, `pageSize`).
  - On the smoke server: `?pageSize=3` gives 3; `?pageSize=501` is a 422 ("less than or equal to 500");
    `?pagesize=3` is a 422 that lists `deep, page, page_size, published, q, review_status`.
- **#11 What a 422 says.** `pangloss_api/validation.py` (new), registered with the other error handlers:
  - The long name was the tag of the member of a union, which Pydantic puts in `loc` after the field; a generic
    class's name is every type it takes. The handler follows `loc` through the body that was sent: a part that is
    a key (or an index) stays, a part that is a union member (`pangloss_models...tagged_union.is_tag`, or the name
    of a model) and not a key there is taken out, and the last one is given as `model`, with the types of a
    generic left out (`Causes[…]Create`).
  - `input` is left out when it is more than 200 characters as JSON (a missing field's input is the whole object
    it is missing from); "Unable to extract tag using discriminator choose()" is now "Input should be an object, of
    one of the types that are allowed here".
  - **Found on the way:** the interface puts a server's problem on a field by its `loc`, and its filter did not
    know tags like `DeathCreate`, so a 422 never marked the field of a statement. With a clean `loc` it does.
  - Tests: `pangloss-api/tests/test_validation_errors.py` (new, 4). On the smoke server the request of the report
    (a `Death` with nothing in it and a `Causes` with a list for `cause`) is 1,113 bytes, was 4,152.
- **#12 The production interface on its own.** `interface-app/serve.mjs` passes `/api` on to the API (Node's
  `http`, no new dependency): the browser's headers with its `Host`, `X-Forwarded-For` added, the answer piped back
  as it comes (so a stream of events stays one), not compressed again; if the browser goes away the request to the
  API is dropped. `pangloss interface serve --api-url URL` (or `PANGLOSS_API_URL`, as before) says where the API
  is, for the pass-through and for the pages rendered on the server; `--no-api-proxy` for a deployment whose
  reverse proxy does it. If the API is not there: 502 with a `detail` that says where it was looked for and how to
  say where it is; the interface shows "The interface cannot reach the API. If you run this site: ..." (a new
  slot, `error_api_unreachable`, en/de/fr) in place of "Not Found" or "Something went wrong".
  - Checked in the smoke project: `pangloss interface build`, `pangloss interface serve --api-url
    http://localhost:8010 --port 3011`, and in a browser the login dialog logs in and `/Person` lists
    (`/tmp/pgstubs/serve_browser.py`); with `--api-url` at a port nothing listens on, the dialog shows the new
    message; with `--no-api-proxy`, `/api/Person` is a 502 that says so.
  - `e2e/conftest.py`: the Python proxy that stood in front of the interface is gone; the suite uses the built
    interface's own pass-through, so all of it tests this path.
  - Docs: `docs/interface.md` (Architecture; the decision is struck from "Decisions to make next"),
    `guide/interface/README.md` (Deploying), `TODO.md`, `e2e/COVERAGE.md`, the skill.
  - **To confirm:** that the interface's server passing `/api` on is the wanted answer to the open decision. A
    reverse proxy that does it instead is still possible (`--no-api-proxy`).

### #24 A server that is running when the database is migrated (Perf list, but a 500)

Not committed yet.

- `pangloss_api/migration_watch.py` (new). `MigrationWatch` remembers which migrations were applied when the server
  started (and which migration files its code had), and reads the record again (`migration_backend.applied()`, on
  either backend) every `MIGRATION_WATCH_SECONDS` (new setting, 10), before a write and after a request that
  failed, if the last look is more than a second old. A migration applied that the code did not have, or one
  taken back, and from then on `MigrationGate` (a middleware, inside CORS) answers every request for `/api` with a
  503 whose `detail` names the migration and says to restart the server; logged once as an error. A request that
  fails with an unhandled error looks first, so the read of a document the models no longer fit is that 503 and
  not a 500 (`ServerErrorResponder`).
- Not a change: a migration the server's code already had (pending at a start with `MIGRATION_CHECK = "warn"`); a
  migration that is still running (writes are refused by its lock, as before; reads go on). Nothing is watched
  with `MIGRATION_CHECK = "off"`.
- Tests: `pangloss-api/tests/test_migration_check.py` (4 new: a write looks first and is refused, then everything
  is; a failing read is a 503; back and forward; the loop on its own, and off).
- On the smoke database: `makemigrations --empty smoke`, `migrate` beside the running server; six seconds after it
  was done the server answered 503 with "smoke.0003_watch_probe applied ... Restart the server". Undone after
  (`migrate smoke 0002`, the file removed, the server restarted).
- Docs: `docs/migrations.md` (with the start-up check), `docs/settings.md`, `docs/api.md` (503), `docs/logging.md`,
  `guide/migrations/01-ideas.md` and `08-troubleshooting.md`, the skill.
- **Not done:** the server does not restart itself; the interface shows its general "Something went wrong on the
  server" for the 503 (the reason is in the response and the server's log). The SDK raises `PanglossReadOnlyError`
  with the message (its error for a 503).

### #16, #25 The Zotero sync

Not committed yet.

- `pangloss_zotero/sync.py`, `sync_library`:
  - The stored version means "everything up to here is written". Deletions are dealt with first; then the items
    in the order of their versions, and after a batch (not more often than `CHECKPOINT_SECONDS`, 30) the version
    just below the next item's is stored. A sync that stops goes on from there.
  - An item that fails is in `report.errors`; the others are written; the stored version stays just below it
    (`stored_version`). `Progress` (new) is what a process keeps between its syncs of a library: how far it read
    and the items (and deletions) to try again, so that its next sync asks only for what is new and for them.
  - `PanglossReadOnlyError` (a migration is running) is not an item's fault: the sync stops with `SyncPostponed`
    (a `ZoteroError`, so the watcher's delay and retry apply), and nothing is counted as failed.
- `watch.py`: the watcher keeps a `Progress` for each library, and after a sync with items that failed tries
  again by itself (10 s, doubling to an hour), where it used to wait for Zotero to say something.
- `cli.py`: `zotero status` says "first sync not finished" where a version is stored and no sync has ended.
- Tests: `test_zotero_sync.py` (9 new: stopping part way and going on; items of one version not split; a failed
  item with and without `Progress`; one Zotero no longer has; postponed; a failed deletion; `stored_version`),
  `test_zotero_watch.py` (2 new). The package: 93 passed (with its live tests on Memgraph).
- On the real library (`groups/2556736`, 16,006 versions), in a scratch project with only users and Zotero on the
  test Memgraph (:7687, emptied after): `zotero sync` stopped after 100 s had written 1,060 items and `status
  --remote` said "version 6883 of 16006 (behind), first sync not finished"; run again for 50 s it went on (1,488
  items, version 8108).
- Docs: `docs/zotero.md` (Sync), `guide/zotero/README.md`.
- **Not changed:** the speed of a first sync (about 12 items a second here: Zotero's answers with citations and
  bibliography are most of it). The failed items are remembered in the process, not in the database: a new
  process finds them again by starting below them, at the cost of reading what came after once more.

### Found on the way: the built interface said "Internal Server Error" for an item that is not there

Not in `PROBLEMS.md`: the smoke test could not use the built interface (#12), so it did not see it. Not committed
yet.

- `GET /Person/<an id that is not there>` on `pangloss interface serve` rendered "Internal Server Error" where
  the development server says "Page not found" (following a link inside the application was right: only the page
  as the server renders it was wrong). Solid's built server puts a bare `Error("Internal Server Error")` in place
  of any error that is not marked safe to show, before the page's own error boundary sees it; so every
  `error instanceof ApiError` on the server was false.
- `interface-core/src/api/client.ts`: an `ApiError` is what the API answered this reader, so it is marked
  (`markSafeError`, from `@solidjs/web`). What then arrives in the browser is a plain `Error` with `name`, `status`,
  `detail` and `body`; `ApiError` takes such a value for one of its own (`Symbol.hasInstance`), so the 22 places
  that ask `instanceof ApiError` are right after hydration too.
- Tests: `fetch.test.ts` (new test; `interface-core` 334 passed); e2e
  `test_an_item_that_is_not_there_is_explained` now asks for the heading and the text, in the page as the server
  renders it (it asked only for an alert, which the wrong message also was). Checked in a browser on the smoke
  project's built interface.

### #23 The size of a page (measured; not changed)

On the built interface (which #12 made usable): an empty page is 154 KB, 30 KB gzipped (`/` 163 KB / 30 KB;
`/Person` 216 KB / 36 KB). 144 KB of it is one script: the texts of the language (the interface's own and the
labels of this project's 96 classes and their fields), which the server puts in every page so that the browser has
them when it takes the page over. The page itself is 7 KB. Since the gzip change the cost on the wire is the 30 KB.
To take it out of the page, the texts would be a file of their own that the browser keeps (one request, then
cached), read before the page is taken over: a change to how translations are loaded, **not made**. For the user
to decide whether 30 KB a page is worth it.

### #13 `initialise()` (Perf)

Not committed yet.

- Profiled on the smoke project: 6,237 schemas made for 1,512 generated classes, 4,562 `model_rebuild` calls. A
  class was rebuilt each time it was given fields, and at the end every schema was forgotten and made again
  anyway (so that classes that refer to each other get a recursive schema).
- `pangloss_models/model_bases/model_tools.py`: `rebuild(model)` in place of `model.model_rebuild(force=True)` in
  the code that makes the generated models, and `rebuilds_put_off()`, inside which a rebuild is only noted.
  `ModelRegistry._initialise_models` works inside it, and then forgets and rebuilds, once, the classes made for
  the models and whatever else was noted (the search patterns among them: one that kept its schema would be
  embedded as it was). Outside that phase `rebuild` rebuilds at once, as before.
- Measured: `initialise()` 11.3-12.1 s -> 3.2 s; `pangloss zotero status` 17 s -> 5.1 s. The JSON schemas of all
  1,297 classes with a schema are the same before and after (`/tmp/pgstubs/init_deferred.py`, comparing them with
  the order of union members put aside, see next).
- **Found with it:** the members of the union of an embedded field (`start: ExactDate | DateRange | ...`) were in
  the order of a set, which differs from one process to the next: 745 of the 1,297 schemas differed between two
  runs of the same code. `builder.embedded_annotation` now sorts them, as a relation's are.
- Tests: `pangloss-models` 938 passed (the snapshot of the generated models among them).

### #36 `squashmigrations`

Not committed yet.

- The run from an app's first migration is replaced by the changes from the models before to the models after,
  if applying those gives the same state. That comparison was of a state as the changes left it with one put in
  order (`data_view`): with an index from another app already there, the indexes were in another order, the two
  were "different", and every change was kept. `pangloss_models/migrations/files.py`: both sides in order. On the
  smoke project: "220 changes in 2 migrations -> 218 changes" (the rename and the added field are in the creates).
- `pangloss squashmigrations APP NAME` with one migration named is the run from the app's first up to it (it said
  only "Missing argument 'last'").
- Tests: `test_migration_squash.py` (new; it fails without the fix), `test_migrations_cli.py`.

### Reported by the user: what the development server logged (`SSR_BOUNDARY_WATERFALL`, `SERVER_WRITE`)

Not committed yet. The whole account, with the table of what was found, is in `docs/interface-refactoring.md`
("2026-11-06: rc.21, and what the development server said").

- **Solid raised first, as asked**: `solid-js` and `@solidjs/web` 2.0.0-rc.19 -> rc.21, `@solidjs/router`
  next.43 -> next.44, `@solidjs/vite-plugin` next.52 -> next.56, in `interface-core`, `interface-app` and the eight
  modules' `package.json`, and `js/package-lock.json`. The plugin renamed an option (`start: { nodeServer: true }`).
  Type check, layer check, 334 unit tests and the build pass. **It changed neither diagnostic**: both were there
  on rc.21 as on rc.19 (checked by putting rc.19 back in the smoke project's copy).
- **`SSR_BOUNDARY_WATERFALL`** (`pages/Item.tsx`): the code the modules add to an item's page was asked for only
  once the item had come. `useModules().preloadItemPage(type)` (new, `context/modules.tsx`) starts it with the
  request for the item.
- **`SERVER_WRITE`** (`pages/Item.tsx`, `Track`): a cleanup that clears the console's item ran on the server, which
  discards each pass. Registered in the browser only.
- **Three more, found by clicking through 18 pages and following links, logged in:** a value read once without
  `untrack` (`pages/Edit.tsx`); **hydration warnings on every list page** (the options of the menu that adds an
  order were not taken over by the browser: an `<option>` whose text is a child expression, followed by a `<For>`;
  fixed here and in five other places of the same shape); every row of that menu made again on each choice (keyed
  by value now).
- After: the smoke project's development server says nothing through the same clicks, and the browser has no
  warning (`/tmp/pgstubs/click_around.py`, `diag_pages.sh`).
- **So that it stays so:** the browser tests' development server fixture fails if its log has any such diagnostic
  when the tests are done (`e2e/conftest.py`, `development_warnings`).
- **Its first run found three more**, in the tests' own project: a second set of retype buttons made and thrown
  away on the form of a document with documents inside (a prop that is elements, read twice:
  `form/ModelFields.tsx`, `Block`); an untracked read where a view of what refers to an item is shown
  (`ItemContents.tsx`); and the waterfall again, on an item page with two components of modules. The first two are
  fixed.
- **The waterfall is fixed in part.** The code the modules add is now asked for with the item (also the cards of
  models that have their own). What is left is the development server's: Solid waits one pass for the assets of
  each lazily loaded component it renders, and does not count that as work already started, so a page with two or
  more of them still says "3 sequential async waits" the first time, in development only (found by logging what
  each pass waited for; the built server looks assets up at once). The check knows this one
  (`KNOWN_IN_DEVELOPMENT`). It could be reported to Solid: the lookup's promise is not stamped when the module is
  already loaded.
- **For the user:** the demo's linked development server on :3000 runs from the package's `js/`, whose
  `node_modules` now has rc.21: restart it.

### #31 `/openapi.json`

Not committed yet.

- FastAPI makes the document in the coroutine of the first request for it: 4.9 s here in which the server answered
  nothing. `pangloss_api/openapi.py` (new): its route is put behind one that has the document made in a thread,
  once (those who ask meanwhile wait for the one), and then kept as before.
- On the smoke server: the first request 4.78 s, during which 32 other requests were answered (the slowest 0.43 s);
  the second 0.02 s; 2.68 MB, 104 KB on the wire with gzip.
- Tests: `pangloss-api/tests/test_openapi_route.py` (new, 2). `docs/api.md`.
- Not changed: the time it takes to make (pydantic's JSON schemas of 1,014 models).
- Later (2026-11-06, fbb87a0): `/docs` is RapiDoc (`add_rapidoc` in `pangloss_api/openapi.py`, a page that
  loads rapidoc@12.0.0 from unpkg; FastAPI's `docs_url=None`; `/redoc` unchanged). Swagger UI had not listed 50 of
  the 840 operations after 180 s; RapiDoc lists them all in 0.5 s (document already made) and opens `POST
  /api/Factoid`, with its example and schema, in 1.8 s; no page errors. Test: the first in `test_openapi_route.py`.

### #27 Load (measured again)

`smoke_scripts/load_test.py 32 20` after everything above: 450 requests a second (479 in the report); get person
119/145 ms p50/p95 (113/139), list search 50/65 (47/63), autocomplete 38/51 (35/49), structured search 42/58
(38/51). Unchanged: the limit is one Python process at full use. `pangloss run` starts one worker and has no
option for more; with more, each would run the background tasks (the Zotero watcher, the derived worker, the
migration watch), which is why it is left: for the user to decide. (#14, writes of ~500 ms while another writer is
busy, is the same kind: the cost of the text index for each commit, see `docs/large-data.md`.)

### Going back to an earlier migration (from the Design list)

Not committed yet. `pangloss migrate APP EARLIER` reads the affected models back with the code's models, which
still have what was undone, so it lists what they cannot read (421 factoids in the smoke test), rightly, and that
read as damage. It now says first: "The code is ahead of the database now (it still has smoke.0002_...): what its
models cannot read below is expected, until the code is at the same migration or the database is migrated forward
again". `pangloss_cli/migrations.py`; asserted in `test_migrations_cli.py`.

### #19 Searching by a type and its subtypes (Design: looked at, nothing built)

The report tried a field `supertype`, which there is not: the hierarchy is the types' field `is_subtype_of`, and a
structured search follows it today, a level at a time (`smoke_scripts`-style check in
`/tmp/pgstubs/subtype_search.py`): `has_type is Merchant` 595 people; `has_type` a type whose `is_subtype_of` is
Merchant 2,965; the two and the level below together (`$any_of`) 3,506. What is missing is one operator for "this
type or any below it" (the guide calls it `$under`, under "Not yet"). `guide/typology/README.md` now shows the
search that works. **For the user:** whether to build the operator.

### The last full run (2026-11-06, with everything above in; committed after it as `04c58e4` and `0f4594f`)

`./run_tests.sh`: ruff, `ty`, the skill check and the packages' stubs pass; packages on Memgraph 2,871 passed and
1 failed; on Neo4j the conformance suite 537, `pangloss-neo4j` 166, the live tests of typology 26, calendar 19,
dates 12 and Zotero 15; the browser tests 166 passed, on Solid rc.21, with the development server's log checked.
The one failure was `test_dev_link_runs_the_package_source_with_the_projects_models`: it looked at whether the
checkout's own `node_modules` was up to date (it was not marked so, the packages having been installed by hand
after the versions were raised) and saw an install it did not expect. The test no longer depends on that; it and
the rest of `pangloss-interface` and `pangloss-cli` pass (286), as do ruff and `ty`, after the last two small
changes (that test, and the message of going back). The whole script was not run again after those.

**Left, in the order of `PROBLEMS.md`:** #14 (writes while another writer is busy: the text index's cost for each
commit) and #27 (one worker) are measured and not changed; #23 is measured (30 KB a page gzipped) and left for a
decision; the Design items #17 and #18 are not looked at, #19 has a search that works and no new operator; #7,
#28 and #35 are fixed in part, as before.

**For the user to decide or do** (all in the sections above): restart the demo's linked development server on
:3000 (its `node_modules` is on rc.21 now); the production interface passing `/api` on itself (#12); the two
earlier judgement calls (unknown dates out of the calendar; no two types of one name side by side); 25 or 10
reverse relations for each field on an entity's page; a small project on port 7687 (#7); several workers for the
API (#27); an operator for "this type or any below it" (#19); whether the texts of the language should leave the
page (#23).

### #37 An embedded model with a relation, reached through a binding (High)

- **Cause.** The models are made in the order of their direct dependencies (`ModelRegistry._toposort`). `Order`
  depends on `PositiveSubjunctive[Statement]`, not on `Statement`'s subclasses; but giving `Order.Create` its
  `thing_ordered` with its `FieldBinding` builds a bound `Create` of every concrete `Statement`, `SealedLetter`
  among them, and that asks `embedded_annotation` for `Seal.Create`, which did not exist yet (`Seal` waited on
  `Person`, which waited on `WithCertainty[str]`; by name `Order` came first). Without a relation in the embedded
  chain the embedded models were made early enough by chance. So: an embedded model reached, through an abstract
  class, by a model whose name sorts before it.
- **Fix.** `embedded_annotation` (`pangloss_models/initialise_models/builder.py`) makes the embedded model's class
  for the kind if it is not there yet (`initialise_model`, as `entity_types` already does for an entity that may
  be named inline), and the main loop gives it its fields in its turn. The schemas are all forgotten and made again
  at the end of `_initialise_models` anyway, so the early, fieldless one is not kept.
- **Test.** `pangloss-models/tests/generated_models/test_embedded_reached_through_a_binding.py` (the abstract class
  is called `Act` so that it sorts before `Seal` in the test module, which is what shows the bug; failed before,
  passes after). All 940 model tests pass.
- **Checked** on the smoke models with `engraved_by: Person` restored: `initialise()` is fine. The smoke models
  keep `engraved_by: str` (the comment says why: the data holds strings, and a migration to a relation would lose
  them).

### #41 Reading a deeply nested document (Perf)

- **Cause.** Every model made from database data (`_FromDatabaseBase`, the head's `meta`) has a `mode="before"`
  validator that calls `pangloss_models.hooks.convert_from_database`, and the one converter registered
  (`pangloss_cypher.from_database.convert_neo4j_datetimes`) walked everything it was given. So each nested model
  converted its whole subtree again: O(nodes x depth). Measured with the models directly on the smoke database
  (`/tmp/pgfix/measure41.py`, median of five `Factoid.get`): 61 deep 1,020 ms and 1,132,862 converter calls;
  21 deep 437 ms; 13 deep 38 ms.
- **Fix.** `convert_from_database` (`pangloss_models/hooks.py`) does the walk itself, once: dicts become a marked
  dict (`_Converted`), lists are walked, and the converters are given the values. A marked dict is returned as it
  is, so the nested models' validators cost nothing. The contract of the hook changed accordingly: a converter is
  given a value, not the tree (the one converter works as before: its own recursion is never reached). With no
  converter registered (the SDK) nothing is walked, as before.
- **After:** 61 deep 73 ms (13,400 calls), 21 deep 38 ms, 13 deep 26 ms: linear now, and about what the query
  takes.
- **Tests.** `test_from_database_hook.py`: a converter is given each value once, however deep, and what has been
  through is not walked again. All 941 model tests pass; the database-backed packages (Memgraph) run below.
- **Not changed:** the size of the response (each nested document's `meta.semanticSpaces` lists every space above
  it, which is what the data holds), and the query, which the report found was not where the time went.

### #38, #39, #40 Deeply nested documents in the interface (High, High, Medium)

- **Cause of #38/#39.** Solid makes a component tree synchronously, hundreds of frames for each nested document
  (more in the development build), so a chain of 41-61 documents overran the call stack in the browser, and on
  the server the render of the edit page of the 61-deep factoid kept `serve.mjs` busy for minutes.
- **Fix.** `interface-core/src/components/nesting.ts` (new): a context counting how many blocks (a document inside
  a document, a reified relation, a conjunction) a thing is inside. A block five deep starts folded
  (`startsFolded`: `FOLD_FROM` 5, then every `FOLD_EVERY` 5 levels of what is unfolded), in the view
  (`ItemContents.tsx`: the head bar of such a block is the toggle, as in the form; a ▸ before the label while it is
  folded) and in the form (`ModelFields.tsx`, `Block`, whose fold already existed). What is folded is not made at
  all (`<Show>` round the children), so what is made at once is bounded; unfolding starts from the click, a new
  stack. The server renders the same five levels. `?show=<id>` of the edit page (the edit button of a nested
  document) still reaches its block: `ItemForm` takes `show`, and a block that holds that id starts open
  (`RevealProvider`, `holdsId`); `Edit.tsx` passes it.
- **#40.** The grid of fields (`fieldGridClass`, `fieldRowClass` in `form/styles.ts`) is a Tailwind container
  query of the thing it is nested in (`nestedClass` and the item's contents and the form are `@container`):
  under 28rem the name goes above the field (one column) and the indent and the bands' padding shrink
  (`@max-md:`); under 24rem the indent all but vanishes (`@max-sm:ml-0 pl-1`, the rules down the left still show
  the depth, as the bars of a quoted letter do) and the fields keep a floor of 14rem (`@max-sm:min-w-56`), so each
  further level steps out of the one above by a few pixels: a staircase the page scrolls sideways for, instead of
  text one character wide. Head chips, labels and space labels tighten in the same tier.
- **Measured** on the smoke project, production build (`smoke_scripts/ui_nested.py`, and `ui_unfold.py`, new,
  which unfolds to the bottom): the 13, 21, 41 and 61-deep factoids open in 0.06-0.27 s (view) and
  0.08-0.20 s (edit), 334 / 625 elements, no errors, the server unmoved (before: 61 deep view "message only",
  edit hung the server four minutes). Unfolding the 61-deep one to the bottom: 13 unfolds of 18-44 ms (view,
  2,412 elements) and 34-120 ms (edit, 9,298 elements); the page 1,678 / 1,690 px wide (viewport 1,400; before the
  floor 2,446 / 2,550, with text one character wide). The development build: the same pages, no errors and no
  diagnostics in its log, unfolds of 58-334 ms (view) and 111-1,286 ms (edit). Screenshots in
  `smoke_scripts/out/ui_nested_c6b10e*.png`.
- **Tests.** Vitest: `ItemContents.test.tsx` (folds at five, unfolds five more, folds again; the containers),
  `ItemForm.test.tsx` (the same in the form; `show` opens the way). All 340 interface tests pass. The e2e project
  has no deep nesting: `e2e/COVERAGE.md` says so.
- **Not changed:** a part deeper than five levels that a review comment points at is in a folded block until it is
  unfolded (the item page has no `?show=`); the blocks' depth is counted from the page, so a document opened on
  its own starts fresh.

### #42 A kind added to what a wrapper holds (Low)

- **Cause.** `diff_relation` (`pangloss_models/migrations/diff.py`) compared a relation's options by `option_key`,
  which for a wrapper (`Causes[TCause=document:Accusation|...]`) spells out everything it holds; so three kinds of
  statement added made every wrapper that takes a statement an option removed and another added: "lossy", with a
  text naming every kind (33 KB).
- **Fix.** `options_difference`: a wrapper that is in both (by `option_base`, the wrapper without its parameters)
  is compared by what it holds (`option_leaves`): what it now also holds is an addition
  ("semanticSpace:Negative holding Death"), what it no longer holds a removal. The change applied to the
  database is unchanged (`alter_relation_target` uses `removed` only as a yes or no, and the labels of the
  options as they are now). Test: `test_a_kind_added_to_what_a_wrapper_holds_is_an_addition_not_a_removal`
  (both ways). All 30 diff tests pass.

### #43 Page 1 of an abstract class (Perf: measured, not changed)

- Logged in, on 73,093 statements: `GET /api/Statement?pageSize=5` 267 ms; `DatedStatement` (25,712) 117 ms;
  `Factoid` (30,783) 46 ms; `Person` (56,001) 60 ms. The count alone (the first half of `_plain_page`,
  `list_query.py`) is 114 ms; profiled, 76% of it is the lookup of each node's head by id (`ScanAllByLabelProperties
  (counted_head :HeadNode {id})`, 148,020 hits), which the rule of what is seen needs for a nested node (its
  head's `deleted` and `published`). The other 150 ms is the second scan with the sort by id for the page.
  Entities and head documents have no head to look up, so their pages are cheaper for the same count.
- Not changed: grouping the nested nodes by head before the lookup would cut the count by at most the number of
  statements for each factoid (2.4 here); the sort stays. `/tmp/pgfix/profile43.py`. For the user: whether it is
  worth it.

### #44 A list search for a digit (Perf: measured, not changed)

- `GET /api/Person?q=1` 271 ms and 0 results; `q=Lorenzo` 36 ms, 493; `q=1500` 12 ms, 0; `q=' OR 1=1 --` 477 ms
  (its words are `or`, `1`, `1`), 0 and `truncated: true`.
- "Finds nothing" is right: no Person label has a `1` in it (`CONTAINS '1'`: 0). The time is the text index's:
  the pattern `.*1.*` matches thousands of distinct terms (every year in a label: 65,819 hits in 261 ms), each
  with its postings to merge, where `.*of.*` is one term (58,689 hits in 41 ms) and `.*15.*` 5,847 in 12 ms. It is
  the known cost of a substring search on the index (docs/deep-search.md), not a scan of the nodes. Not changed.

### #45 `/api/search` for a class that is only ever inside another (Low)

- `resolve_search_type` (`pangloss_models/search.py`) now refuses a document class that can never be a document
  of its own (`create_directly` false for it and every class below it, `can_be_a_head`) with a
  `PanglossSearchError`, a 422 at the API: "A Letter is never a document of its own (create_directly is False),
  so a search for it finds nothing: it is inside Factoid.statements, Order.thing_ordered, Report.reported.
  Search the document that holds it, with $somewhere: {"type": "Factoid", "where": {"$somewhere": {"type":
  "Letter", ...}}}" (`holders_of`: the fields of the documents whose options hold the class or one above or below
  it, wrappers such as `Hearsay[Statement]` left out; the example starts from a holder that can be a head).
  Checked on the smoke API for Letter, Statement and Meeting.
- Test: `test_a_type_that_is_never_a_document_of_its_own_says_what_holds_it` (`test_search_match.py`).
- The interface's list page offered the search form for such a class too (its structured search went to the same
  route, and found nothing): it no longer does, see below. **For the user:** whether the search should instead
  find such documents through the ones that hold them (a change of the decision "results are head documents",
  docs/structured-search.md).

### The full run after the second run's fixes (2026-11-07, uncommitted)

`./run_tests.sh`, exit 0: ruff, `ty`, the skill check and the packages' stubs pass; the packages on Memgraph 2,876
passed; on Neo4j the conformance suite 537, `pangloss-neo4j` 166, the live tests of typology 26, calendar 19,
dates 12 and Zotero 15; the browser tests 166 passed (the development server's log checked). Not committed: for
the user to review.

## Still to do for what is fixed

- **Docs: written** (2026-11-06): `docs/sdk.md` ("As built: phase 8": the stand-in, model settings, the check, the
  packages' stubs), `guide/sdk/01-server.md`, `docs/cli.md` (stubs), `docs/autocomplete.md` and `docs/memgraph.md`
  (the hit limit; long words), `docs/typology-implementation.md`, `TODO.md` (the demo's SDK item closed; an item for
  what is open), the skill (`references/architecture.md`: `no_interface`, `model_settings`, `framework_stubs`).
- **`./run_tests.sh` in full**: passed on 2026-11-06 with everything above in (exit 0): ruff, `ty`, the skill check,
  the packages' stubs; all packages on Memgraph (2,834); on Neo4j the conformance suite (530), `pangloss-neo4j`
  (165) and the live tests of typology (26), calendar (19), dates (12) and Zotero (15); e2e in a browser (165).
  Committed after it.
- `PROBLEMS.md`: the fixed items are marked (a line at the top, and each item). `REPORT.md` is as the smoke test
  wrote it: add a pointer to this file when the work is done.
- **For the user to decide**: the two judgement calls (calendar: plain unknown dates left out; typology: no two
  types of one name side by side); whether the add-on packages should be installable on a client without
  `--no-deps` (they depend on `pangloss-api`).

## Where things are

- **Servers** (2026-11-07, left running): the smoke test API on :8010 (`ZOTERO_LIBRARIES='[]' ../.venv/bin/pangloss
  run --port 8010` from `pangloss-smoketest/`; log `smoke_scripts/out/api_fixes2.log`); the development interface on
  :3010 (`../.venv/bin/pangloss interface dev --api-url http://localhost:8010 --port 3010`; log `interface_dev-7.log`);
  the production interface on :3011 (`pangloss interface build`, then `pangloss interface serve --api-url
  http://localhost:8010 --port 3011`; log `interface_serve-7.log`). Containers as in `REPORT.md` §8. Stop a server
  by the process on its port.
- **Scratch of the second run's fixes**: `/tmp/pgfix/` (`measure41.py`, `profile43.py`, `time_lists.py`,
  `repro37.py`; may be gone).
- **Scratch** (may be gone): `/tmp/pgstubs/` (`sdk_debug.py` runs `sdk build` keeping ty's whole output).
- **Data made in the smoke database by the checks**: a few `Commodity` entities labelled "Longword ..." and
  "Wordlen ..." (the long-word probes); `sdk_client.py` deletes what it makes; about 4,000 more ordinary factoids
  (the write measurements) and a dozen "Scaling N" factoids of up to 1,000 statements.
- **The demo**: its stubs were made again (`demo_app/models.pyi`) and its SDK built (`.pangloss/sdk`, 0.8). Its
  database was not touched.
