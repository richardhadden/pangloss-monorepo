# Smoke test: problems found (running log)

Written as the smoke test goes (started 2026-11-06 00:32). The full report is `REPORT.md` at the end. Each item says
what was done, what happened, and how sure I am. Severity: **High** (blocks a feature), **Medium** (wrong result or
a 500 a user can hit), **Low** (rough edge, confusing message), **Perf** (slow or heavy), **Design** (works as
documented, but questionable).

Setup: Memgraph `pangloss-memgraph-smoketest` on :7697, API on :8010, interface on :3010. 26 entity classes + 2
typologies, 68 concrete statement kinds. Data at the end: 49,910 entities + 15,570 Zotero items (the real group
library, synced), 8,795 factoids, 337,423 nodes / 825,815 edges. Item numbers are in the order found, grouped by
severity.

**Fixed since (2026-11-06, branch `full-smoke-test-fixes`; what was changed and how it was checked is in
`FIXES.md`):** 1, 2, 3, 5, 6, 7 (in part), 8, 9, 10, 11, 12, 13, 15, 16, 20, 21, 22, 24, 25, 26, 31 (in part), 28 (in part), 29, 30, 32, 33, 34, 35 (the count, not the speed), 36, and what the user reported at the end. Each is marked below. The text of an item is as it was found.

## Second run (2026-11-07, 10:32-11:13): deeper models, twice the data

On `full-smoke-test-fixes` (everything in `FIXES.md` in). New in `smoke/models.py` (migration `0003_deep_nesting`):
`Report` (an undated statement whose `reported` is a `Hearsay[Statement]` space, so reports of reports of orders of
orders nest without limit), `Witnessing` (`witnesses: list[Attributed[InRole[Identification[WeightedAlternative[
Person]]]]]`: four reified relations deep) and `SealedLetter` (`seal: Seal`, `Seal > SealImpression > SealMatrix`:
three embedded levels). The data was doubled: a second run of `ingest_entities.py` (`SMOKE_RUN=2`: other names and
URL ids, typologies and vocabularies reused) and 15,000 more factoids, which now include the new kinds (954 reports,
1 to 4 deep with an order chain of 2 to 4 at the bottom in 40%; 425 witnessings; 431 sealed letters). Now: 115,227
entity nodes (15,570 of them Zotero items), 30,228 factoids, **686,164 nodes** (410,274 before; 337,423 at the first report). Scripts:
`nested_checks.py`, `deep_reads.py`, `deep_updates.py` (all three take `SMOKE_API`/`SMOKE_OUT`/`SMOKE_TOKEN`/
`SMOKE_BOLT` for the Neo4j copy), `ui_nested.py`, `ui_pages.py` (`SMOKE_UI` for the production build on :3011).

37. **High. `initialise()` crashes (`AttributeError: Create`, in `builder.embedded_annotation`) when an `Embedded`
    model with a relation is a field of a document that a `FieldBinding` reaches.** Here: `SealMatrix.engraved_by:
    Person`, in `Seal > SealImpression > SealMatrix`, on `SealedLetter`, a `Statement`; `Order.thing_ordered` binds
    `ordered_to` into every `Statement`, so `build_bound_model` builds a bound `SealedLetter` and asks for
    `Seal.Create` before it exists. The nesting does not matter: a relation directly on `Seal` crashes the same; with
    no relation in the embedded chain (three levels deep) it works. `Order` and `Statement` are in a cycle, and
    `_order_cyclic` puts the cycle before the embedded models that depend on `Person`. The docs allow an embedded
    relation (`Date.about: Person`). Worked round in the smoke models (`engraved_by: str`, a comment points here).
    `makemigrations`, `migrate` and the server all fail to start with it.
38. **High. Deeply nested documents crash the interface: "Maximum call stack size exceeded".** Factoids of a report
    chain (Report > Hearsay > Report ... > Order > PositiveSubjunctive > Order ... > Letter):

    | Documents deep | 2, 4, 8 | 13 | 21 | 41 | 61 |
    |---|---|---|---|---|---|
    | Dev build, view | ok | ok | renders, then the message at the bottom | | |
    | Dev build, edit | ok | **message only** (42 elements) | **message only** | | |
    | Production, view | | ok (704) | ok (965) | ok (1,674) | **message only** (89) |
    | Production, edit | | ok (2,293) | ok (3,590) | **message only** (90) | the server hangs (39) |

    The stack when it fails (Chrome, paused on the exception) is 7,974 frames: each nested document costs hundreds of
    synchronous frames of Solid's component creation (`createComponent` > `createRoot` > `createMemo` > `recompute`,
    and in the dev build `HMRComp`, `observedComponent`, `runAsSolidCopy` too). Nothing is logged: the error boundary
    shows the message and the console and `pageerror` see nothing, so the e2e checks for page errors would not
    catch it. Data that the API takes and returns correctly cannot be opened or edited.
