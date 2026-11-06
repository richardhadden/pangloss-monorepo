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
`FIXES.md`):** 1, 2, 3, 5, 20, 21, 26, 29, 32, 33. Each is marked below. The text of an item is as it was found.

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

6. **`Annotated[int, Ge(1)] | None` is refused** by `initialise()` ("Unsupported type for field
   LanguageSpoken.fluency"), though `Annotated[int, Ge(1)]` and `int | None` both work.
   `Annotated[int | None, Ge(1), Le(5)] = None` is accepted. Natural spelling, confusing refusal.
7. **`pangloss new-project` writes `DB_URL="bolt://localhost:7687"`**, the port the test suite wipes (the
   tutorial says to change it, but the default is the dangerous one).
8. **`pangloss users create admin` (username as an argument) says only "Username: Aborted."** with stdin closed:
   the extra argument is ignored silently, not reported. Emails at `.test` are refused as "special-use" (fine, but
   surprising for a smoke test; `example.org`-style works).
9. **A Period that starts after `DATES_OPEN_END_YEAR` and is ongoing is refused** with "the earliest date is after
   the latest (the range would be empty)". With the default 1600, a period starting in 1605 cannot be ongoing. The
   message does not name the setting. (Set `DATES_OPEN_END_YEAR = 1700` here.)
10. **Query parameters are snake_case only, and unknown ones are ignored silently.** `?pageSize=100` (the camelCase
    the JSON uses everywhere) is ignored and 50 come back; `?pageSize=501` is not refused either.
11. **422 messages for union fields are enormous**: the `loc` of a factoid's statement error names the whole union
    (`Hypothetical[Accusation, Appointment, ... 68 names]Create`), ~3 KB for one error.
12. **The production interface (`pangloss interface serve`) on its own cannot log in**: nothing passes `/api` to
    the API (by design: "the production proxy for /api is a decision still open"), and the login dialog shows a bare
    "Not Found". A message saying the API cannot be reached would save time. Used `interface dev --api-url` instead.

## Perf

13. **`initialise()` takes 11-12 s for this model** (6,538 Pydantic classes built, 4,600 `model_rebuild` calls;
    profiled `setup-database`: 18.5 of 19.5 s in `_initialise_models`). Every command that needs models pays it
    (`makemigrations` 14 s, `migrate` 15 s, `setup-database` 12 s, `zotero status` 17 s), and so do server start and
    any script. Commands that do not initialise (`showmigrations`) take 0.5 s.
14. **Writes are ~500 ms each while another writer is busy.** During the Zotero sync, entity writes at concurrency
    16 took 510-550 ms each (`write_head_node took 5xx ms (slow)`), and reads queued behind them
    (`get_access_token_in_db_by_hash took 706 ms`, `get_user_in_db 563 ms`). Alone: 155-200 entities/s.
15. **An entity's `HeadView` inlines every reverse relation, unpaged.** The super-person (3,926 reverse items from
    3,000 factoids) is a 1.86 MB response, 0.8-1.1 s, logged in. Linear in references.
16. **The Zotero first sync is slow and restarts from zero.** The library version is stored only at the end of a
    sync, so a server restart during the first sync (here at 5,440 items) starts it again; the second pass skips
    unchanged items but still took 15+ minutes to make progress visible. `zotero status` says "version 0, never
    synced" the whole time, with 8,000+ items in the database.

21. ✅ *Fixed: the month page is 0.45 MB, the day page 0.55 MB (see 5).* **Interface calendar pages are huge.** `/calendar/gregorian/1500/3` server-renders **21 MB of HTML** (1.6 s on
    the server; 5-6 s to load in the browser), and the day and year pages are as slow: the API's hits of item 5,
    once per day. Other pages: 70-250 ms.
22. **The super-person's interface page**: 5.2 s to load, 29,507 DOM elements, 105,716 px tall (every reverse
    relation as chips, no paging or folding). Usable, but it grows with the data. (Its edit page: 160 ms.)
