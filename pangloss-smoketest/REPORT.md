# Pangloss smoke test: report

2026-11-06, 00:32 to 01:50 (CET), on branch `full-smoke-test` at 1765f20. One laptop, Docker Memgraph 3.14
(`mage`, commit-lock narrowing on), Neo4j 2026.10.1 Community for the backend check. Everything below was run, not
read from the code, unless it says so. Item numbers (#n) refer to `PROBLEMS.md`, which has the detail, the error
messages and the commands for each.

**Second run, 2026-11-07:** deeper models and twice the data, after the fixes of `FIXES.md`; see section 9, and
`PROBLEMS.md` items 37-45.

## 1. Summary

The core works well at this size. 50,000 entities and 8,000 factoids went in with no errors. Versions, validation,
deletes, review, history, derived facts, migrations (forward, back, forward), typology, Zotero and the interface's
main pages all did what the docs say. Reads and searches take tens of milliseconds on 337,000 nodes.

The serious problems:

1. **The SDK cannot be built for any project that uses `InterfaceMeta` or `pangloss-library`, the demo included**
   (#1). So the SDK could not be pulled.
2. **Writing a large document is superlinear.** A factoid of 200 statements took **134 s**, and on Neo4j a factoid
   of 160 took 50 s; once it failed with a Neo4j internal error (#26, #33).
3. **Autocomplete loses entities whenever a word of the query is in 1,000+ labels of any type**, because Memgraph's
   regex search returns 1,000 hits by default. In the interface, a person could not be picked in a form by their
   surname (#3).
4. **Pages and answers grow without limit with the data.** The calendar puts every document with an unknown or open
   date on every day (2.6 MB API answer, a **26 MB** interface page). An entity's view inlines every reverse
   relation (1.9 MB JSON, 7.8 MB page, 29,000-47,000 DOM elements for the super-person). Nothing was gzipped
   (#5, #15, #21, #22). Gzip was added as an experiment and cuts these by 89-95% (section 6).
5. **The interface's derived section crashes** for an entity with more than 25 facts of a class (#20).
6. **The generated type stubs do not type-check** in a project outside the monorepo's relaxed `ty` settings (1,748
   diagnostics), mostly because `pangloss-dates` has no stubs (#32).

There were also five unhandled 500s in all the server logs, all explained: a search word of 490+ characters (#2,
three times), a server left running after a migration (#24), and Neo4j's internal error (#33).

## 2. What was built

Made with the CLI as a user would (`pangloss new-project smoketest_site`, `new-app smoke`, `makemigrations`,
`migrate`, `users create`, `users tokens create`), in `pangloss-smoketest/` (see `README.md`).

- **Apps:** every package. `pangloss_memgraph` (or `pangloss_neo4j`), users, api, dates, calendar, typology,
  review, derived, library, interface, history, sdk_server, zotero, and `smoke`.
- **Entities (26 classes + 2 typologies):** Person (an `Agent` trait, URL ids, `create_inline`, `WithCertainty`
  name, `Date` born, `Typed[OccupationTypology]`); Group and 8 subclasses (Family, Guild, ReligiousOrder, Army,
  TradingCompany, University, Monastery, Court); Place, Settlement, Region, Building; PhysicalObject, Ship,
  Manuscript, Artwork, Painting, Sculpture; Book (`ZoteroBacked`, URL ids); Commodity, Currency, Office (typed by
  `TitleTypology`), Language; Feast (`DateCharacterisation`).
- **Statements (68 concrete kinds)** under an abstract `Statement` (`create_directly=False`), in four abstract
  groups:
  - `DatedStatement` (`Dateable`, 24 kinds: Letter, Sale, Loan, Order, Meeting with `InRole`, Gift with
    `Identification[WeightedAlternative[Person]]`, …);
  - `EventStatement` (`SingleDateable`, 23: Birth, Marriage with `MinLen(2)`, Founding with `ViaEdge[Agent,
    Certainty]`, …);
  - `PeriodStatement` (`PeriodDateable`, 11: OfficeHolding, Residence, Membership, Siege, …);
  - `UndatedStatement` (10: Kinship, NameVariant, LocatedIn, OccupationAscription, …).

  Most kinds narrow `involves` with `subclasses_parent_fields`. An `Order` binds `ordered_to` into the `given_by`,
  `payer` or `sender` of what it orders, inside a Positive or Negative subjunctive space.
- **Factoid:** `source: AtPage[ZoteroBacked]` (a page; `headless`), and `statements: list[Statement |
  Negative[Statement] | Hypothetical[Statement] | Causes[Statement, Statement]]`. It is reviewable.
- **Derived rules:** SameGroup, MetWith (through `InRole`), GaveTo.
- **Data, all invented:**
  - 49,910 entities, through the server-side model API, 16 at a time: 308 s, 162/s, 0 errors;
  - 15,570 Zotero items from the real group library in the demo's `.env` (synced by the server);
  - 5,000 factoids over REST with a personal access token: 91 s, 55/s, p50 136 ms, p95 184 ms, 0 errors;
  - **Bartolomeo Ubiquitous**, one person named in half the person slots of 3,000 more factoids: 3,926 reverse
    items, 2,176 referring documents, 137 MetWith;
  - in all, 8,795 factoids and 19,191 statements; 337,423 nodes and 825,815 edges at the end.
- **Users:** admin (admin), importer, editor, reviewer, reader, each with password `smoke-<name>-pw-2026`; the
  importer has a write token.

## 3. Findings

Severity as in `PROBLEMS.md`. Each line is a summary; the evidence is under the same number there.

### High
- **#1 No SDK with `InterfaceMeta` or `pangloss-library`.** `pangloss_interface` is "server only" for the SDK
  builder, and `pangloss_library` imports it. The demo fails the same way. It started with 5f128e1 (2026-10-28).

### Medium
- **#2** A one-word search of about 490+ characters is a 500 (Tantivy: "regex exceeds size limit"), on lists and
  autocomplete.
- **#3** Autocomplete does not pass a hit limit to `text_search.regex_search` (Memgraph's default is 1,000), and
  filters by type after. "Ubiquitous" finds no Person, and "House of" finds 0 of 1,500 Families. The counts stop at
  1,000.
- **#5** The calendar day view lists 5,829 documents, 97% of them spanning 100+ years (an `UnknownDate`, or an
  open period), on every day, with no paging: 2.1-2.6 MB, 1.1-2.2 s.
- **#20** Interface: `pangloss-derived`'s section throws `node.setAttribute is not a function` once a class has
  more than 25 facts (its "and N more" button), and the whole section is missing. This happens on the dev server and on
  the production build.
- **#26** Writes are about n^2.7 in the size of the document. Deaths 10 / 20 / 40 / 80: 58 / 134 / 527 / 3,681 ms;
  200 mixed statements: 134 s, all in one transaction. Dropping 50 of them in an update: 59 s.
- **#29** Typology: the generic `DELETE` marks a type in use for deletion. The typology's own rule is to refuse.
- **#33** On Neo4j the same writes are slower (160 statements: 49-52 s), and one attempt in three was a 500 from
  inside Neo4j ("Comparison method violates its general contract!").

### Low
- **#6** `Annotated[int, Ge(1)] | None` is refused; `Annotated[int | None, Ge(1)]` works.
- **#7** `new-project` writes the test port 7687 (which the test suite wipes) as the database.
- **#8** `users create admin`: the positional argument is ignored and it says only "Aborted".
- **#9** A period starting after `DATES_OPEN_END_YEAR` that is ongoing is refused with a message that does not name
  the setting.
- **#10** Query parameters are snake_case only (`pageSize` is ignored silently).
- **#11** 422 messages name the whole 68-member union, twice inside a `Causes`.
- **#12** `interface serve` on its own cannot log in: there is no `/api` proxy, and the dialog says only "Not
  Found".
- **#24** A running API is not told a migration happened, and answers 500 until restarted.
- **#25** One failed Zotero item (refused during my migration's write lock) leaves the library version unstored, so
  the next sync goes through all 15,570 items again.
- **#30** `check-data` floods the terminal with "slow" warnings.
- **#35** `history baseline --dry-run` would record the 19,191 nested statements, which have no versions of their
  own, and took 6 min to say so. The history SQLite file is 222 MB.
- **#36** `squashmigrations` does not fold a rename or an added field into the create (220 changes stay 220).
- **#34** On a new Neo4j database, driver notifications are logged with the whole query, about 3 KB each.
- Smaller notes in `PROBLEMS.md`:
  - `/Nonsense` renders as a list page titled "NONSENSES";
  - the migration file name is cut mid-word (`..._addfield_pers.py`);
  - a period of 1456 to 1456 shows as "1456 – 1456";
  - two root types may both be called "Merchant";
  - the API and the CLI name a typology differently;
  - "PLACES *" is marked required on the form, though an empty list saves.

### Perf
- **#13** `initialise()` takes 11-12 s for this model (6,538 Pydantic classes), and so does every command that needs
  models, every server start and every script.
- **#14** Writes take ~500 ms each while another writer (the Zotero sync) is busy, and reads queue behind them.
- **#15, #22, #28** The super-person: 1.86 MB JSON (0.8-1.1 s); the interface page 5.2 s, 29,507 DOM elements, 7.8
  MB of HTML; by-date view 3.5 s, 47,069 elements.
- **#16** The first Zotero sync of a 16,000-version library took over 25 minutes, and a restart during it starts it
  again.
- **#21** The calendar month page is 21-26 MB of HTML (28,167 person links), 1.6-2 s on the server.
- **#23** Every interface page is 160-260 KB of HTML even when empty.
- **#27** Load on one API worker: 479 req/s with 32 readers; 301 req/s with 8 writers as well. A person `GET` is 7 ms
  alone but 113-199 ms p50 under load, because it reads ~95 reverse fields.
- **#31** `/openapi.json` is 2.5 MB; the first request takes 4.9 s.

### Design (works as documented, worth a decision)
- **#17** An edit to a checked factoid is published at once, unreviewed. Anyone may check their own work by default.
- **#18** Structured search cannot look inside a reified relation (no "factoids citing page 12"), cannot name the
  abstract `Statement`, and cannot search a TypedDict.
- **#19** Structured search does not reach subtypes of a typology type, and `supertype` is not searchable. Subtypes
  are found only by `GET /api/typology/{T}/{id}?include_subtypes=true`.
- **#32** The stubs do not type-check outside the monorepo's relaxed `ty` settings: `pangloss_dates` has no stubs,
  `Typed[X]` is "non-generic", and derived patterns through wrappers are refused.
- **Login lockout is by username.** After 10 wrong passwords even the right one gets 429, so anyone can lock out
  any user.

## 4. Performance numbers

All on Memgraph with ~200-337k nodes, one API worker, unless it says Neo4j.

| What | Result |
|---|---|
| `initialise()` (this model) | 10.8-11.5 s |
| Entities, model API, 16 at once | 162/s with the Zotero sync running (155-200/s per class); Neo4j at 1/10: 319/s |
| Factoids, REST, 8 at once | 55/s, p50 136 ms, p95 184 ms (Neo4j: 39/s, p50 179 ms) |
| One factoid of 10 / 40 / 80 Deaths | Memgraph 58 / 527 / 3,681 ms; Neo4j 281 / 1,676 / 8,896 ms |
| One factoid of 200 mixed statements | 134.5 s (update dropping 50: 59 s; read 116 ms) |
| Structured searches | 8-60 ms (counts checked against Cypher); deep search 0.04-0.84 s |
| List and label search | 9-61 ms; autocomplete 6-15 ms |
| Person `GET` / factoid `GET` | 7 ms / ~30 ms alone; under 32 readers 113 / 31 ms p50 |
| Super-person `GET` (logged in) | 0.8-1.1 s, 1.86 MB |
| Calendar day / month (API) | 1.1-2.2 s, 2.1-2.6 MB |
| Migration: rename 217 props + index + field | 67-72 s each way, including the read-back of 36-37k items |
| `check-data` (93,470 items) | 135 s |
| `makemigrations` / `migrate` / `setup-database` (no change) | 12-15 s each, nearly all `initialise()` |
| Review: checking 500 factoids one by one | p50 9 ms, p95 19 ms |
| Calendar seed / link | 73,414 days, 24,120 feast edges, 13-16 s each |
| Load, 32 readers (+8 writers) | 479 (301) req/s |

## 5. What worked as documented

- **Security spot checks:** script and event-handler HTML in a label is shown as text on the item, list and search
  pages, and nothing runs. Cypher-looking field names, model names and `order_by` fields in a structured search are
  refused with a 422 that names them; nothing was deleted.

- **Model errors** are early and clear: the `has_type` rule, unsupported annotations.
- **Versions:** 428 without `If-Match`, 412 when stale (with `currentVersion`), 400 for a weak ETag, `*`
  overwrites. Ten racing updates on one version: exactly one 200 and nine 412. 308 and 409 at a parent's route.
  405 on abstract and `create_directly=False` classes.
- **Validation** (422): missing fields, `MinLen`/`MaxLen` on literals and relation lists, a wrong type or missing
  entity in a reference, a Period where a single date is wanted, 30 February, `AtPage` with 0 or 2 targets.
- **Deletes:** `deletable` with `referencedBy`; delete, undelete, and 409 on undeleting what isn't deleted; an
  entity in use is marked; a nested document cannot be deleted alone.
- **Users:** wrong logins all 401; non-admins get 403 on user routes; read-scope tokens cannot write; refresh and
  revoke work; a disabled user is refused; logout-all ends sessions but not personal tokens; a password change ends
  sessions; a short password is refused.
- **`create_inline`** makes a person from inside a factoid; the same URL again reuses it; a class without
  `create_inline` is refused.
- **Field binding** works on the server, through 30 nested Orders, and every level records its spaces.
- **Review:** unpublished factoids are hidden from anonymous readers; `checked` publishes; `errors_found`
  unpublishes and queues the factoid; comments on parts (422 for a part not in the document); resolve;
  `?review_status=checked` on create.
- **History:** the panel and "restore to this point", with a "what will change" confirmation, giving version 3 with
  the old label. The diff of the 200-statement factoid takes 14 ms.
- **Derived facts** follow REST writes, deletes and undeletes within a second. `derive explain`, `dry-run` and
  `status` work.
- **Migrations:** a rename is asked and recorded; the dry run counts the properties; a backward migration demands
  `--backup` or `--no-backup` and takes a snapshot; back and forward both work; writes are refused during a
  migration.
- **Typology:** tree, path, move (a cycle gives 409), rename, view with subtypes.
- **Calendar:** Easter, month, year and day views; seed and link; attach and detach (422 outside the span, 404 for an
  unknown feast).
- **Zotero:** the real library synced (10,129 created and 5,440 unchanged on the second pass, 150 removed); its
  fields are read-only (403); base-on keeps the id and the citations; unlink.
- **Interface:**
  - every main page loads, mostly in 70-250 ms, with chips everywhere and coloured space bands;
  - `headless` `AtPage` shows the source and page with no head bar;
  - the type grid of 68 kinds is grouped by abstract parent;
  - the date menu offers only the kinds a `SingleDateable` allows;
  - a factoid made through the form was stored exactly;
  - a stale save is refused with a clear message;
  - delete explains what refers to an item;
  - the search-by-fields form showed the new field after the migration.

## 6. Experiment: gzip (code changed, uncommitted)

Nothing was compressed. At the user's request:

- `pangloss-api/app.py` now adds Starlette's `GZipMiddleware` (`minimum_size=1000`; event streams are left alone);
- a new `interface-app/serve.mjs` wraps the Solid plugin's generated server and gzips text answers of 1 KB or more,
  flushing each chunk so streamed rendering still streams;
- `pangloss interface serve` runs `serve.mjs`, and its test is updated.

The `pangloss-api` (165) and `pangloss-interface` (163) tests pass and ruff is clean. **Not run:** the whole
`./run_tests.sh`, ty over the repo, e2e. Docs are not updated. The dev server is not changed.

| Answer | Plain | Gzipped |
|---|---|---|
| API calendar day | 2.64 MB | 197 KB (7.5%) |
| API calendar month | 2.40 MB | 197 KB (8.2%) |
| `/openapi.json` | 2.55 MB | 101 KB (4.0%) |
| API super-person | 1.86 MB | 205 KB (11.0%) |
| API list of 500 factoids | 184 KB | 15 KB (8.3%) |
| Interface `/`, `/Person`, `/Factoid/new` | 161-216 KB | 30-36 KB (17-19%) |
| Interface super-person page | 7.85 MB | 539 KB (6.9%) |
| Interface calendar month | 26.3 MB | 1.95 MB (7.4%) |
| Interface calendar day | 12.4 MB | 656 KB (5.3%) |

- **Cost:** compressing 1.86 MB takes 23 ms in the middleware at level 9 (10 ms at 6). End to end it is lost in
  the server's own variance: 0.79 or 1.12 s, either way, over eight interleaved runs.
- **Streaming:** time to first byte of the streamed calendar page is unchanged (8 ms).
- **Hydration:** pages hydrate with no errors; JS and CSS bundles are gzipped, and files under 1 KB are not.

This makes the big pages cheap to send. It doesn't make them cheap to build or to render: #5, #15, #21 and #22 are
still worth fixing at the source.

## 7. Not done, or only partly

- **The SDK** (#1). The data went in through the model API and REST instead, which is what the SDK calls.
- **The production interface with a login.** `serve` has no `/api` proxy, so browser checks used `interface dev`.
  The production build was loaded anonymously and measured, and logged in by setting the session cookie (#20 happens
  there too; the super-person page loads in 2.3 s against 5.2 s on dev).
- **Live sync of the interface's review feed, typology drag and drop, clipboard, stash, retype, sliders** of
  `WeightedAlternative`: not driven in the browser.
- **Neo4j:** only ingest, write scaling and the migration were run, at 1/10 scale.
- **Analytical bulk load** (`memgraph bulk-load`), `restore` of a snapshot: not run. `squashmigrations` only as
  `--dry-run` (#36).
  `history baseline` was run only as `--dry-run` (#35).
- **`run_tests.sh`:** not run in full.

## 8. Left running and where things are

- **Containers (not removed):** `pangloss-memgraph-smoketest` (:7697) and `pangloss-neo4j-smoketest` (:7699).
  `docker stop` or `docker rm -f` them when done.
- **Servers (background processes of this session):** none is running; each stopped at its background time limit:
  - the Memgraph API on :8010: restart with `../.venv/bin/pangloss run --port 8010`;
  - the production interface on :3011: `PANGLOSS_API_URL=http://localhost:8010 ../.venv/bin/pangloss interface
    serve --port 3011`;
  - the dev interface on :3010;
  - the Neo4j API on :8011: `PANGLOSS_SETTINGS=smoketest_site.settings_neo4j ../.venv/bin/pangloss run --port 8011`.
- **Files:** the project in `pangloss-smoketest/`, with `REPORT.md` (this file), `PROBLEMS.md`, `README.md` and
  `smoke_scripts/`. Logs, timings, JSON results and screenshots are in `smoke_scripts/out/` and `out-neo4j/`
  (git-ignored, with `.env`, `.secrets` and tokens).
- **Framework changes (uncommitted):** `packages/pangloss-api/src/pangloss_api/app.py`,
  `packages/pangloss-interface/src/pangloss_interface/cli.py`,
  `.../js/interface-app/serve.mjs` (new), `packages/pangloss-interface/tests/test_interface_cli.py`.

## 9. Second run (2026-11-07, 10:32 to 11:13): deeper models, twice the data

On `full-smoke-test-fixes`, with everything in `FIXES.md` in. Detail, numbers and commands in `PROBLEMS.md`
("Second run", items 37-45).

**Built.** Three new kinds of nesting in `smoke/models.py` (migration `0003_deep_nesting`, applied to the Memgraph
and the Neo4j copies): `Report`, whose `reported` is a `Hearsay[Statement]` space, so reports of reports of orders
of orders nest without limit; `Witnessing`, whose witnesses are reified four deep
(`Attributed[InRole[Identification[WeightedAlternative[Person]]]]`); and `SealedLetter`, with three embedded levels
(`Seal > SealImpression > SealMatrix`). The data was doubled with the same scripts (a second seeded run): now
115,227 entity nodes, 30,228 factoids and 686,164 nodes (410,274 before).

**The data layer holds up.** Everything was stored and read back exactly on both backends, up to 61 documents
deep; field binding still reaches the innermost letter; reverse relations and structured search see through four
reified levels and three embedded levels, with counts that match Cypher; updates keep every nested id. Ingest speed
was the same on twice the data (154/s entities, 52/s factoids), and the mixed load test dropped from 301 to 277
requests a second on 3.4 times the nodes of the first one.

**What broke:**

1. **A model the docs allow cannot be started** (#37): an `Embedded` with a relation, on any document that a
   `FieldBinding` reaches, makes `initialise()` fail with `AttributeError: Create`, so `makemigrations`, `migrate`
   and the server all fail. Here, any `Statement`, because `Order` binds into all of them. Worked round in the
   smoke models.
2. **The interface cannot show or edit deep documents** (#38): "Maximum call stack size exceeded", with nothing
   logged. In the development build the edit page fails at 13 documents deep (8 works); in the production build
   the edit page fails between 21 and 41 deep and the view between 41 and 61. Each nested document costs hundreds
   of synchronous Solid frames.
3. **One request can stop the production interface's server** (#39): the 61-deep edit page kept it at 100% CPU
   for about four minutes, answering nobody.
4. **Deep documents are laid out badly** (#40): every level indents, so past about five levels the text is one
   character wide and spills off the page.
5. **Reading a deep document grows with the square of its depth** (#41), on both backends: 35 ms at 21 deep, 1.1 s
   at 61. Most of it is in Python: a pydantic "before" validator on every model read from the database converts
   the database's types in its whole subtree, so each level converts everything below it again (profiled: 1.39 of
   1.55 s); converting once at the root would make it linear. The query itself is 57-88 ms at 61 deep. The size grows the same way (every nested document lists all the spaces above
   it).

Smaller: adding a `Statement` kind is flagged `[LOSES DATA]` and described in 33 KB (#42); page 1 of the abstract
`Statement` takes 240 ms, seven times the first run, in proportion to its 71,881 items (#43); a list search for
digits or punctuation takes 250-450 ms to find nothing (#44); `/api/search` for a class that is never a head
document silently finds 0 (#45).

**Items of section 7 settled:** `history baseline` has nothing to record on this data (the dry run, 12 min 16 s,
found 0 of 145,451), so a real run was not needed; `migrate --backup` took a snapshot; `check-data` read all 219,101 documents and
entities of the doubled database in 6 min 45 s. Still not done: restoring a
snapshot, the analytical bulk load (it needs an empty database), and driving the clipboard, stash, retype and
sliders in the browser.

**Left running:** nothing. The API (:8010), the dev interface (:3010) and the production interface (:3011) that
this run started were stopped at the end; the containers are as in section 8. Scratch files in `/tmp/smoke-nest/`.