39. **High. One request for a very deep document stops the production interface's server for everyone.** Opening the
    edit page of the 61-deep factoid (logged in) kept `serve.mjs` at 100% CPU for about four minutes, its memory
    growing from 706 to 790 MB; meanwhile it answered nothing, not even `/`. It recovered on its own. Most likely the
    server-side render of the same tree as 38 (not confirmed: I did not ask again, to keep the server up).
40. **Medium. Nested documents are indented once more at each level, so beyond about five levels the content column
    shrinks to one character a line and the content spills out to the right** (the 21-deep view:
    `out/ui_nested_8a542d.png`). Nested spaces each add their own coloured band too.
41. **Perf. Reading a deeply nested document grows with the square of its depth, on both backends.** Median of five
    `GET /api/Factoid/{id}` (Memgraph; Neo4j in brackets): 8 deep 31 ms (19), 21 deep 35 ms (29), 41 deep 120 ms
    (536), 61 deep 1,097 ms (1,166); the edit view the same. The log says `read transaction get_document took
    1076 ms`, but **the query is not most of it**: the query alone takes 88 ms at 61 deep. Profiled
    (`Factoid.get`, 1.0 s): 1.39 s of 1.55 s under the profiler is pydantic validating the result, nearly all in
    `convert_from_database` (`pangloss_models/hooks.py`), called 167 times with 4.5 million `isinstance` calls. It
    is a `mode="before"` validator on every model made from database data (`_FromDatabaseBase.convert_database_types`),
    and the converter walks everything it is given, so each nested model converts its whole subtree again:
    O(nodes x depth). Converting once, at the root, would make it linear. (The query collects a path from the root to
    every node and unwinds every edge of every path, which is also O(nodes x depth); keeping only the last edge of
    each path, `last(relationships(path))`, gives the same 347 edges at 61 deep, but no clear gain in time: 57-88 ms
    either way, `/tmp/smoke-nest/readq.py`. So the query is not where the time goes.) The size grows the same way:
    38 KB / 117 KB / 241 KB, because each nested document's `meta.semanticSpaces` lists every space above
    it (59 at depth 60; 7.4 KB of `meta` for that one document). Writes and updates are linear: a PUT that changes
    the innermost letter is 68 ms at 21 deep and 232 ms at 61, and keeps every nested id.
42. **Low. Adding a subclass of a type that a generic wrapper takes is flagged as losing data, and the migration's
    description is enormous.** Adding three `Statement` kinds made `Factoid.statements` and `Order.thing_ordered`
    "now also `Causes[TCause=document:Accusation|...]`, no longer `Causes[TCause=...]` [LOSES DATA]": the option is
    compared by its text, which lists every kind. The labels are the same, so nothing is deleted (the check for
    edges to removed labels finds none), but `migrate` asks for `--backup`/`--no-backup` and a "y", and
    `makemigrations` printed 33 KB for this change.
43. **Perf. Page 1 of an abstract class costs time in proportion to its size.** `GET /api/Statement?pageSize=5`:
    240 ms (71,881 statements; 35 ms on the first data); `DatedStatement` 105 ms (25,261); `Letter` 17 ms (1,377);
    `Factoid` 60 ms (30,228). Probably the count; not looked into.
44. **Perf. A list search for text with no letters is slow and finds nothing.** `GET /api/Person?q=1` 250 ms,
    `q=' OR 1=1 --` 450 ms (94 ms on the first data), both 0 results; `q=Lorenzo` 30 ms (493). Not looked into.
45. **Low. `/api/search` for a class that is only ever inside another document answers `count: 0`.** `{"type":
    "Letter"}`, `{"type": "Meeting", "where": {"participants": {"exists": true}}}`: 0, with no message. As documented
    (results are head documents), but it looks like a search that found nothing. It could say "a Letter is only
    found inside a Factoid: search Factoid with `statements` or `$somewhere`".

**What worked in the second run:**

- The new kinds are stored and read back exactly on both backends (Neo4j: the same checks on its copy, migrated with
  0003): report chains up to 61 documents deep (30 reports of 30 orders of a letter), the letter's `sender` bound
  from the innermost order; four reified levels with the people and their percentages; three embedded levels.
  Writes stay linear: 21 deep 84 ms, 61 deep about 1.4 s (with the ingest running). Updates keep every nested id.
- A person four reified levels down has the `Witnessing` in `witnessed`; one in an order 16 spaces deep has it in
  `ordered`. Structured search sees through `InRole`, through all four reified levels (`witnesses: {is: id}`),
  into three embedded levels (nested patterns) and finds deep documents with `$somewhere`; every count matched
  Cypher (50-150 ms).