23. **Every interface page is ~256 KB of HTML** on the dev server even when empty (a missing person: 256,570 bytes).
    Not checked on the production build (it needs a proxy for /api, item 12).

24. **A running server is not told the database was migrated.** `pangloss migrate` (rename `Kinship.kind` to
    `kinship_kind`, 217 nodes; 67 s with the read-back of 36,525 items) while the API ran: during it, writes were
    refused properly (`PanglossReadOnlyError`); after it, the old server read a factoid with a Kinship and answered
    **500** (`ValidationError for FactoidHeadView`) until restarted. It could notice the schema moved on (it already
    checks pending migrations at start) and say so (503), rather than 500.
25. **One failed Zotero item means the whole library version is not stored.** The sync finished with "10129
    created, 0 updated, 5440 unchanged, 150 removed, skipped 10 attachment, 14 note, 1 errors": the one error was
    ZZ3UD5ZS, refused because my migration had locked writes for a minute. So `synced_version` stays 0 with ~15,500
    items in the database, and the next sync goes through all of them again; and it is not retried until Zotero's
    stream reports a change or the server restarts. (Expands item 16. A transient error could be retried, or the
    version stored for the batches that succeeded.)

27. **Load (one API worker, dev laptop, ~200k nodes):** 32 readers: 479 req/s; p50/p95: get person 113/139 ms, get
    factoid 31/43, list search 47/63, autocomplete 35/49, structured search 38/51. With 8 writers as well: 301 req/s,
    get person 199/489 ms, writes 328/675 ms. A person read is 7 ms alone but queues badly under concurrency (it
    reads ~95 reverse-relation fields).
28. **The by-date view of the super-person** takes 3.5 s and makes 47,069 DOM elements.

29. ✅ *Fixed: the delete refuses and marks nothing; a second type of one name beside the first is refused (a judgement call, to confirm); either name finds a typology.* **Typology: the generic DELETE route marks a type in use for deletion**, where the typology's own rule is to
    refuse. `DELETE /api/OccupationType/{Banker}` (620 people have it) answered 409 "... It has been marked for
    deletion", and Banker now has `meta.markedForDeletion: true` while it stays in the tree, in autocomplete and on
    620 people (guide/typology: `delete(id)` "refused if it has subtypes or is in use"). Also: a second root type
    called "Merchant" is accepted (two "Merchant"s side by side in the tree); and the API takes the typology's class
    name (`/api/typology/OccupationTypology/tree` works) while the CLI only takes the type's
    (`pangloss typology tree OccupationTypology`: "No typology OccupationTypology. Known: OccupationType, TitleType").
30. **`pangloss check-data` floods the terminal** with hundreds of `read transaction get_entity took 5xx ms (slow)`
    warnings while it reads (93,470 items, 135 s), burying its one line of result.
31. **`/openapi.json` is 2.5 MB (570 paths, 1,014 schemas) and the first request takes 4.9 s** (then cached: 10 ms).
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
34. **On a new Neo4j database the logs are flooded with driver notifications**, each "property key does not exist"
    warning (`head_node_type`, `review_status`, `meta.semantic_spaces`, ...) printed **with the whole Cypher query**
    (~3 KB each) during `migrate`'s read-back and the first reads, until data exists. They are harmless and could be
    filtered (the driver's `notifications_min_severity` / disabled categories).

35. **`pangloss history baseline --dry-run` counts nested statements as needing a record, and is slow.** "93474
    looked at: 19191 would be recorded, 74283 had a record of their version already" in **6 min 8 s**. 19,191 is
    exactly the number of `Statement` nodes, which are nested in factoids (`create_directly=False`) and have no
    versions of their own; every factoid and entity has its record (history was written even for the entities made
    by a separate script process, as the hooks run in any Pangloss process). So a real run would write ~19,000
    needless records (not run). The history store is `.pangloss/history.sqlite3`, 222 MB for this data.

36. **`squashmigrations` does not fold a later rename or added field into the create** (dry run of 0001-0002: "220
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
- **Migrating back** asks before losing data (`--backup` or `--no-backup`; `nickname` is flagged although no node
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
