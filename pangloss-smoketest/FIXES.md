# Smoke test: fixes (progress log)

Fixing what `PROBLEMS.md` lists, in order of severity. Started 2026-11-06 on branch `full-smoke-test-fixes`. Nothing
is committed yet. This file is kept up to date as the work goes, so that it can be picked up again: the state of each
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
| 10, 11, 12, 13, 14, 16, 23, 24, 25, 27, 31, 36 and the Design items | | Not started |

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

- **Servers**: the smoke test API on :8010, started with `/tmp/pgstubs/restart_api.sh` (the Zotero watcher off:
  `ZOTERO_LIBRARIES='[]'`; log in `smoke_scripts/out/api_fixes.log`). Containers as in `REPORT.md` §8.
  The interface dev server (`../.venv/bin/pangloss interface dev --api-url http://localhost:8010 --port 3010`, from
  `pangloss-smoketest/`) is **not running**: start it when a page has to be looked at.
- **Scratch** (may be gone): `/tmp/pgstubs/` (`sdk_debug.py` runs `sdk build` keeping ty's whole output).
- **Data made in the smoke database by the checks**: a few `Commodity` entities labelled "Longword ..." and
  "Wordlen ..." (the long-word probes); `sdk_client.py` deletes what it makes; about 4,000 more ordinary factoids
  (the write measurements) and a dozen "Scaling N" factoids of up to 1,000 statements.
- **The demo**: its stubs were made again (`demo_app/models.pyi`) and its SDK built (`.pangloss/sdk`, 0.8). Its
  database was not touched.