- `migrate --backup` took a snapshot first, applied 0003 and read all 15,784 documents back (47 s). It says Memgraph
  removes the snapshot in about 15 minutes unless kept: good to be told.
- Doubling: 49,910 more entities in 325 s (308 s the first time) with 0 errors; 15,000 factoids over REST in 288 s
  (52/s, p50 140 ms, p95 192 ms; 55/s the first time), 2 refused rightly (people deleted by earlier checks).
- On 3.4 times the nodes of the first load test: 32 readers and 8 writers 277 requests/s (301), get person p50/p95
  210/604 ms (199/489), writes 374/806 ms (328/675). `api_checks.py`: the same 8 failures as before (the three
  fixed since are gone), its timings 1.5-2 times the first run's in total; `search_checks.py` the same 8 failures,
  1.7 times. The super-person: `GET` 0.99 s / 1.86 MB; its page in the production build 0.84 s, 16,260 elements;
  the list pages 0.06-0.13 s, the calendar 1.0 s.
- `pangloss history baseline --dry-run` (an item left last time): 145,451 looked at, **0** to record (the hooks wrote
  a record of everything as it went in), in 12 min 16 s (3.9 ms each on the first data, 5.1 ms now). So a real run
  has nothing to do; it was not run.
- `pangloss check-data` on the whole doubled database: all 219,101 documents and entities can be read, in 6 min
  45 s. Six reads logged as slow, 10.0-11.6 s each (probably the most referred-to entities, read whole and several
  at once; not checked).

## High

1. ✅ *Fixed: the SDK's copy of a module takes the interface names from an inert stand-in; `pangloss_library` no longer needs the interface.* **No SDK can be built for a project that uses `InterfaceMeta` or `pangloss_library`, the demo included.**
   `pangloss_interface` is in the SDK builder's `SERVER_ONLY` list (`pangloss-sdk-server/.../closure.py`), so a
   models module that imports `InterfaceMeta` (as the docs and the demo do) is refused: "`smoke.models` imports
   `pangloss_interface`, which a client of the API does not have". After taking `InterfaceMeta` out of the models,
   the build still fails, because `pangloss_library/models.py` itself imports `InterfaceMeta, Slider` from
   `pangloss_interface` (the clean-client check raises `ImportError: a client does not have pangloss_interface`).
   `pangloss sdk status` in `pangloss-demo` fails the same way. The import came in with 5f128e1 (2026-10-28).
   So the SDK could not be pulled; the data went in through the server-side model API (entities) and the REST API
   with a personal access token (factoids), which is what the SDK would have called.

## Medium

2. ✅ *Fixed: a word is cut to what the index can match; both backends.* **A search term with one long word is a 500.** `GET /api/Person?q=<500 × 'a'>` and `GET /api/autocomplete?q=...`
   answer `500 Internal server error`; Memgraph says `Tantivy error: ... Compiled regex exceeds size limit of 1000
   states`. 480 characters passes, 500 fails. (A pasted URL or a long run of text with no spaces can do it.) Should
   be a 422, or the word cut short.
3. ✅ *Fixed: the autocomplete search passes `SEARCH_HIT_LIMIT`.* **Autocomplete loses entities whenever a word of the query is in more than 1,000 labels of any type.**
   Root cause found: `autocomplete_query` (`pangloss-cypher/autocomplete_query.py`) calls Memgraph's
   `text_search.regex_search("label_text", pattern)` with no limit, and Memgraph returns **at most 1,000 hits** by
   default; the type filter (`$labels`) is applied after. (The list query passes `SEARCH_HIT_LIMIT`, 100,000, and
   does not have the problem.) Seen: `autocomplete?q=Ubiquitous&type=Person` finds **nothing** (the super-person's
   3,000 factoids have the word in their labels: `regex_search('.*ubiquitous.*')` gives 1,000, `CONTAINS` 3,001),
   though `q=Bartolomeo` finds him and `GET /api/Person?q=Ubiquitous` finds him. `q=House of&type=Family` finds 0
   of the 1,500 "House of X" (thousands of Buildings and Zotero titles have "of"); `q=Codex` says `count: 1000` of
   2,500; `q=House&type=Family` 501 of 1,500. **In the interface this means a person cannot be picked in a form by
   their surname if the surname is common in factoid labels**: `Find Person…` with "Bartolomeo Ubiq" offers nothing.
