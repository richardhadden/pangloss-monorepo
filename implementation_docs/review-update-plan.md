# Review update: creators, toolchains, tasks, unreconciled entities, toolchain identifications ✅

**Status: built and tested 2026-11-10 (all six parts), for the spec in [review_update_spec.md](review_update_spec.md).
The plan is as it was written; what differs is in ["As built"](#as-built-2026-11-10) at the end, with what is not
done. The demo's database is not migrated (its migration is written).**

## Decisions (the user's, 2026-11-10)

| Question | Decided |
|---|---|
| What an Unreconciled is | **Part of the document**: one node for each mention, written with the document that holds it. Not an entity. Reconciling rewrites the holding document through the ordinary update (a version, history) |
| How a model allows it | **On the entity class**: `_review_meta = ReviewMeta(allow_unreconciled=True)` on `Person` (inherited): every relation that takes a `Person` also takes an `Unreconciled` whose `unreconciled_type` is `Person`. A field opts out with a marker, `Annotated[Person, NoUnreconciled()]`. (The user's name: not "unreconcilable", which means something else) |
| Several creators in `meta` | **`meta.created_by` becomes a list** of creators everywhere (API, SDK, stubs, history, interface), now, rather than a second field beside a single name. (I recommended keeping the single name; the user chose the breaking change while nothing is published) |
| "Checked" → "Published" | **The value is renamed too**: the status is `published` in storage, API, SDK and CLI, with a migration; `checked` is still accepted where a status is given |
| Confirming an `IdentificationByToolchain` | **It becomes a plain `Identification`**, identified by the person who confirmed it. What the toolchain suggested is in the document's history |
| `Identification.identified_by` | **Filled by the server**: the username of whoever saves it (kept when others edit the document later); in an admin's push for others, the first person named; for a toolchain's, the toolchain |
| Which other unreconciled mentions are offered | **The same or a similar label**: same `unreconciled_type`, label equal after folding (ticked), and near matches found by shared words and scored (shown with the score, not ticked). A rule in the model can narrow them |

Decisions I took, to be confirmed by use (say if any is wrong):

- **A toolchain is a user of kind `toolchain`** (`PGUser.kind`), with no password: it cannot log in. Its version and
  date are on each creation it took part in (properties of the `created_by` edge), not on the user.
- **Only an admin may write in the name of others**, and the admin who pushed is recorded (`meta.uploaded_by`).
  Everyone named must exist; a toolchain must be a user of kind `toolchain`.
- **`updated_by` stays one name** (who made the update). Naming others on an update is not in this build.
- **Tasks are read from the data, not stored beside it.** A document to check, an `Unreconciled` in a document, an
  `IdentificationByToolchain` in a document: each *is* a task while it is there, so nothing has to be kept in step
  with writes, bulk loads, restores or migrations. What is stored is who a document's tasks are assigned to
  (`review_assigned_to` on the head, with who assigned it and when). Assignment is per document: the unreconciled
  mentions and identifications of a document assigned to Ann are Ann's tasks. Anyone may take a task over
  ("pick up": assign it to themselves).
- **Reconciling and confirming are done by the server, at once, on the saved document.** On an edit page with
  unsaved changes the button asks for a save first; after it, the form reads the document again. (One path for the
  item page, the edit page and the review pages; no second version of the work in the form.)
- **"In the background"** for the other mentions chosen: an asyncio task of the API process, one document at a time,
  each an ordinary update by the user who asked. If the server stops, what is left is still unreconciled and is
  offered again. Progress is seen as the list shrinking.
- **A URL that already belongs to another entity is not copied** (a URL is unique): the answer says which were left.

## 1. Creators and toolchains (core, users) 

### Stored

- `(creation:PGCreation)-[:created_by {position, version?, date?}]->(:PGUser)`: one edge for each creator, in the
  order given (people first, then the toolchain). `PGCreation.uploaded_by`: the admin who wrote it, when that is
  someone else. Existing data has one edge and no position: read as one creator.
- `PGUser.kind`: `user` (none stored means `user`) or `toolchain`.
- A nested node's own `meta.created_by` (kept so a part added later says who added it) stays a plain username when
  one person made it, and is JSON text of the list otherwise (one form for both databases; Neo4j holds no list of
  maps).

### Read

`meta.created_by: list[Creator]` on head views and reference views, `Creator = {username, kind, version, date}`;
`meta.uploaded_by: str | None`. The models accept what old data and old callers give (a name, a list of names).
Every query that matched one `created_by` edge collects them (`fragments.creators`).

### Written

- `Create.save(created_by=["ann", "bob"], toolchain=ToolchainRun("MyFancyToolchain", version="1.2", date=...))`, the
  same on the SDK; over HTTP `?created_by=ann&created_by=bob&toolchain=...&toolchain_version=...&toolchain_date=...`
  on `POST /api/<Model>`. Admin only (403); unknown names 422. In core: a ContextVar in `pangloss_users`
  (`acting_creators`), read where the creation record is written, entities made with the document included.
- Toolchains: `service.create_toolchain(name, full_name=None)`, `pangloss users create-toolchain NAME`,
  `POST /api/users/toolchains` (admin), listed with users (`kind`), shown in the admin's Users section and on
  `/users`.

### Tests

Conformance: one creator as before but a list; several creators in order with a toolchain's version and date; refused
for a non-admin over the API, for an unknown user, for a toolchain that is a person; an entity made with the document
has the same creators; lists, search, reference views, incoming relations carry them; a part added by a later update
names its own maker. Users: toolchain cannot log in, has no email. SDK contract tests for the new arguments. Interface:
`Console` shows each creator (a toolchain with its version), Vitest.

## 2. `published` instead of `checked` (review)

`ReviewStatus.PUBLISHED = "published"`; `checked` is read as it wherever a status comes in (API, SDK, CLI, bulk-load
line, the document's own `review_status`). A migration of `pangloss_review` rewrites stored `checked`. Interface words,
guide and docs follow. Tests: the existing review tests with the new value; one that `checked` is still taken; the
migration forward and back on both databases.

## 3. Tasks and assignment (review)

- Head properties `review_assigned_to`, `review_assigned_by`, `review_assigned_at`, kept by an update as the status is.
- `save(review_assigned_to="ann")` on a create (SDK, and `?review_assigned_to=` over HTTP, the review middleware):
  admin only when it names someone else.
- `POST /api/review/{id}/assign {username | null}`: anyone may assign to themselves or unassign themselves; an admin
  to anyone.
- `GET /api/review/queue` gains `assigned_to=` (`me`, a username: admin only for another's, or `none`), and each row
  its assignee. `GET /api/review/tasks/summary`: the counts of each kind (documents, reconciliations,
  identifications), all and mine.
- The Review page: tabs **Documents**, **Reconciliations**, **Identifications**; a filter *All / Mine / Unassigned*,
  and for an admin a choice of user; "Take" on a row.

Tests: conformance for assignment (create with it, assign, take over, kept by an update, refusals), queue filters;
e2e for the filter and taking a task.

## 4. Unreconciled (models core hook, review)

### In the models

- Core: a general hook, **stand-ins** (`pangloss_models.hooks.stand_ins`): a package says "a relation that takes this
  entity class also takes this document class in its place", and checks a value against the entity types of the
  field. The core knows nothing of review. A relation option made this way records which entity types it stands for
  (`stands_in_for`), exported to the interface. A field marker can refuse it for one field.
- `pangloss_review.models.Unreconciled(Document)`: `label`, `unreconciled_type: str` (checked against the field: one
  of the entity types it takes that allow it), `uris: list[AnyHttpUrl]`, and a database-side `label_key` (the label
  folded: case, accents, spacing), indexed. `create_directly=False`. The package gets migrations.
- `ReviewMeta(allow_unreconciled=True)` on an entity class; `NoUnreconciled()` on a field;
  `ReviewMeta(reconcile_together=...)` on a head document class: field names of the head that must hold the same
  entities (`("source",)`), or a function `(mine: HeadView, other: HeadView) -> bool`.

### Service and API (`/api/review/unreconciled`)

| Route | |
|---|---|
| `GET /api/review/unreconciled?type=&q=&assigned_to=&page=` | The mentions, each with the document it is in and its head |
| `GET /api/review/unreconciled/{id}/similar` | Others to do in one go: same type, same or similar label, after the model's rule; each `[chip] in [chip]`, a score, `exact` |
| `POST /api/review/unreconciled/{id}/reconcile` `{entity: {type, id}, also: [ids]}` | Replaces the mention by the entity in its document (an update, as the user), copies its URIs to the entity (none twice; those taken are reported), and queues the others |

Finding similar ones: exact by `label_key` (index); near by the words of the label through the text index, limited to
`Unreconciled` of the type, scored in Python (the ratio of `difflib`, on the folded labels), at least 0.75, at most 50.
No database-specific fuzzy function: the same on Memgraph and Neo4j.

### Interface

- An `Unreconciled` is shown as a chip (type at the left, as any chip) with a **spanner** button at its right, on the
  item page and in the form (`view_card` / `edit_card` of the review module).
- The spanner opens a dialog: search for an entity of the type (the usual autocomplete) or make a new one (the usual
  new-item dialog); then the table of similar mentions with a checkbox each; **Reconcile**.
- `/review/reconciliations`: the same, as a page (the list on the left, the same panel in place of the dialog).
- In a form, the field offers "Unreconciled" beside the entity search, for a person who cannot say who is meant.

### Tests

Models: the option is added for a class that allows it and its subclasses, through traits, unions and wrappers; not
with the marker; `unreconciled_type` refused when the field does not take it; export. Conformance/live (both
databases): create, read, list; similar (exact, near, other type left out, the rule); reconcile (the document's new
version, history event, URIs copied once, a taken URL reported, `also` done, stale ids skipped). e2e: the chip and
spanner on both pages, the dialog (choose existing, make new), the similar table and the background ones, the page,
the form asking for a save first.

## 5. Identifications (library, review)

- `pangloss_library.Identification[T]` (moved from the demo; the demo migrates onto it): `identified_by` filled by the
  server; `target` one item. `IdentificationByToolchain[T](Identification[T])`: `identified_by` is the toolchain (a
  link to its user page), `toolchain_version`, `uris`.
- One in a document is a task. `GET /api/review/identifications?...`, `GET .../{id}/similar` (the same candidates,
  each percentage within 10 points), `POST .../{id}/confirm {also: [ids]}`: the node becomes an `Identification` by
  the user, with the target as saved; with one candidate, its URIs go to that entity; the others chosen get the same
  target, in the background.
- Interface: a **Confirm** button on the block in the form and on the item page (the same dialog pattern: the
  candidates as they are, the similar ones with checkboxes); the tab on the Review page.

Tests: library models; live tests of confirm (class changed, id kept, URIs, similar by candidates and percentages,
en masse); e2e: confirm in the form after correcting, the similar table, the tab.

## 6. Demo, docs, measurements

- Demo: `Person` (and `Group`) allow unreconciled; `Identification` from the library; migration; stubs; `populate.py`
  makes some unreconciled mentions and toolchain identifications.
- Docs: `review.md`, `users.md`, `models.md`/`relations.md` (stand-ins), `api.md`, `sdk.md`, guides, `status.md`,
  `e2e/COVERAGE.md`, the skill.
- **Measured on the large scratch database (about 640,000 nodes)** with some thousands of unreconciled mentions and
  toolchain identifications added: reads and lists after the creators change (against the numbers before it), the
  queue with the assignment filter, the unreconciled list, `similar` (exact and near), a reconcile, a batch of 100 in
  the background, `similar` for identifications. Numbers go in `large-data.md`.

## Order of work

1 → 2 → 3 → 4 → 5 → 6, the tests of each phase passing on both databases before the next.

## As built (2026-11-10)

Everything above is built, on both databases, with these differences and additions.

### Creators and toolchains

- `Creator`, `ToolchainRun`, `creators_asked`, `writing_as` and the ContextVar are in **`pangloss_models.creators`**,
  not `pangloss_users`: a client of the API (the SDK) has the models and not the users package, and `meta` is the
  models'. `Creator` and `ToolchainRun` are exported by `pangloss_models`.
- The creators are known **while the model for the database is made** (`create_head_node` sets them around
  `_to_db_model()`), because a class's `@create_validator` may need them: the library's `Identification` says who
  identified it from them.
- A creator who does not exist, or is named as the wrong kind, is a `PanglossWriteRefused` (422), not the 403 of a
  writer who does not exist.
- `pangloss_users.current_request_is_admin` (a ContextVar, true outside a request) is new: what review reads to
  refuse a non-admin who gives a new document to someone else.
- `service.set_password` refuses a toolchain. A toolchain can be given a personal access token by an admin, as any
  user: nothing stops it, and nothing was built for it.
- Not built: naming others on an **update** (`updated_by` is the one who wrote it).

### `published`

- `checked` is taken where a document is written (`save`, `?review_status=`, the document's own `review_status`, a
  `bulk-load` line), where a status is set (`/api/review/{id}/status`, `pangloss review set`), and as a list's filter.
  A structured search (`where: {review_status: ...}`) needs the new name.
- The stored values are renamed by `pangloss_review`'s migration `0002_review_status_published` (written by hand,
  both dialects, reversible). Until it is applied, a document stored as `checked` reads as `checked`.

### Tasks

- `GET /api/review/tasks/summary` counts with queries of its own (`graph.task_counts`), reading nothing of the tasks.
- `REVIEW_ALLOW_SELF_REVIEW` has no say in reconciling or confirming: they are edits, not checks.

### Unreconciled

- The core hook is **`pangloss_models.hooks.stand_ins`** (a list of `StandIn(document, stands_for, check,
  refused_by)`); the option made is a `RelationToDocument` with `stands_in_for`, exported as `standsInFor`. It
  reaches into wrappers (`InRole[Agent]` takes one in its target), and the value is checked there too.
- `pangloss_review` now says `requires = {"cypher"}`: the tasks are read by its own queries (`graph.py`, through
  `pangloss_core.backend`), not by functions of the backend as the state and the comments are.
- `reconcile_together` as field names reaches an entity through one wrapper (a source *at a page* is the source):
  the demo's `Factoid` uses `("source",)`.
- A mention that is new in a form has no spanner until it is saved (it has no id yet); with unsaved changes the
  spanner says to save first. After reconciling, the page is read again (a reload, a little after the toast).
- Finding similar mentions (`reconcile.similar`): the same label **by the index** of `label_key`, all of them; near
  ones by shared words (at least 3 letters), the most words in common first, at most 3,000 read as (id, label) and
  scored (`difflib`, with its quick upper bounds first), at least 0.75; 50 offered. The first version read every
  candidate whole with a limit of 2,000, and for a common name the limit cut off mentions with the *same* label
  (found by measuring: 2 of 4 exact matches of "john smith" were offered).
- A URI that could not be given (another entity has it, or the entity changed at that moment) does not undo the
  reconciliation: it is reported (`urisTaken`).

### Identifications

- `identified_by` is an ordinary optional field (`str | None`), filled on the models written to the database when
  it is empty, and hidden on forms (`InterfaceMeta(hide_on_forms=...)`). A `DBField` would not do: it is not read
  back, so it could not be shown, or kept by an update.
- An `IdentificationByToolchain` needs its toolchain: from `identified_by`, or from the toolchain the write names;
  with neither it is refused. `toolchain_version` is filled from the write's toolchain.
- `ReifiedRelation.Meta(label_index=True)` is new in the core (an index of the label of a reified relation, a
  migration): the library asks for it for `IdentificationByToolchain`, which review lists whole.
- The button is a **`partActions`** component, a new general hook of the interface (a module's small component
  beside a part of a document, on the item's page and in the form), and a model's `edit_card` now also applies to a
  document that a relation holds (it was for embedded values only): what the form's row of an `Unreconciled` is.
- Review knows the library's classes by name (`IdentificationByToolchain`, `Identification`) and does not depend on
  the library: a project without them has no such tasks.

### After the first build (2026-11-10)

- **A mention is shown as two chips in one**: a rose "Unreconciled", then the type it would be and its label
  (`MentionChip`). In a form a saved one is that chip with a spanner and a ✕, and is not rewritten (no label box, no
  URIs to add); a new one is written as before.
- **Confirm is a yellow tick in the bar of the identification** (`partActions` now says where it is drawn:
  `place`). It confirms at once unless there is something to ask: one candidate who would take URIs (the dialog
  warns, with who and which), or other suggestions that say the same.
- **Nothing is confirmed from `/review/identifications`**: a row leads to the form at the suggestion
  (`/Type/id/edit?show=<part>`; a reified relation in a form has its id to be found by, as a document has).
- **A project's subclass of `IdentificationByToolchain`** is a suggestion too, and becomes the class it names
  (`confirmed_as`, default `Identification`; checked by the library before the models are initialised), keeping
  the fields the two share. A node does not have the label of a generic class its class is made from, so review
  reads each suggestion class by its own label (one class: the plain match that was measured; several: a `CALL`
  of a `UNION ALL`, not measured on the large database), and `label_index` is inherited, for declared classes only.
- **The SDK of a project that allows unreconciled mentions**: a client loads review's `Unreconciled` itself; on a
  server `pangloss_review` still has to be installed. `pangloss dev` does not watch `.pangloss` (the SDK is built
  there as the server starts).

### Measured (2026-11-10)

On the scratch Memgraph of [large-data.md](large-data.md) (the demo's data, 642,551 nodes) with 3,000 witnesses and
12,000 hearings added (24,000 unreconciled mentions, 12,000 toolchain identifications; 732,555 nodes, 145,000 head
nodes), one process, medians of six runs after the first. The numbers are in
[large-data.md](large-data.md#review-tasks-on-a-large-database-2026-11-10). Nothing is slower than 130 ms; three
things were changed because of what was measured (the limit above; lookups by id that scanned a label; a join that
scanned every head node).

### Confirming and reconciling in an edited form (2026-11-11)

As first built, both were requests that rewrote the saved document, so the form refused them while it held changes
("Save your changes first") and read the page again afterwards. Someone checking a document works down it and saves
once, so both are now changes of the form, saved with the rest:

- **Confirm** replaces the part by the identification it becomes (`PartActionProps.replace`, a new prop of
  `partActions` in a form). The server learns of it from the save itself (`Identification.note_if_confirmed`, a
  `@before_update` in `pangloss-library`; `identify.on_write` in review) and gives the stored URIs to the one
  candidate after the write. `POST …/identifications/{id}/give` does the ticked others, in other documents, at once.
- **Reconcile** gives the form the entity (the `editCard`'s `onChange`); `POST …/reconcile` with `inForm` gives the
  entity the URIs and does the ticked others, in other documents, without writing the mention's own document.
- Not offered in either dialog: the similar ones of the same document, which are in the form with buttons of their
  own (writing them on the server would make the form stale).
- Open: the others are done before the form is saved, and stay done if it never is; URIs a form confirm could not
  give (another entity has them) are logged, not said to the person.

### A URI in common, same-document parts, read-only URIs (2026-11-11)

After the user tried the above: a URI in common is asked before any likeness and across the two kinds of part;
what is offered that is in the same document is changed in the form with it; a suggestion's URIs are shown in its
form and not edited. How it is stored and what it costs: [review.md](review.md) ("A URI in common"),
[large-data.md](large-data.md) ("Parts found by a URI"). Open: the index is brought up to date after a write, not in
it (a mark is in the write, so nothing is forgotten, and whatever asks works the marks off first); a project's own
subclasses of suggestion in data from before the index need `pangloss review index-uris` once; with several API
processes two may work off the same marks at once (the second is run again a second later).

### URIs kept by an identification with several candidates (2026-11-11)

Asked by the user: a suggestion with a URI that a person confirms with more than one candidate could not give the
URI to anyone, and lost it. `uris` is now a field of `Identification`, and the identification keeps them in that case;
a later save with one candidate gives them to the candidate. [review.md](review.md) ("URIs kept while there are
several candidates"). Open: once given, they stay on the identification as well; an identification that keeps URIs is
not found by them when another part of the same URI is confirmed or reconciled.

### Not done

- The demo's database is not migrated (`pangloss migrate` in `pangloss-demo/`: the user's to run), and `populate.py`
  makes no unreconciled mentions or toolchain identifications.
- Notices (email) of a task given to someone.
- A task of a part cannot be given to someone apart from its document.
- The background work is in the API's process (not a job of `pangloss-admin`): with several API processes each does
  its own, and a restart drops what is queued (it stays a task).
- The interface's own tests for the new components are browser tests only (`e2e/test_reconcile.py`, and the
  development build in `test_dev_mode.py`); the module has no Vitest for them.