4. (merged into 3)
5. ✅ *Fixed: unknown dates are in no view (a judgement call, to confirm); long covering periods are counted and read from `GET /api/calendar/covering`; one query for all fields: a day 0.15 s, 55 KB.* **Calendar day view lists thousands of undated-in-effect documents, on every day.** `GET
   /api/calendar/day/G1500-03-25` returns 5,829 hits (2.1 MB anonymous, 2.6 MB logged in, 1.1-2.2 s). 5,673 of
   them span 100 years or more: statements with an `UnknownDate`, or periods whose end is unknown or ongoing, which
   run from `DATES_EARLIEST_YEAR` to `DATES_OPEN_END_YEAR`. So every day of 1400-1700 shows the same ~5,700 items;
   there is no paging or cap (`truncated: false`). Month and year views take 1.2-1.7 s too.

20. ✅ *Fixed: the cause was a nested `Loading` round a lazily loaded section, not the 25 facts.* **Interface: the derived section of an entity with more than 25 facts of a class crashes.** On the super-person's
    page (MetWith 137, GaveTo 58: the only person over the first page of 25) the console says `A section of an
    interface module failed: TypeError: node.setAttribute is not a function at className ... at _$effect.name
    (DerivedSection.tsx:74:5)` and the whole derived section is missing (no "and N more" button either). An ordinary
    person's derived section renders with no error. Likely the `class={[...]}` of the "and {count} more" button in
    `<Show when={left() > 0}>` (`pangloss-derived/.../DerivedSection.tsx` ~line 249), which only exists past 25.
    Seen on the dev server and **also on the production build** (`TypeError: e.setAttribute is not a function at
    ... DerivedSection-H0mb7qHC.js`), logged in by the session cookie; there the page loads in 2.3 s (dev 5.2 s).

26. ✅ *Fixed: a write is three statements over rows whatever its size: 200 statements 134 s -> 0.3 s.* **Writing one document is superlinear in its size: a factoid of 200 statements took 134 s.** One
    `write_head_node` transaction of 134,444 ms (`POST /api/Factoid -> 201 in 134537 ms`); dropping 50 of them in an
    update (`replace_head_node`) took 59 s. Reading it back: 116 ms. Measured (`smoke_scripts/scaling.py`): Deaths
    only, 10 / 20 / 40 / 80 statements: 58 / 134 / 527 / 3,681 ms; mixed kinds, 5 / 10 / 20 / 40: 53 / 90 / 211 /
    1,219 ms (about n^2.7). Orders nested 3 / 12 / 30 deep: 62 / 181 / 1,387 ms. A long charter or a register page
    with a hundred entries is a realistic factoid. (The long transaction is also one the other writers wait on.)

## Low

6. ✅ *Fixed: read as `Annotated[int | None, Ge(1)]`.* **`Annotated[int, Ge(1)] | None` is refused** by `initialise()` ("Unsupported type for field
   LanguageSpoken.fluency"), though `Annotated[int, Ge(1)]` and `int | None` both work.
   `Annotated[int | None, Ge(1), Le(5)] = None` is accepted. Natural spelling, confusing refusal.
7. ✅ *Fixed: in part: the template says so at the port, and the tests stop at a database of more than 20,000 nodes.* **`pangloss new-project` writes `DB_URL="bolt://localhost:7687"`**, the port the test suite wipes (the
   tutorial says to change it, but the default is the dangerous one).
8. ✅ *Fixed: the username is an argument, as in the other commands.* **`pangloss users create admin` (username as an argument) says only "Username: Aborted."** with stdin closed:
   the extra argument is ignored silently, not reported. Emails at `.test` are refused as "special-use" (fine, but
   surprising for a smoke test; `example.org`-style works).
9. ✅ *Fixed: the message names the setting.* **A Period that starts after `DATES_OPEN_END_YEAR` and is ongoing is refused** with "the earliest date is after
   the latest (the range would be empty)". With the default 1600, a period starting in 1605 cannot be ongoing. The
   message does not name the setting. (Set `DATES_OPEN_END_YEAR = 1700` here.)
10. ✅ *Fixed: read in either case; an unknown one is a 422 that lists those the route has.* **Query parameters are snake_case only, and unknown ones are ignored silently.** `?pageSize=100` (the camelCase
    the JSON uses everywhere) is ignored and 50 come back; `?pageSize=501` is not refused either.
11. ✅ *Fixed: `loc` is the path in what was sent; the union member is in `model`, short; a long `input` is left out.* **422 messages for union fields are enormous**: the `loc` of a factoid's statement error names the whole union
    (`Hypothetical[Accusation, Appointment, ... 68 names]Create`), ~3 KB for one error.
12. ✅ *Fixed: the interface's server passes `/api` on (`--api-url`), and says so when the API is not there.* **The production interface (`pangloss interface serve`) on its own cannot log in**: nothing passes `/api` to
    the API (by design: "the production proxy for /api is a decision still open"), and the login dialog shows a bare
    "Not Found". A message saying the API cannot be reached would save time. Used `interface dev --api-url` instead.

## Perf

13. ✅ *Fixed: 3.2 s; the schemas made on the way are no longer made.* **`initialise()` takes 11-12 s for this model** (6,538 Pydantic classes built, 4,600 `model_rebuild` calls;
    profiled `setup-database`: 18.5 of 19.5 s in `_initialise_models`). Every command that needs models pays it
    (`makemigrations` 14 s, `migrate` 15 s, `setup-database` 12 s, `zotero status` 17 s), and so do server start and
    any script. Commands that do not initialise (`showmigrations`) take 0.5 s.
14. **Writes are ~500 ms each while another writer is busy.** During the Zotero sync, entity writes at concurrency
    16 took 510-550 ms each (`write_head_node took 5xx ms (slow)`), and reads queued behind them
    (`get_access_token_in_db_by_hash took 706 ms`, `get_user_in_db 563 ms`). Alone: 155-200 entities/s.
15. ✅ *Fixed: the query cuts before it reads; `?incoming_limit=` and `GET /api/NAME/{id}/incoming/{field}`; whole read 0.6-0.8 s, limited 0.32 s.* **An entity's `HeadView` inlines every reverse relation, unpaged.** The super-person (3,926 reverse items from
    3,000 factoids) is a 1.86 MB response, 0.8-1.1 s, logged in. Linear in references.
16. ✅ *Fixed: the version reached is stored as the sync goes, and `status` says how far it is. Its speed is Zotero's.* **The Zotero first sync is slow and restarts from zero.** The library version is stored only at the end of a
    sync, so a server restart during the first sync (here at 5,440 items) starts it again; the second pass skips
    unchanged items but still took 15+ minutes to make progress visible. `zotero status` says "version 0, never
    synced" the whole time, with 8,000+ items in the database.

21. ✅ *Fixed: the month page is 0.45 MB, the day page 0.55 MB (see 5).* **Interface calendar pages are huge.** `/calendar/gregorian/1500/3` server-renders **21 MB of HTML** (1.6 s on
    the server; 5-6 s to load in the browser), and the day and year pages are as slow: the API's hits of item 5,
    once per day. Other pages: 70-250 ms.
22. ✅ *Fixed: the page reads 25 of each relation, with "and N more": 2.4 s, 16,045 elements, 61,050 px.* **The super-person's interface page**: 5.2 s to load, 29,507 DOM elements, 105,716 px tall (every reverse
    relation as chips, no paging or folding). Usable, but it grows with the data. (Its edit page: 160 ms.)
23. **Every interface page is ~256 KB of HTML** on the dev server even when empty (a missing person: 256,570 bytes).
    Not checked on the production build (it needs a proxy for /api, item 12).

24. ✅ *Fixed: the server looks, and answers 503 "restart the server" once a migration it did not have is applied.* **A running server is not told the database was migrated.** `pangloss migrate` (rename `Kinship.kind` to
    `kinship_kind`, 217 nodes; 67 s with the read-back of 36,525 items) while the API ran: during it, writes were
    refused properly (`PanglossReadOnlyError`); after it, the old server read a factoid with a Kinship and answered
    **500** (`ValidationError for FactoidHeadView`) until restarted. It could notice the schema moved on (it already
    checks pending migrations at start) and say so (503), rather than 500.
25. ✅ *Fixed: a failed item holds only itself back and is tried again; a migration postpones the sync.* **One failed Zotero item means the whole library version is not stored.** The sync finished with "10129
    created, 0 updated, 5440 unchanged, 150 removed, skipped 10 attachment, 14 note, 1 errors": the one error was
    ZZ3UD5ZS, refused because my migration had locked writes for a minute. So `synced_version` stays 0 with ~15,500
    items in the database, and the next sync goes through all of them again; and it is not retried until Zotero's
    stream reports a change or the server restarts. (Expands item 16. A transient error could be retried, or the
    version stored for the batches that succeeded.)

27. **Load (one API worker, dev laptop, ~200k nodes):** 32 readers: 479 req/s; p50/p95: get person 113/139 ms, get
    factoid 31/43, list search 47/63, autocomplete 35/49, structured search 38/51. With 8 writers as well: 301 req/s,
    get person 199/489 ms, writes 328/675 ms. A person read is 7 ms alone but queues badly under concurrency (it
    reads ~95 reverse-relation fields).
28. ✅ *Fixed: in part: the view has what the page has read (2.2 s) and reads everything only when asked; all of it is as heavy as it was.* **The by-date view of the super-person** takes 3.5 s and makes 47,069 DOM elements.

29. ✅ *Fixed: the delete refuses and marks nothing; a second type of one name beside the first is refused (a judgement call, to confirm); either name finds a typology.* **Typology: the generic DELETE route marks a type in use for deletion**, where the typology's own rule is to
    refuse. `DELETE /api/OccupationType/{Banker}` (620 people have it) answered 409 "... It has been marked for
    deletion", and Banker now has `meta.markedForDeletion: true` while it stays in the tree, in autocomplete and on
    620 people (guide/typology: `delete(id)` "refused if it has subtypes or is in use"). Also: a second root type
    called "Merchant" is accepted (two "Merchant"s side by side in the tree); and the API takes the typology's class
    name (`/api/typology/OccupationTypology/tree` works) while the CLI only takes the type's
    (`pangloss typology tree OccupationTypology`: "No typology OccupationTypology. Known: OccupationType, TitleType").
30. ✅ *Fixed: the slow threshold is raised while the check reads many at once.* **`pangloss check-data` floods the terminal** with hundreds of `read transaction get_entity took 5xx ms (slow)`
    warnings while it reads (93,470 items, 135 s), burying its one line of result.
31. ✅ *Fixed as far as it goes: made in a thread, so the server answers meanwhile; 104 KB on the wire since gzip.* **`/openapi.json` is 2.5 MB (570 paths, 1,014 schemas) and the first request takes 4.9 s** (then cached: 10 ms).
    `/docs` loads it.

32. ✅ *Fixed: the packages ship stubs of their models; typology entities, `Typed[...]` and `Var` of a trait type-check.* **`make-stubs` output does not type-check in a project outside the monorepo's `ty` overrides.** `ty check
    pangloss-smoketest/smoke`: 1,748 diagnostics (1,240 `invalid-type-form`, 335 `unresolved-attribute`, 161
    unused `type: ignore`). Causes: the stub refers to `pangloss_dates.models.DateRange.Create` / `.Where` etc., which
    in `pangloss_dates` (no stubs of its own) are typed as variables (`type[_EmbeddedCreateBase]`) or not at all (1,232
    and most of the 335); `Typed[OccupationTypology]`, as the typology guide says to write it, is "Non-generic class
    `Typed` cannot be specialized"; and the derived-rule patterns `Meeting.Where(participants=a)` with `a:
    Var[Agent]` (through `InRole[Agent]`) and `Gift.Where(given_by=a)` (through `Identification[...]`) are refused by
    the stubs though they work. The demo shows "All checks passed" only because `pyproject.toml` relaxes those rules
    for `pangloss-demo/**`; `models.pyi` here is 689 KB, 6,074 lines.

33. ✅ *Fixed: as 26: the same write path, and no long transaction.* **Neo4j (`pangloss-neo4j`), same project at 1/10 scale on `neo4j:2026.10.1` (:7699, `settings_neo4j.py`):**
    5,333 entities at 319/s and 500 factoids over REST (39/s, p50 179 ms), 0 errors. But the superlinear write of
    item 26 is worse there: one factoid of 10 / 20 / 40 / 80 / 120 / 160 Deaths took 281 / 694 / 1,676 / 8,896 /
    23,817 / 49,045-52,321 ms. Once in three tries at 160 it was a **500**: Neo4j's own `Neo.DatabaseError.General.
    UnknownError: Comparison method violates its general contract!` (a Java sort inside the database, during
    Pangloss's single big transaction), then `GqlError 50N09 invalid server state transition`.
34. ✅ *Fixed: the "unrecognized" class of notifications is off in the driver.* **On a new Neo4j database the logs are flooded with driver notifications**, each "property key does not exist"
    warning (`head_node_type`, `review_status`, `meta.semantic_spaces`, ...) printed **with the whole Cypher query**
    (~3 KB each) during `migrate`'s read-back and the first reads, until data exists. They are harmless and could be
    filtered (the driver's `notifications_min_severity` / disabled categories).

35. ✅ *Fixed: the count: a document inside another is not a head node. The speed is as it was.* **`pangloss history baseline --dry-run` counts nested statements as needing a record, and is slow.** "93474
    looked at: 19191 would be recorded, 74283 had a record of their version already" in **6 min 8 s**. 19,191 is
    exactly the number of `Statement` nodes, which are nested in factoids (`create_directly=False`) and have no
    versions of their own; every factoid and entity has its record (history was written even for the entities made
    by a separate script process, as the hooks run in any Pangloss process). So a real run would write ~19,000
    needless records (not run). The history store is `.pangloss/history.sqlite3`, 222 MB for this data.

36. ✅ *Fixed: 220 -> 218 here; one migration named alone is the run up to it.* **`squashmigrations` does not fold a later rename or added field into the create** (dry run of 0001-0002: "220
    changes in 2 migrations -> 220 changes": "Create the Document Kinship" then "Rename the field Kinship.kind to
    kinship_kind"; "Create the Entity Person" then "Add the literal field Person.nickname"). It works; it is just not
    shorter. Also `squashmigrations smoke 0002` (one number) only says "Missing argument 'last'".

## Design (documented, but worth a look)

17. **Editing a checked factoid keeps it checked and published**: the edit is public at once and never reviewed
    unless the editor sets it back. And by default anyone may check their own work (`REVIEW_ALLOW_SELF_REVIEW`
    defaults to True). Both as `guide/review` says.
18. **Structured search cannot reach into a reified relation** (`source: 'AtPage' is not a document or an entity
    type, so it cannot be searched`: no "factoids citing page 12"), **cannot name the abstract `Statement`** in a
    nested pattern (`'Statement' is not one of the types the relation allows`), and **cannot search a TypedDict**
    field (`coordinates.latitude`).
19. **Structured search `has_type is Merchant` does not include subtypes** (594 directly typed; with its five
    subtypes it would be ~3,000), and `supertype` is not a searchable field (`OccupationType has no field
    'supertype'`). Subtypes are found only through `GET /api/typology/OccupationType/{id}?include_subtypes=true`,
    not in a search pattern (so not combined with other conditions).

- **Login lockout is by username**: after 10 wrong passwords for `editor`, the 11th and 12th tries are 429, and so
  is the right password. Anyone can lock any user out by guessing (documented as "count towards the login limit").
- ✅ *Fixed: it says so before the list.* **Migrating back** asks before losing data (`--backup` or `--no-backup`; `nickname` is flagged although no node
  has it), took a snapshot, renamed 219 properties back in 72 s; its read-back then lists 421 "unreadable"
  factoids, rightly, since the code is still at 0002: it could say "the code is ahead of the database" instead.

## Experiment: gzip (code changed, uncommitted)

Nothing was compressed: not the API (`content-length: 2109640` for a calendar day with `Accept-Encoding: gzip`),
not the interface's server. Changed, at the user's request:

- `packages/pangloss-api/src/pangloss_api/app.py`: Starlette's `GZipMiddleware` (`minimum_size=1000`; it leaves
  `text/event-stream` alone), inside the request logger, outside CORS.
- `packages/pangloss-interface/.../interface-app/serve.mjs` (new): wraps the Solid plugin's generated
  `createListener` and gzips text answers of 1 KB or more, flushing each chunk (`Z_SYNC_FLUSH`) so streamed
  rendering still streams; `pangloss interface serve` runs it (`cli.py`), and `test_serve_needs_a_build` expects it.
  The dev server (Vite) is not changed.
- `pangloss-api` (165) and `pangloss-interface` (163) tests pass; ruff clean. Not run: the full `run_tests.sh`, e2e.

Measured (`smoke_scripts/gzip_sizes.py`, `out/gzip_sizes.txt`):

| Answer | Plain | Gzipped |
|---|---|---|
| API calendar day | 2,641,196 | 197,230 (7.5%) |
| API calendar month | 2,397,702 | 196,739 (8.2%) |
| `/openapi.json` | 2,546,833 | 101,479 (4.0%) |
| API super-person (logged in) | 1,860,254 | 205,484 (11.0%) |
| API Factoid list of 500 | 183,736 | 15,196 (8.3%) |
| Interface `/` | 163,189 | 29,960 (18.4%) |
| Interface `/Person` | 215,522 | 35,706 (16.6%) |
| Interface super-person page | 7,848,410 | 539,082 (6.9%) |
| Interface calendar month | 26,289,998 | 1,948,396 (7.4%) |
| Interface calendar day | 12,360,458 | 656,268 (5.3%) |

Cost: compressing the super-person's 1.86 MB takes 23 ms at level 9 (10 ms at 6) in the middleware alone; end to
end the difference is lost in the server's own variance (0.79 or 1.12 s either way, eight interleaved runs).
Time to first byte of the streamed calendar page is unchanged (8 ms gzipped, 11 ms plain); pages hydrate with no
errors. On localhost this saves no time; over a real network a 26 MB page becomes 1.9 MB. (The big pages are still
too big: items 5, 15, 21, 22.)

## Worked well (for balance)

- Security spot checks (`smoke_scripts/security_checks.py`): a label of `<img onerror>`, `<script>` and `<svg onload>`
  is shown as text on the item, list and search pages of the production interface, and nothing runs; Cypher-looking
  field names, a model name and an `order_by` field in `/api/search` are all refused (422, naming them).

- The interface's form made a factoid end to end (Zotero source search, headless `AtPage` with page, type grid
  grouped by abstract parent, single-date kinds only for an `EventStatement`, person search, Save, toast): stored
  exactly. Stale edit in the form: "Someone has saved this item since you opened it. Nothing was overwritten".
  History panel and restore with a "what will change" confirmation: version 3 with the old label. Delete explains
  what refers to an item. Search-by-fields form shows the new field after the migration.
- 10 racing updates on one version: exactly one 200, nine 412. `create_inline` makes a person by URL from inside a
  factoid; a second `create_new` with the same URL reuses it; an entity class without it is refused (422).
- Field binding is filled in on the server (the ordered Gift's `given_by` is the Order's `ordered_to`), through
  30 nested Orders; every level records its spaces.
- Derived facts follow deletes and undeletes within a second (justifications 2 -> 1 -> 2).
- Migration with a rename asked and recorded; dry run counts the properties; applied with a read-back of 36,525.

- Model errors at `initialise()` are early and clear (`has_type` naming rule, unsupported annotations).
- 49,910 entities in 308 s (162/s) with 0 errors; 5,000 factoids over REST in 91 s (55/s, p50 136 ms, p95 184 ms),
  0 errors; 3,000 more in 54 s.
- Structured search, lists and autocomplete: 8-60 ms on ~194k nodes; counts checked against Cypher matched.
- Versions (428/412/400/`*`), 308/409 on subclass routes, validation 422s, delete/undelete/referencedBy, read-scope
  tokens, disabled users, refresh/revoke, review comments and targets, history, typology tree, calendar Easter, the
  Zotero read-only fields (403): all as documented.
- Derived rules kept up with the REST writes (923 MetWith, 278 GaveTo, 34 SameGroup) and are hidden from anonymous
  readers while their factoids are unpublished.



- ✅ *Fixed (2026-11-06): Solid raised to rc.21, which changed neither; both were ours, and three more of the kind were found. See `FIXES.md` and `docs/interface-refactoring.md`.* REPORTED BY USER: Clicked around a bit on the live smoketest frontend, and the server was logging the following:

[SSR_BOUNDARY_WATERFALL] A <Loading> boundary took 4 render passes — 3 sequential async waits, 524ms end to end: each read could start only after the previous one answered. If a later read doesn't need the earlier answer, derive both from the same inputs so they start together; if the dependency is intrinsic, preload the dependent data or join the requests.
  in <Document> › <App> › <ComponentsProvider> › <ComponentsContext> › <ApiProvider> › <ApiContext> › <ModelsProvider> › <ModelsContext> › <ModulesProvider> › <ModulesContext> › <Loading> › <TranslationsProvider> › <TranslationsContext> › <NavExpandedProvider> › <NavExpandedContext> › <LoginDialogProvider> › <LoginDialogContext> › <ConsoleMountProvider> › <ConsoleMountContext> › <SidePanelProvider> › <SidePanelContext> › <Router> › <RouterContextObj> › <Root> › <RootComp> › <Frame> › <SessionProvider> › <SessionContext> › <ClipboardProvider> › <ClipboardContext> › <StashProvider> › <StashContext> › <ToastsProvider> › <ToastsContext> › <Padded> › <Loading> › <Routes> › <Show> › <RouteContextObj> › <wrap> › <Page> › <Errored> › <Loading>
  at src/pages/Item.tsx:163:9
[SSR_BOUNDARY_WATERFALL] what it means and how to fix it: https://v2.solidjs.com/reference/solid-js/diagnostics/ssr-boundary-waterfall
[SSR_BOUNDARY_WATERFALL] agent repair guide: node_modules/solid-js/skills/reactivity-diagnostics/SKILL.md#ssr_boundary_waterfall — https://github.com/solidjs/solid/blob/next/packages/solid/skills/reactivity-diagnostics/SKILL.md#ssr_boundary_waterfall
[SERVER_WRITE] Writing a signal on the server is deprecated and will become an error. Server render is pure: state changes flow from async sources (promises, async iterables), never setters — this write landed as inert data (nothing re-renders). If you are bridging a subscription, make it the async source itself instead of pushing writes from its callback.
[SERVER_WRITE] what it means and how to fix it: https://v2.solidjs.com/reference/solid-js/diagnostics/server-write
[SERVER_WRITE] agent repair guide: node_modules/solid-js/skills/reactivity-diagnostics/SKILL.md#server_write — https://github.com/solidjs/solid/blob/next/packages/solid/skills/reactivity-diagnostics/SKILL.md#server_write

Check these things out. First, try bumping the version of SolidJs 2.0 to the most recent release (it's still working through release candidates, but at a quite fast rate)
