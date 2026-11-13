# Duplicate entities: merging, identity statements, and documents that cite documents 🚧

Written 2026-11-12 as a proposal; **decisions taken the same day** (see the end). **Built so far: part A, the backend
of a merge, and part B, what is around it** (API, SDK, CLI, proposals, history, `check-data`; 2026-11-12; see "As
built: part A" and "As built: part B"). The interface (part C) and the rest are planned. It answers three questions
of the user's:

1. Two entities that are one by mistake (someone could not find the first and made a second): a merge, which can be
   undone.
2. Two entities that the sources do not show to be one, though further evidence suggests they are: they stay two,
   and a statement says they are the same, with its evidence.
3. If that statement cites other statements as evidence, a document refers to a document it does not contain, which
   Pangloss has so far ruled out. What follows from allowing it.

A fourth, preventing the first kind in the first place ("did you mean…?" when a person is made), is noted at the end
for later. It belongs to [the similarity plan](similarity-plan.md).

## Building this: start here

Parts A, B and C (merging), step 3 (the identity section and `SameEntity[T]`) and step 4 (citations) are built: the
five "As built" sections, next, say what there is and what is still to do. For whoever builds the rest (reading
through identities):

- **Read in this order**: "In short"; then **"Details settled"** and **"Measured before building"**, which are later
  than parts 1 to 3 and the risks and **override them where they differ**; then the part being built; then "Risks
  and safeguards". "Decisions for the user" lists all 32 decisions, every one taken.
- **Build in these parts, stopping after each for the user to look** ("Order of work" has the detail of each step):
  - **A, the backend of a merge**: `KeepOnMerge()` and `IdentityClaim()`; `relink` taking an open transaction; merge
    and undo with the recorded moves (B marked and A written first in the transaction); the `listed` fragment;
    the resolution of merged ids; the conformance tests on both backends, the concurrent ones included.
  - **B, around it**: API, SDK, CLI; proposals and verification; history's `merged` conflict; `pangloss check-data`.
  - **C, the interface**: the comparison page, the undo screen, the notices, e2e.
  - Then, each a piece of work of its own: the identity section and `SameEntity[T]` (step 3), citations (step 4),
    reading through identities (step 5).
- **Three things written here that the user has not yet confirmed in so many words** (ask, or go on with them as
  written): on Neo4j the race of decision 24 is closed by a *delayed* second pass and `check-data`, not by a lock; a
  merge is refused while a bulk load or a migration runs, and gives up after a few retries; each recorded move also
  keeps the node that holds a wrapper.
- **To expect**: `PGMerge` needs indexes, so a backend migration, and the demo database (:7688) will need `pangloss
  migrate` (the user's to run). The time of a merge on Neo4j has not been measured: measure it when part A exists and
  put it in "Measured before building".

## As built: part A, the backend of a merge (2026-11-12) ✅

Where the code differs from the plan below, this section is right.

**What there is.**

| | Where |
|---|---|
| `KeepOnMerge()`, a field marker of the core; `IdentityClaim()`, its subclass in the library | `pangloss_models.markers`, `pangloss_library.identity` |
| `Entity.merge(absorb=, into=, values=, as_class=, version_into=, version_absorb=, allow_large=)`, `Entity.unmerge(merge_id, confirm_migrated=, dry_run=)`, `Entity.merge_preview(...)`, `Entity.merges(id)` | bound from `pangloss_cypher.merge` (`merge_entities`, `unmerge_entities`, `preview_merge`, `merges_of_entity`); `operations.merge_second_pass`, `operations.get_merge` are not bound to the models |
| The rules that need no database: the survivor's class, its default fields, `Entity.Meta(merge=MergeRules(label_into="aliases"))`, the results (`MergeResult`, `MergePreview`, `UnmergeResult`, `MergeRecord`) | `pangloss_models.merging` |
| `hooks.before_merge` (an app refuses by raising `PanglossMergeError`); `WriteEvent.op` `merge`/`unmerge` and `WriteEvent.merge` (a `MergeNote`) | `pangloss_models.hooks` |
| `PanglossMergeError`, `PanglossMergeTooLargeError`, `PanglossMergeBusyError`, `PanglossMergedError` | `pangloss_models.exceptions` |
| `relink_in(tx, ...)`: relink in an open transaction (`relink` is batches of it) | `pangloss_cypher.relink` |
| `fragments.listed(...)` and `fragments.not_merged(...)` | `pangloss_cypher.fragments` |
| The resolution of merged ids in writes (`check_references_exist`, `find_existing_entities`, `survivors_of`) | `pangloss_cypher.validate_write` |
| Settings `MERGE_LIMIT` (1000) and `MERGE_SECOND_PASS_SECONDS` (the database's: Memgraph 0, Neo4j 5) | `pangloss_core.settings` |
| Indexes: `PGMerge(id)` unique, `PGMerge(survivor)`, `PGMerge(absorbed)`, `PGMergeMove(pg_merge)` | migrations `pangloss_memgraph` 0008 and `pangloss_neo4j` 0006. **A database made before needs `pangloss migrate`** (the demo's too) |

**What is stored.**

- B: the property `merged_into` (A's id). Nothing else of B changes.
- `(:PGMerge {id, survivor, absorbed, state, by, when, finished, survivor_type, survivor_type_before, absorbed_type,
  absorbed_label, survivor_version, absorbed_version, before, urls, migrations, heads, moved, dropped, kept, late,
  undone_by, undone_when})`. `state` is `running` (a large merge between batches), `done` or `undone`. `before` is A's
  fields before the merge, as JSON of what its `Update` takes: always kept, whether or not history is installed and
  whether or not the class changed. `migrations` is the last migration of each app when it ran.
- `(:PGMergeMove)`, one for each edge that left B: **the edge's own properties** (so `pg_position` and the properties
  of a `ViaEdge`, copied in Cypher and never through Python), and `pg_merge`, `pg_source` (the node the edge was
  from), `pg_source_type`, `pg_head`, `pg_field`, `pg_reverse`, `pg_dropped`, `pg_holder` (the node that holds the
  source, for one below a head: "Measured", 6), `pg_late` (moved by the second pass).

**How it differs from the plan.**

- **The moves are found from the graph, not from the models**: every forward edge into B from a `PGIndexableNode`.
  The models say only the reverse name of each and which are kept. An edge that is not a relation of the class it
  is from (written around the models) **refuses the merge**; nothing is left unrecorded by not being thought of
  (risk 4). A field that narrows another is two edges, and both are moved and recorded.
- **A preview is the merge itself, rolled back**, when it is under the limit: what it says is what would happen
  (the collapsed heads validated as they would be, the class check, the count). Over the limit it counts only. It
  costs what a merge costs, and takes the same locks for as long.
- **The check of collapsed heads (decision 23) and of the count (risk 4) are made in the merge's transaction**, on
  the documents as the merge left them, and a failure commits nothing. A large merge makes the first check in a
  transaction of its own that is rolled back, before its first batch.
- **Above the limit**: the first transaction marks B, writes A and records the `PGMerge` as `running`; then a
  transaction for each `MERGE_LIMIT` heads; then one that checks nothing is left. If it stops, `merge(...,
  allow_large=True)` of the same pair goes on with it, and `unmerge` takes it back. "Needs an admin" is the API's to
  say (part B): here it is the argument `allow_large`.
- **No lock node.** Both entities' locks are taken first in the transaction (`Dialect.before_replace`, in the order
  of their ids), and each is read again after: of two merges of one pair, or of each into the other, one is made.
- **Giving way.** The driver runs a merge's transaction again for ten seconds when it conflicts; after that it is
  `PanglossMergeBusyError`. A merge decided on no versions that finds A or B changed under it (another merge into
  the same survivor) is prepared again, up to six times with a growing wait; one decided on versions is refused
  (`PanglossVersionConflictError`).
- **The second pass** runs at once after the commit on both databases, and again after `MERGE_SECOND_PASS_SECONDS`
  where that is not 0 (Neo4j), in a task of the event loop that is not awaited (`settle_second_passes()` waits for
  them). What it moves is recorded with the merge (`pg_late`), so an undo puts it back.
- **Undo after a migration** is coarser than planned: **any** migration applied since the merge makes the undo ask
  for `confirm_migrated=True` (a dry run shows what would still go back). Which models a migration changed is not
  looked at, and a renamed field is **not** followed: its moves are listed as `changed`. `pg_holder` is recorded
  and not yet used to find a move again after an unwrap.
- **Undo puts an edge back with the place it has now**, not its recorded place (the list may have been reordered
  since). A dropped duplicate is put back at its recorded place, and only if the node still has the relation to A.
- **Undoing A ← B while A ← C stands**: if C's merge dropped a duplicate from a node whose edge now goes back to B,
  the node keeps A by C's record (which is no longer "dropped"). So `[B, C]` merged twice and undone twice is
  `[B, C]` again.
- **A's fields on undo**: put back only if A's version is the one the merge made and no other merge into A stands;
  if that write is refused (a relation that cannot hold the class it was), the undo is still made and the fields
  are given as a draft with the reason.
- **"Made since"** is the heads that refer to A now, were created or updated after the merge finished, and are not
  among those the undo put back (200 at most).
- **Reads.** `get(B)` gives A as it is, of whatever class (`meta.merged_from` is every id passed through);
  `get(B, follow_merge=False)` gives B (`meta.merged_into`). An entity shown in a document has `merged_into` on its
  reference view. The autocomplete follows up to three merges in the query.
- **`listed` is used by** the lists (plain, by words, deep), structured search, "search everything", the blank
  autocomplete, what refers to an entity, use counts, and a user's items. **Not** by what decides whether an entity
  can be deleted (decision 25), nor by `Entity.references`.
- **Resolved references** are noted for whoever asks (`pangloss_models.merging.noting_resolved()`); the API saying
  so in its response is part B.

**Not built in part A**: what part B built (next section), and what is still to do, listed at the end of that
section.

**Tests.** `conformance/test_merge.py`, `test_merge_reads.py`, `test_merge_writes.py`, `test_merge_undo.py`,
`test_merge_concurrent.py` (72, on both backends), with the models of `conformance/merge_support.py`, which have every
kind of relation to an entity; `pangloss-models/tests/test_merging.py`.

**Not measured.** The time of a merge on Neo4j; the autocomplete with merged entities on the large database; the
preview's cost for a busy entity. The numbers in "Measured before building" are of hand-written Cypher, not of this
code.

## As built: part B, around the merge (2026-11-12) ✅

Where the code differs from the plan below, this section is right.

**The API** (`pangloss_api.routes.merges`; every route needs a login).

| | | |
|---|---|---|
| `POST` | `/api/NAME/{id}/merge/preview` | What the merge of `absorb` (in the body) into `{id}` would do: a `MergePreview`. Nothing is written |
| `POST` | `/api/NAME/{id}/merge` | The merge: a `MergeResult`. 403 for a user who may not merge alone |
| `POST` | `/api/NAME/{id}/merge/propose` | A proposal (201): a `MergeRecord` in state `proposed` |
| `GET` | `/api/NAME/{id}/merges` | The merges the entity is part of, the latest first |
| `GET` | `/api/merges` | All of them (`state=`, more than once; `open=true`: proposed, or proposed to be undone; `page`, `page_size`) |
| `GET` | `/api/merges/permissions` | `{direct, large, limit}`: what this user may do |
| `GET` | `/api/merges/{merge}` | One |
| `POST` | `/api/merges/{merge}/verify`, `/reject` | Carry out a proposal (anyone but the proposer), or reject it |
| `POST` | `/api/merges/{merge}/undo` | Undo (`dryRun`: say what would be undone; `confirmMigrated`) |
| `POST` | `/api/merges/{merge}/undo/propose`, `/undo/reject` | Propose that it be undone; reject that |

- The body of a merge: `{absorb, values?, asClass?, versionInto?, versionAbsorb?}` (and `note` on a proposal).
  `values` is what the survivor's `Update` takes. Results have camelCase keys (`pangloss_models.merging.to_wire`),
  and the fields of an entity inside them (`values`, `draft`) are as the API gives any entity.
- **The undo is at the merge**, `/api/merges/{merge}/undo`, not at `/api/Person/{A}/merges/{merge}/undo` as planned:
  the id of a merge says which entities it is of.
- **The routes are on abstract entity classes too** (`/api/Agent/{id}/merge`): two entities of sibling classes are
  merged at the class they share.
- **Statuses**: 409 a merge that cannot be made as things are (`PanglossMergeError`), and a write addressed to a
  merged entity (`PanglossMergedError`, with `mergedInto`: decision 19); 412 a version that has passed; 403 not for
  this user (`PanglossMergeNotAllowedError`) or over the limit for one who is not an admin
  (`PanglossMergeTooLargeError`, with `heads` and `limit`); 503 with `Retry-After` when the entities are being
  written (`PanglossMergeBusyError`).
- **Fields that something else keeps up to date** (`Protection(read_only=...)`, a Zotero item's) cannot be changed
  by the `values` of a merge: 403, as for an update.
- **Reading B**: `GET /api/Poet/B` gives A as it is, with `meta.mergedFrom` and `Content-Location: /api/Person/A`
  (decisions 2 and 27).
- **A write that named a merged entity** says so in the header `Pangloss-Resolved-References: B=A, …` (create,
  update, create with companions); a restore from history says it in its body (`resolved`). Both headers are
  exposed to browsers (CORS).

**Who may** (`MERGE_DIRECTLY`: `"admin"`, the default; `"any"`; `"none"`).

- Those the setting names merge and undo alone. Everyone else proposes, and **a different logged-in user** verifies
  (or accepts the undo). The rule that it be a different user is the storage's (`verify_merge`, `unmerge(...,
  accepting=True)`), so it holds in the SDK and in a race, not only in the API.
- A merge over `MERGE_LIMIT` is made only for an admin, whatever the setting says (the API passes `allow_large` for
  an admin), or from the command line.
- A dry run of an undo, a preview and the lists are for any logged-in user.

**Proposals** (`pangloss_cypher.merge`: `propose_merge`, `verify_merge`, `reject_merge`, `propose_unmerge`,
`reject_unmerge`, `list_merges`; `Entity.propose_merge` is bound to the models, the rest are operations of the
storage).

- A proposal is a `PGMerge` in state `proposed`, with `proposed_by`, `proposed_when`, `note`, the fields chosen
  (`proposed_values`), the versions of the two entities and the migration state. Proposing runs the whole preview,
  so a merge that could not be made is never proposed.
- **Verifying uses the proposal's own record**: it becomes the merge's (`by` is the verifier, `proposed_by` stays).
  Of two who verify at once, one carries it out and the other is refused.
- **If A or B changed since the proposal**, verifying with the fields proposed is refused (412): the verifier looks
  again and sends the fields, with the versions they were decided on. With fields sent, the proposal's are not used.
- States besides those of part A: `proposed`, `rejected` (kept, with who and why), `stale`. A proposal becomes
  stale when one of its entities is absorbed by another merge (set in that merge's transaction), or when the
  database has been migrated since it was made (found when someone verifies it: decision 26).
- **An undo is proposed on the merge itself** (`undo_proposed_by`, `undo_proposed_when`, `undo_note`), after a dry
  run has shown it can be made. Rejecting clears them and records `undo_rejected_by` and the reason; it can be
  proposed again.

**The SDK** has the same functions as requests (`Person.merge`, `unmerge`, `merge_preview`, `merges`,
`propose_merge`; in `exposed_functions` also `get_merge`, `verify_merge`, `reject_merge`, `propose_unmerge`,
`reject_unmerge`, `list_merges`), giving the same dataclasses and raising the same errors. `allow_large` and
`accepting` are the server's to decide, by who the user is. `Poet.get(B)` where the survivor is not a `Poet` raises
`PanglossMergedIntoOtherClass`, with the survivor's `reference` (decision 27).

**The command line** (`pangloss_cli.merges`): `pangloss merge TYPE SURVIVOR ABSORBED --user U` (`--pairs FILE`,
`--as CLASS`, `--large`, `--dry-run`), `pangloss unmerge MERGE_ID --user U` (`--dry-run`, `--confirm-migrated`),
`pangloss merges`. They merge directly: who may run a command on the server is not `MERGE_DIRECTLY`'s to say.

**History** (`pangloss-history`).

- The absorbed entity has a record `merge` (and `unmerge`), with the version it had and no content; the survivor's
  side is an `update` at the version on the merge's record (`survivor_version`); each head moved is an `update`.
- **The `merged` conflict**: restoring the absorbed entity at all, or the survivor to a version below the merge's,
  is refused (409, kind `merged`, with the merge's id) while the merge stands. The draft route lists the same
  problem. After an undo both are allowed.
- A restore of a document that named B is written with A (as every write), and B is not touched or undeleted; a
  `KeepOnMerge()` relation is restored as it was. If the survivor is deleted, the restore is refused naming it.
- The version of a merged entity that history's routes show is its own, not its survivor's.
- **Found on the way and fixed**: a version of an entity whose class takes its id from outside (`create_with_id`)
  could not be restored at all, because the recorded write form has `create_new`, which an `Update` refuses. The
  draft now leaves it out.

**`pangloss check-data`** also reports every reference that is on a merged entity and that a merge would have moved
(`stray_references`: not `KeepOnMerge()` fields, not the two entities' own), with the head it is in, and the large
merges that stopped (`unfinished_merges`). `--move-merged --user U` moves the first (each merge's second pass, in the
order the merges were made, so what is on an entity merged twice over ends on the last survivor; each move is
recorded and an undo puts it back). It exits with 1 if anything is left.

**The add-ons.**

- **Typology**: a type that has subtypes is refused (`before_merge`): it is merged by its typology. A type without
  subtypes is merged as any entity is, into a type of the same typology, and can be brought back. The typology's
  tree and its lists use `listed`, so a merged type is not in them.
- **Zotero** (decision 28, and the case of two linked items): an item of the library is never the one absorbed.
- **Review, calendar, derived, RDF**: nothing changed. Their own queries read documents, which are not merged, or
  derived facts, which are made again.

**The bulk load** needed nothing: the analytical load is only for an empty database, where nothing is merged, and
it holds the migration lock, under which a merge is refused as every write is. The ordinary upload
(`pangloss_models.bulk_upload`) saves through the models, which resolve merged ids.

**Still to do** after part B (the interface is part C, next section).

- Proposals in the review queue (the general hook is not made).
- RDF: `owl:sameAs` for a merged entity.
- "Search everything" finding a survivor by an absorbed label; the label worked out again after a change of class.
- The undo's following of renamed fields after a migration (part A's coarser rule stands).
- A migration that removes a class is not refused while a merge of that class stands (risk 2, last point).

**Tests.** `conformance/test_merge_proposals.py` (16), `test_merge_api.py` (9), `test_merge_sdk.py` (4),
`test_merge_check_data.py` (5), `test_merge_cli_live.py` (4), `test_history_merge.py` (6), on both backends; one
each in the typology's and Zotero's live tests.

## As built: part C, the interface (2026-11-12) ✅

Where the code differs from the plan below, this section is right.

**Where it is.** The pages are an **interface module that `pangloss_interface` itself ships**
(`packages/pangloss-interface/src/pangloss_interface/interface/`, module name `pangloss_interface`), not code in
`interface-core` or the application. A merge is the core's business in Python; in the interface it needs only what
every module has (routes, a console action, a part of `/admin`, its words), so it uses those hooks, is loaded only by
the pages that show it, and a project can turn parts of it off (`InterfaceConfig(disabled=["pangloss_interface:Merge"])`).
A project has it whenever `pangloss_interface` is in `INSTALLED_APPS`.

| | |
|---|---|
| **Merge with…** in the console of an entity's page (`consoleActions.Merge`) | A dialog with the search box of a relation field (`EntityPicker`, now exported from core), over the entity's whole family of classes; under it, the merges the entity is part of. Picking one goes to the comparison |
| `/:type/:id/merge/:other` (`ComparePage`, `Comparison`) | The comparison: the entity that stays, the one absorbed, and what the survivor is to have |
| `/merges/:merge` (`MergePage`) | One merge: a proposal (the comparison again, to verify or reject), a merge that stands (the undo screen), or what became of it |
| `/merges` (`MergesPage`), linked in the navigation bar for someone logged in (`pangloss_interface/interface_config.py`) | The merges, those that wait for someone first (`?show=all`, or a state) |
| Notices above an entity's contents (`itemNotices.Merges`) | A merge proposed; an undo proposed; "X was merged into this" |
| On `/admin` (`slots.admin.Merges`) | The ten merges made last, following a live feed (`feed.ts`), each leading to its page |
| The job `check_merged` on `/admin` (`pangloss_interface/admin.py`) | Counts the references left on merged entities and the merges that stopped, and writes them to a file |

**New in the core, and general.**

- **`itemNotices`**, a manifest hook like `itemSections` but drawn *before* the item's contents, under its heading
  (`<ItemSections place="before">`, first in the item page's `Reveal`). The identity section of part 2 will use it too.
- **The page of an entity that was merged shows its survivor's address**: the item page sees `meta.mergedFrom` and
  replaces the address with `/Type/A?merged=B` (in the browser; the server sends the survivor's page under the address
  asked for). The notice reads `merged` to say how the reader came there.
- `EntityPicker` is exported from `interface-core`.

**The comparison page.**

- It reads each entity as its own class edits it, the preview, and what the user may do. The rows are the fields of
  the class the survivor is to have that either entity has something in. Each row offers **Stays**, **Absorbed**, and
  for a list **Both**; the label has the two and a box to type in. What the API suggests that is none of those (the
  absorbed label put among the aliases by `MergeRules(label_into=...)`) is a fourth choice, **Suggested**.
- **The choices are whole values, not an editable form.** The plan's "third column, editable" is a choice for each row
  and a typed label; a value that is neither entity's is made by editing the survivor afterwards.
- The logic has no DOM (`compare.ts`, 23 Vitest tests): a reference to an entity is known by its id, anything else by
  what it holds; a node of the absorbed entity (an embedded date) is given to the survivor without its id, so it is
  made anew; neither entity appears in the other's fields (decision 22). Fields that something else keeps up to date
  (`readOnly`) have no row.
- **The class** is the first row when the two differ: the class the API suggests, and each entity's own. Changing it
  asks for the preview again and starts the choices again. Fields the class chosen does not have are named as not kept.
- Under the rows: how many of each type refer to each (the ten largest kinds), the documents that name both, how
  many documents the merge writes, why it cannot be made (if it cannot), and "more than the limit" for someone who is
  not an admin.
- **Merge** (for those `MERGE_DIRECTLY` names) asks again in a dialog that names both. Everyone else has a note and
  **Propose the merge**. The versions of both are sent: a 412 says so and shows the two again as they are.
- After a merge the page says what it did, with the documents that named both as chips to look at.

**A proposal** (`/merges/:merge`, state `proposed`) is the comparison with what was proposed as its starting choices
(if neither entity has changed since; otherwise the rows are as they are now, and the page says so). **Verify and
merge** sends the fields on the screen with the versions; the proposer sees it disabled and may **withdraw**; anyone
else may **reject** with a reason.

**The undo screen** (`/merges/:merge`, a merge that stands) asks the API for a dry run and shows: how many days old
the merge is and what it moved; how many references go back; those that cannot, each with why; what was written to
the survivor since, as chips, which stay on it; whether the survivor's own fields go back, or what they were before
(the draft, with the reason). Then **Undo the merge** (a dialog first), or, for someone who may not undo alone, a note
and **Propose undoing it**, which someone else accepts by undoing or rejects ("Leave it merged"). If the database was
migrated since the merge, the dialog says so and the undo is asked for a second time.

**Differences from the plan, and not built.**

- **No "move to B" action** in the list of what was written to the survivor since the merge: the documents are chips
  to open and change by hand.
- **The admin job only reports.** A job does not record who started it, and moving references is a write made by
  someone: `pangloss check-data --move-merged --user U` moves them.
- **History's panel names a `merge` and an `unmerge` record** ("Merged into another", "Merge undone", each with an
  icon), but has **no undo button**: the undo is reached from the notice, the console's dialog and `/merges`. The
  panel of the absorbed entity is not reachable in the interface while it is merged, since its page shows the
  survivor.
- **The autocomplete does not mark "(merged: B's label)"** in its results: the API sends `mergedLabel`, and no picker
  shows it yet.
- What refers to each entity is counts by type, not chips on demand; the entities' own pages list it.
- A document shown inside the pages that names an absorbed entity under `KeepOnMerge()` has no "merged into A" mark
  on its chip.
- The merge pages of an entity whose class has its own `item_page` (a typology's type) are the same generic ones.

**Tests.** `e2e/test_merges.py` (5: merge and undo as an admin; propose, verify, propose an undo and reject it between
two users; reject a proposal; nothing for someone logged out or for a document; the admin section and job),
`e2e/test_dev_mode.py::test_merging_two_entities`, the module's Vitest tests in the built project
(`test_module_unit_tests.py`), `ItemContents.test.tsx` (the notices hook), `test_interface_modules.py`.

## As built: the identity section and `SameEntity[T]` (step 3, 2026-11-12) ✅

Where the code differs from part 2 below, this section is right.

**`SameEntity[T]`** (`pangloss_library.models`) is a `ReifiedRelationDocument[T]`: `target: Annotated[list[T],
MinLen(2), MaxLen(2), IdentityClaim()]` and `argument: str | None`. A document cannot be generic, and this kind can:
it has a label, goes in a list of statements (`statements: list[Statement | SameEntity[Person] |
Negative[Statement | SameEntity[Person]]]`), and is written with what holds it. So its field is `target`, not
`entities` as in the sketch below, and it has no `evidence` (that is part 3). A project's own statement class with
a relation marked `IdentityClaim()` (`SameAs.entities`) works as well. The demo's `Factoid.statements` takes
`SameEntity[Person]`, plainly and in `Negative` and `Hypothetical`. The class has a migration of the library
(`pangloss_library` 0004), and the demo's change one of its own (`demo_app` 0018): **a project that has the library,
the demo too, needs `pangloss migrate`** (the demo's is the user's to run).

**The marker reaches the interface.** A relation's markers are now exported (`markers`, only where there are any;
migrations do not see them): `KeepOnMerge()` says `keepOnMerge`, `IdentityClaim()` also `identityClaim`. The
interface asks that, not the marker's name, so a project's subclass of the marker works.

**The section** is an `itemNotices` entry of the library's interface module (`IdentitySection`), above an entity's
contents. It needs no configuration and no route of its own: it reads the entity's reverse fields
(`/api/Type/{id}/incoming/{field}`), and only those in which a claim can be (`identityIncoming`: none for most
classes, so nothing is asked). Two shapes are read (`identity.ts`, 16 Vitest tests):

- a statement held like a reified relation (`SameEntity`, in a factoid's `statements`): the reverse field has the
  document at the top and the chain down to the statement, through any semantic spaces, with both entities;
- a document's own relation (`SameAs.entities`): the reverse field has the statement without its fields, so each is
  read once more for the entities it names.

It shows, for each other entity, its chip, how many statements say so, and on demand the statements (each a chip to
its place in its document, with the argument). Those said plainly come first, under "Said to be the same as"; those
in a semantic space come under the space's name ("Said to be the same as, in Negative"). **The section does not know
what a space means**: it names it. An entity that is in both is marked "said otherwise too". One that has since been
merged is still named, as "merged into this", which is the record of why. For someone logged in, each has **Compare,
or merge**, which is the comparison page of part C.

**Found on the way and fixed:** what a wrapper holds was read from the reverse side in any order (Neo4j gave `[C, A]`
for `[A, C]`); it is now in the order written (`read_incoming.fetch_held`).

**Not built** (they belong to step 5, reading through identities): the cluster, its size and its warnings (risk
8); "C, through B"; the derived relation; the page toggle; the search operator. Also: the section reads the first
100 of each reverse field and says when there are more; the comparison reached from it is the editable one, not a
read-only view.

**Tests.** `conformance/test_same_entity_live.py` (5, both backends: written and read, exactly two of its class,
found from each entity with its space, a merge and an undo leave the claims naming both, the export),
`e2e/test_identity.py` (2), `e2e/test_dev_mode.py::test_what_an_entity_is_said_to_be_the_same_as`, `identity.test.ts`.

## As built: citations, `Cites[T]` (step 4, 2026-11-12) ✅

Where the code differs from part 3 below, this section is right.

**The model.** `evidence: list[Cites[Statement]]` (`pangloss_models.Cites`; one, `Cites[Note] | None`, or a union,
`Cites[Note | Factoid]`). A citation is a node of the citing document, `PGCitation`: **a nested document as any
other**, of a class that Pangloss declares the first time a `Cites[...]` is written (a project without citations has
no such model). So the write plan, the tree read, history's snapshots, the export, migrations and the forms know it
without being told, and what is particular to it is small. It is written as a reference is, `{"type": "Birth", "id":
"…"}`, or in full as it is read. Its fields:

- `target_id`, `target_type`: what is cited;
- `changed_since_cited`: an ordinary field, **sent back as it was read**. It is set when what is cited is changed, and
  stays through saves of the citing document until one sends it false. That is how a person says they have looked;
- set by the write, whatever is sent: `target_head_id`, `cited_version`, `cited_hash`, `cited_label`;
- worked out by a read and never stored: `target_label`, `target_head_type`, `target_head_label`, `target_spaces`,
  `target_state` (`there`, `removed`, or `hidden` for a reader who may not see an unpublished document: nothing else
  of it is given).

The class is in no app: its migration (the model and the indexes on `target_id` and `target_head_id`) goes to the app
of a model that uses it (`planner.owner_of`). `Document.Meta(cited_with=["source"])` is decision 29.

**Checked when written** (`pangloss_cypher.citations.record`, after the tree is written, in its transaction): the
target is a document node of a class the field allows, in a head that is not deleted (`PanglossReferenceError`, a
422). The cited head is written to (`pg_cited`) before it is read, which is decision 30.

**The protection compares two readings, not a stored hash** (a departure from the plan, and the reason risk 7 needs
no code). Before a head is written again, who cites it is found by the index, and the normal form of each cited
part is read; after the write it is read again, in the same transaction. They differ: `PanglossCitedError` (409, with
the citing documents and a `fix`), unless the write says `acknowledge_citations` (`save(acknowledge_citations=True)`,
`?acknowledge_citations=changes`, or a `with acknowledging("changes"):` block), and then each citation is marked. The
part is gone: refused even so, unless `acknowledge_citations="removals"`, which the API lets only an admin send
(403). Because both readings are made at one moment by the same code, a merge of entities, a migration or a change
of codec cannot make a citation look changed; `cited_hash` is kept as a record only.

- **The normal form**: the fields the models declare (not `DBField`s, not the ids of nested nodes, not a label that
  is worked out from a template), entities by id and once in a list, and the head's `cited_with` fields.
- **A delete** of a cited head is refused in the same way, and `/deletable` says so, with the citing documents.
- **Citations from deleted documents do not count; those from unpublished documents never refuse** but are marked.
- **A document's citations of its own parts** are written with them, so need no acknowledgement; removing the part
  is a citation of nothing, and is refused.
- **A removal an admin overrode** leaves the citation, which reads `removed`; the citing document can still be saved
  as it is; `pangloss check-data` and the admin job list such citations (as a note, not an error).
- **A restore** (history) is an update: the same refusal, and `?acknowledge_citations=` on its route.

**Who cites what**: `Document.cited_by(id)`, `GET /api/NAME/{id}/cited` (of a head, or of a part), in the SDK too.

**The interface** (in the core: `Citation.tsx`). A citation is shown as the cited document's chip, in the bands of
its spaces, linked to its place (`?show=`), with its document as a second chip, and "changed since cited" or "removed
since cited". In a form it is chosen, never typed: a search of every document, then the parts of the one found that
may be cited here. A document that is cited says so above its contents, and in its form. **The form does not lock
what is cited** (the plan's badge, read-only fields and "Edit anyway"): it saves, and if the server refuses, a dialog
names the citing documents and offers **Save anyway** (or, for a removal, only an admin's **Remove anyway**). The
server then decides what counts as a change, and nothing in the form has to guess. "Seen" on a marked citation takes
the mark off when the citing document is saved.

**The demo** has `Inference(Statement)` with `evidence: list[Cites[Statement]]`, and `Factoid` is `cited_with` its
source (`demo_app` 0019: the demo database needs `pangloss migrate`, the user's to run).

**Not built**: the lock in the form (above); "Cite…" from the cited document's own page, through the clipboard;
↧/↥ and cut refused beforehand (the save refuses them); a link from "changed since cited" to history's compare page;
a refusal of a migration that removes a cited class; an RDF triple between the two documents (a citation is exported
as the nested document it is); a search operator or a derived rule that follows citations (`evidence={"target_id":
…}` works, as for any nested document); the analytical bulk load checks no citations; stubs give a `Cites` field of
a generated model as `Any`. **Not measured**: the cost of the two readings on a large cited factoid.

**Tests.** `pangloss-models/tests/test_citations.py` (7), `conformance/test_citations.py` (15, both backends: written
and read, the checks, self-citation, what counts as a change, removal and delete, the override, deleted and
unpublished citing documents, a merge changes nothing, and three of simultaneous writes: a citation racing a
removal, racing a change, twelve citing at once), `conformance/test_citations_api.py` (6: the API, the SDK,
`check-data`), `e2e/test_citations.py` (4), `e2e/test_dev_mode.py::test_citing_a_part_of_another_document`,
`Citation.test.tsx` (4).

## Contents

- Building this: start here
- As built: part A
- As built: part B
- In short
- What Pangloss does now, and what it rules out
- Part 1: merging entities, and undoing a merge
- Part 2: identity statements (two entities said to be one)
- Part 3: a document that cites a document
- Risks and safeguards
- Details settled (decisions 16 to 32)
- Measured before building
- Alternative considered: merging by pointer (rejected)
- How the three fit together
- Prevention: "did you mean…?" (later)
- Order of work
- Decisions for the user

## In short

- **Merge** (part 1) is an operation, not a model. It moves what refers to the *absorbed* entity B onto the *survivor*
  A, writes A's fields as the person chose them on a comparison page, and leaves B **untouched but marked
  `merged_into` A**. It is a new state, not a deletion. It is recorded as a `PGMerge` node that lists every reference
  it moved. **Undoing** puts those references back on B (those that still exist), clears B's mark, and restores A's
  fields from its history. B's id and URLs keep working: they resolve to A while the merge stands. This rests on what
  already exists: `pangloss_cypher.relink` (typology merges use it), history, and the restore-as-draft dialog.
- **Identity statements** (part 2) need almost nothing new in the model layer. A project declares them as it declares
  any statement (`SameAs(Statement)` with two `Person` fields). What is new is general: (a) a field marker in `Annotated[...]`, `IdentityClaim()`, that
  says a relation is the claim of identity, so a merge does not move it and a statement "A is B" does not become "A is A"; and
  (b) an item-page section, at the top, that lists the entities this one is said to be (or not to be) the same as,
  with the factoids that say so. Following those links in queries is opt-in, through `pangloss-derived` and a search
  operator. Nothing is rewritten globally.
- **Document citing document** (part 3) is possible. It needs a new kind of relation (`Cites[Statement]`, pointed at
  by `{type, id}`). As revised, it is stored as **an id on a small node of the citing document**, indexed, and **not
  as an edge**. Saving the cited factoid tears down and rebuilds its tree, and with an id nothing points into that
  tree, so the update needs no change. A **cited statement is protected**: an edit that changes or removes it is
  refused (409, naming who cites it) unless the person confirms a strong warning. A removal is refused outright, and a
  confirmed change marks the citation "changed since cited". History, review, migrations, RDF and the interface each
  need small changes.

## What Pangloss does now, and what it rules out

Facts this proposal depends on (checked in the code, 2026-11-12):

- **Entities are referred to; documents are contained.** A relation to a `Document` takes its `Create`, nested. "A
  document cannot refer to a document that is not contained in its own head document"
  ([autocomplete.md](autocomplete.md)), and history relies on this: "nothing else refers to a nested document (only
  entities are referred to by id). One snapshot of the head node's payload therefore holds all of them"
  ([history.md](history.md)).
- **An update replaces the whole document**: `build_update_query.py` deletes the owned edges and
  `DETACH DELETE`s every node of the tree, then writes it again with the same ids. Any edge *into* a nested node from
  outside would be lost on every save.
- **Relinking exists.** `pangloss_cypher.relink(field, reverse, from_id, to_id, keep=...)` moves every edge of a field
  from one node to another, 1,000 heads per transaction. Each head it changes gets a new version and a write event
  (history records it, derived marks it pending). Edge properties and list positions are kept. **A node that already
  has the relation to the target keeps the edge it has**: a list `[A, B]` becomes `[A]`. Typology's `merge` uses it.
  `derived.md` already names "a merge of entities" as a kind of write.
- **Delete is a flag.** A deleted entity is not found and cannot be referred to anew. A restore of an old version
  that refers to it undeletes it. "Deleted entities refer to nothing" in structured search.
- **Review comments refer to document parts** by `#<uuid>` in their text, shown as a chip and struck through when the
  part is gone ([review.md](review.md)). This is a soft reference, not an edge.
- **Zotero** already joins two nodes in one case (`link-merge`). The node something refers to is kept, and the link
  is refused if both are referred to ([zotero-sources.md](zotero-sources.md)). The user chose not to re-point
  references then. A general merge has to re-point them.
- The library has `Identification[T]` and `IdentificationByToolchain[T]` (who identified a mention as which entity)
  and review has `Unreconciled` (a mention not yet identified). These are about *mention → entity*. Part 2 is about
  *entity ↔ entity*, which nothing models yet.

## Part 1: merging entities, and undoing a merge

### What a merge does

`Person.merge(absorb=B, into=A, values=...)`, the API `POST /api/Person/{A}/merge` with `{absorb: B, values, version_a,
version_b}`, and a comparison page in the interface. In one operation:

1. **Checks** (refused with a message, nothing written):
   - A and B are of the same class, or B's class is a parent or subclass of A's. A `Person` and a `Group` cannot be
     merged, but a `Person` and a `Poet(Person)` can. The survivor's class is the narrower one, or the person
     chooses (decided 2026-11-12; see "When the classes differ").
   - Neither is deleted, merged, or the same entity.
   - Every relation into B can point at A: a field that allows only `Poet` cannot take a plain `Person`. This is
     checked over B's incoming relations before anything moves.
   - A package may refuse (a `before_merge` hook, like `before_update`). Typology: types with subtypes go through
     typology's own `merge`, which handles the hierarchy. Zotero: two items both linked to the library.
   - The versions given are current (`If-Match` style), so the comparison page was not stale.
2. **Records the merge first**: a `(:PGMerge {id, survivor, absorbed, by, when, state: "running"})` node. Then a merge
   that stops half way (relink runs in batches) can be resumed or rolled back. The merge is not atomic for an entity
   with thousands of references, and this is how that is made safe.
3. **Moves the references** with `relink`, field by field over B's incoming relations. For each edge it moves it
   records, on the `PGMerge` (as rows in a compressed property, or as `PGMergeMove` nodes):
   `(source node id, head id, field, list position, edge properties, whether a duplicate edge to A was dropped)`.
   Edges cannot be recorded by their own identity, since an update deletes and re-creates them. Nested node ids are
   stable, so the source node id plus the field is what identifies a reference across later saves.
   - **Relations marked `KeepOnMerge()` are not moved** (`IdentityClaim()` is one; see part 2). They keep pointing at B, which is shown as
     "B, merged into A".
   - **Duplicates.** A document that refers to both A and B in one list ends with A once (relink's rule). The dropped
     edge is recorded so an undo can put it back in its place. A factoid listing both, for example as two
     witnesses, now names one witness where it named two, so the merge's summary lists these documents for a person
     to look at (decided).
4. **Writes A's fields** as chosen (below), as an ordinary update of A, so that A's history has a version "merged with
   B".
5. **Marks B** `merged_into: A`: a property on B holding A's id, and **no edge** (decision 18). It is set first in
   the merge's transaction, before any reference moves (decision 24). B's own properties and outgoing
   relations are **left as they were**. Nothing of B is lost, and undoing has nothing of B to rebuild.
6. **Moves B's URLs** (`PGUrl`) to A, recorded (done before step 4: see "Details settled"), so that a lookup or a batch upload naming B's external URL finds A.
7. Sets the `PGMerge` to `state: "done"`, emits a write event `merge` (history records it for both, derived marks
   both pending), and announces it on the live feeds.

### When the classes differ (decided 2026-11-12)

**Decided by the user:** the survivor takes the narrower class by default, and the person merging may choose.

- **The survivor keeps A's id**, whatever its class. If it takes B's narrower class (A a `Person`, B a `Poet`), A's
  class changes in place, with the operation built for Zotero (`Update(...).save(changing_class_from=Person)`,
  entities only), in the merge's write of A.
- **The comparison page** has the class as its first row. Changing it redraws the rows: the narrower class's own
  fields (a `Poet`'s `works`) are filled from the entity that has them. If the survivor takes the *wider* class, those
  fields are listed as "not kept" (still on B, or in A's history).
- **Narrower is always safe for references**: everything that pointed at a `Person` can point at a `Poet`. **Wider is
  not**: a field that takes only `Poet` cannot point at a `Person`. So when the chosen class is not the narrower,
  A's incoming relations are checked too, not only B's, and the merge is refused naming the fields (as
  `changing_class_from` already refuses, with `PanglossClassChangeError`).
- **Undo**: history refuses to restore a version from before a class change (`class-changed`), so undoing cannot
  restore A through history. The `PGMerge` therefore keeps A's class and its fields as they were (the `UpdateDB`
  payload) whenever the class changed, and the undo changes the class back with `changing_class_from`, checking the
  references again. If A was edited since the merge, the undo shows the kept fields beside A's current ones for the
  person to reconcile, as restore-as-draft does.
- **The label** is worked out again if the survivor's class has a `label_template` and the label was not written by
  hand.
- **Classes that are siblings** (a `Poet` and a `Soldier`, both `Person`s, neither a parent of the other; decided):
  the survivor takes a class that is both, if the models have one (`class PoetSoldier(Poet, Soldier)`; the narrowest
  such, and the person chooses if there are several). Otherwise the merge is refused, saying to change one entity's
  class first, which the comparison page offers.
- **Classes related only by a trait** (a `Person` and a `Group`, both `Agent`s) are refused: they are different kinds
  of thing.

### The comparison page

`/Person/A/merge/B` (and a console action "Merge with…" on an entity page that opens a picker of the same class):
two columns, one row per field, and a third column, the result, editable.

| Field kind | Default | Choices |
|---|---|---|
| `label` | A's | A's, B's, or typed |
| A single literal, embedded object (`Date`) or annotated value (`WithCertainty[str]`) | A's, or B's if A's is empty | A's, B's |
| A list of literals (`aliases`) | **both, without repeats** | A's, B's, both |
| A list of relations (`has_type`) | both, without repeats | A's, B's, both |
| A single relation | A's, or B's if A's is empty | A's, B's |
| URLs | always both | none |

Under the rows: a count of what refers to each ("A: 12 factoids; B: 3 factoids, 1 group"), as `ReferenceChip`s on
demand, and the documents that refer to both.

**Losing values.** A value not chosen is not lost: it stays on B, and B is kept. But it no longer shows, since B is
hidden. Two ways to keep names visible:

- **A project rule** saying where B's values go. A class option `Entity.Meta(merge=MergeRules(label_into="aliases"))`,
  or a function, so that the absorbed label goes into `aliases` by default. The comparison page shows the result, and
  it can still be changed.
- **No duplicated fields** of the "merged-from" kind on A. The user expected these to be bad, and they are: after
  three merges a person has three copies of every field. Rejected.

### Reading a merged entity

- `GET /api/Person/B` gives **A**, with `meta.merged_from: [B]` and a header saying so (**decided**, 2026-11-12). The interface's page for B redirects to A and says "B was merged into this person on …, by …:
  undo".
- **Lists and search** leave B out, as they leave out deleted entities (a new `listed` fragment, which is `visible` and
  `merged_into IS NULL`; `visible` itself does not change: decision 17). A **name search** that matches B's label gives **A**, marked "(merged: B's label)". This matters most for
  the first case: the person typed a variant spelling, and the next person will type it too. B's label stays in the
  text index, and the autocomplete resolves the hit to its survivor.
- **A write that names B** (a script or a batch file with B's id): **resolved to A**, as a URL already is resolved to
  its entity, and said in the response (**decided**, 2026-11-12).
- **History of B**: its panel shows its versions and "merged into A", with the undo button.
- **RDF**: B's URI stays published. It is written `owl:sameAs` A (or `skos:exactMatch`, following the choice made for
  URLs in [rdf-export-plan.md](rdf-export-plan.md) §14), and dereferencing it redirects to A.
- **Derived**: both are pending after the merge and after an undo. The worker re-derives A's facts with B's documents
  included, and B's facts disappear.

### Proposing and verifying a merge (decided 2026-11-12)

**Decided by the user:** who may merge is a per-project setting, defaulting to admins. **Any logged-in user may
propose a merge, and a second logged-in user may verify it**, which carries it out.

- **The setting**: `MERGE_DIRECTLY = "admin"` (the default; or `"any"`, any logged-in user; or `"none"`, so every
  merge is proposed and verified). Who may merge directly does so from the comparison page as described above.
- **A proposal** is the comparison page's result saved without being carried out: a `PGMerge` with `state:
  "proposed"`, the survivor, the absorbed, the chosen values, the versions of A and B it was made from, who proposed
  it and when, and an optional note ("same father in F1 and F2"). Nothing else is written: no reference moves, B is
  not marked.
- **Where it shows**: a notice at the top of both entities' pages ("A merge with B was proposed by …: review it"),
  and a list of open proposals (`/merges`, and a section of `/admin`). If `pangloss-review` is installed, its queue
  lists them too, through a general hook (the core does not know about review).
- **Verifying**: a **different** logged-in user opens the proposal, which is the comparison page with the proposer's
  choices filled in. If A or B has changed since the proposal (their versions), the page says what changed and the
  rows are refreshed. The verifier can change the choices, and then **verifies** (the merge is carried out, recording
  both people on the `PGMerge`) or **rejects** (with a reason; `state: "rejected"`, kept). The proposer cannot
  verify their own proposal; the API refuses it (403).
- **Checks run twice**: when proposing (so an impossible merge is never proposed), and again when verifying, since
  references may have been added since.
- **Two proposals about the same entity**: allowed. Once one is carried out, the others that involve the absorbed
  entity are marked `stale` and say why.
- **History**: the merge's version of A and the `merge` op record the proposer and the verifier.

### Undoing a merge

`POST /api/Person/{A}/merges/{merge id}/undo`, and the button on A's history panel and on the "merged" notice:

1. For each recorded move: if the source node still exists, is not deleted, and still has `field` → A, move it back
   to B, at its recorded position, with the edge properties it has *now*. Each head changed gets a new version, as in
   a merge. A dropped duplicate is written back.
2. Moves that **cannot** be put back (the node was removed, or its relation was edited to point elsewhere) are listed,
   not guessed.
3. **References made to A since the merge** cannot be told apart: some may have been meant for B. They stay on A, and
   the undo lists them ("made since the merge: 4") as chips, so a person can move any of them by hand (a "move to B"
   action in that list).
4. **A's fields** (revised by decision 21: only when A has not changed since the merge; otherwise always a draft to
   reconcile, never restored for the person): A's version from before the merge is restored, through history's restore. If A was edited since,
   this becomes restore-as-draft: the person reconciles the fields in the dialog that exists. Without
   `pangloss-history` installed, the `PGMerge` keeps A's fields as they were before (the `UpdateDB` payload), so undo
   still works.
5. B's URLs go back, B's mark is cleared, and the `PGMerge` is `state: "undone"` (kept, for the record).

**Merges of merges.** A survivor can absorb several entities (A ← B, then A ← C), and undoing one leaves the others:
each `PGMerge` has its own moves. A survivor that is itself absorbed later (A ← B, then D ← A) is harder. B's
references are now on D. Undoing A ← B would have to move them from D, and A is itself merged. Recommended: **undo
only the most recent merge of a chain first**. Undoing A ← B while A is merged into D is refused with "undo D ← A
first". This keeps every undo simple and correct.

### Where it lives

A merge changes what an id means: reads, lists, search, the autocomplete and writes all have to know it. That is the
core's business, not an add-on's.

- `pangloss-models`: `Entity.merge`, `unmerge`, `merge_preview` (what the checks say, and the counts); the write event
  `merge`/`unmerge` in `hooks`; `before_merge`; `MergeRules`; the `KeepOnMerge()` field marker (documented with
  merging only).
- `pangloss-cypher`: the operation (on `relink`, with a recorder for the moves), the `merged_into` rule in `visible`,
  the resolution of a merged id in `find_existing_entities` and the reads, `PGMerge`. **Conformance tests**:
  merge/undo round trip, duplicates, an edit between merge and undo, a chain, a refusal, a resume after a failed
  batch, and both backends.
- `pangloss-api`: the routes; `pangloss-sdk`: the same methods; `pangloss-history`: the `merge`/`unmerge` ops in
  the panel; `pangloss-interface`: the comparison page, the "merged" notice, autocomplete marking, the console
  action; `pangloss-typology` delegates to it or refuses; `pangloss-zotero` and `pangloss-review` (an `Unreconciled`
  reconciled to B is just a reference, and moves) add `before_merge` where needed.
- A CLI `pangloss merge Person A B` / `pangloss unmerge` for bulk clean-ups from a script's list of pairs.

### Difficulties and risks

- **Not atomic at scale.** It is one transaction per 1,000 heads. Others can see a half-merged state while it runs
  (some references on A, some on B). The `PGMerge` state makes it resumable. A small merge (the usual case: a
  duplicate with a handful of references) fits in one batch and is atomic.
- **Concurrency.** An edit to a referring document during a merge: relink bumps versions, so a stale edit is refused
  with a 412 (the existing rule). Two people merging the same pair: the `PGMerge` takes a lock on both entities, as
  typology's `TypologyLock` does.
- **Permissions.** Decided: a per-project setting, defaulting to admins, with proposal and verification by two
  logged-in users for everyone else (above). Who may undo is still open (see decisions).
- **Unpublished documents** (review) refer to B too. They move as well, though the person merging may not be able to
  see them. The counts include them, without labels, for someone who cannot see unpublished ones.
- **Cost.** Each moved head is a version in history. A person with 5,000 references costs 5,000 small versions. That
  is consistent with typology's merge, and is the price of "nothing lost quietly".

## Part 2: identity statements (two entities said to be one)

### The model is the project's

In a factoid model, "A and B are the same person" is something a source, or a scholar, says. It is a statement in a
factoid like any other, with the factoid's source as its authority:

```python
class SameAs(Statement):
    """Two entities are the same person"""
    entities: Annotated[list[Person], MinLen(2), MaxLen(2), IdentityClaim()]
    argument: str | None = None
    evidence: list[Cites[Statement]] = []        # part 3; leave out if part 3 is not built
```

It can go in `Negative[...]` ("A is *not* B") and `Hypothetical[...]`, with no extra work, and the derived rules
already know what those spaces do. This is not a core concept. `pangloss-library` could offer it ready-made, as it
offers `Identification`: `SameEntity[T]` with the fields above, so a project writes `SameEntity[Person]` in its
statement union.

### What is new, and general

1. **A field marker, `IdentityClaim()`**, put in `Annotated[...]` like `NoUnreconciled()` or
   `RDFField(...)` (a `FieldMarker`). It is **not** an option of `RelationConfig`, so a project that is not a factoid
   model never meets it. It lives in `pangloss-library`, next to `SameEntity[T]`, and is a subclass of the core's
   `KeepOnMerge()`: the core's merge knows only "leave this relation where it is" (a general rule, with uses beyond
   identity, such as a record of what an entity was once called), and the library adds the meaning "this is a claim of
   identity", which the section and the derived rule read. So the core knows nothing of identity statements, as the
   principle asks. A merge does not move these edges, and does not collapse `[A, B]` to `[A]`. Without it, merging the two people that a `SameAs` names
   turns the evidence into "A is the same as A" and breaks `MinLen(2)`. After a merge the statement shows "A" and "B,
   merged into A", which is exactly the history of the decision. It is also what the interface section and the
   derived rule look for. An alternative is a trait on the statement class (`IdentityStatement`). A field option is
   finer: a statement may have identity fields and others.
2. **A section at the top of the entity page** (the interface's `itemSections` hook): "Said to be the same as: [B]
   (2 factoids) · Said not to be: [C] (1 factoid)", each a `ReferenceChip`, with the factoids that say so on demand.
   Hypothetical ones are shown as such. It is drawn wherever a class has a field marked `IdentityClaim()` that can point at
   this entity, so it needs no configuration. Actions: "Compare" (the comparison page, read-only) and "Merge…" (part
   1, when a person decides the evidence is enough). Merging leaves the statements in place.
3. **Optional: reading through identities.** The user's worry is that "same as" means every query has to be rewritten
   to return both. Recommended: **never implicitly**. The links are claims, possibly contradicted, and an implicit
   union would quietly mix two people in every list and count. Instead:
   - a `pangloss-derived` rule over fields marked `IdentityClaim()` gives a symmetric derived relation `said_to_be_same_as`
     with its justifications and contexts. The existing machinery blocks `Negative` and qualifies `Hypothetical`;
   - the entity page gets a toggle, "include what is said of the entities said to be the same", which reads B's (and
     C's…) incoming relations into A's page, each marked with which entity it is of;
   - structured search gets an operator, for example `{"$same_as": {"type": "Person", "id": A}}` or `including:
     "same_as"` on a relation condition, so that a search can ask for it.
4. **Transitivity** (decided 2026-11-12: **the whole cluster by default**). One source says A = B and another says
   B = C; A, B and C are then one cluster, and the toggle and the search operator follow the whole of it by default,
   with "one step only" as an option. The section still shows each member's path ("C, through B"), so that it is
   clear which statements join them. What follows from the decision:
   - **What joins a cluster**: plain identity claims only. A claim in `Hypothetical[...]` is shown in the section,
     marked as such, but joins nothing; a claim in `Negative[...]` joins nothing (the derived rule's existing
     `block`/`allow`).
   - **A contradiction inside a cluster** (A = B, B = C, and a factoid saying A ≠ C): the cluster is still followed,
     but the section and the toggle show a warning naming the negative claim, and the merge action warns too.
   - **Merged members**: a cluster is computed over survivors (B merged into A counts as A), so a merge never splits
     or duplicates a cluster.
   - **Cost**: a variable-length path over the derived `said_to_be_same_as` relation. Clusters will be small (a few
     entities), but the query is bounded (a depth limit, say 10) and measured on the large database before it is on by
     default in search.

### Difficulties

- **Contradictions.** One factoid says A = B and another A ≠ B. The section shows both, and that is correct for a
  factoid model. The merge action warns when a `Negative` identity statement exists.
- **Statements about A and B after a merge.** As above, the `IdentityClaim()` edges stay on B, so the statement still
  reads correctly. The derived relation then joins A to B (merged), which the derived reading should drop, since B is
  A.
- **Cost.** The section is one query per page through the reverse edges of identity fields, which is cheap. The
  derived rule is only as costly as any rule.

## Part 3: a document that cites a document

### What is being asked

A `SameAs` statement's evidence is other statements: "F1 says A's father was X; F2 says B's father was X". To cite
them is to refer to a document (a nested `Statement` in another `Factoid`) by its id, without containing it. Today
the model says a relation to a document *is* containment. So this is a third kind of relation, and it has to be
written differently:

```python
evidence: list[Cites[Statement]]        # payload: [{"type": "Activity", "id": "…"}]; Statement's subclasses allowed
```

`Cites[T]` takes `{type, id}` in a payload. Its `View` is the cited document's `ReferenceView`
(label, type, head) with its context (which factoid, which semantic spaces: "not: …"). It never nests or writes the
cited document.

### How it is stored: an id, not an edge (revised 2026-11-12)

The first version of this proposal recommended an edge. The user asked whether a text id is preferable, since the
cited tree is torn down and rebuilt on every save. **It is.** As revised:

- **Each citation is a small node of the citing document**, `(:PGCitation {target_id, target_type, cited_hash,
  cited_version})`, joined to the citing node by its field. It belongs to the citing document, so it is rebuilt with
  that document, as everything else there is. **Nothing points into the cited tree**, so saving the cited factoid
  cannot break a citation, and its update query is untouched.
- **`target_id` has an index** (a label-property index on `PGCitation`, on both backends). "Who cites this node?" is an
  index lookup, and the protection below and "Cited by" need nothing more.
- **Checked when written**: the id must be a document node of an allowed class (`T` or below), not deleted. This is
  the same check a reference to an entity gets, done by a lookup instead of by `MATCH` for an edge.
- **Followed by a join** where it is needed (`MATCH (n {id: c.target_id})`, which uses the id index): search ("cites
  a statement that…", "cited by"), a derived rule, the RDF export. It is slower than an edge by an index lookup a
  hop, which does not matter at the sizes citations will have. It is measured when built.

The difference from an edge is therefore only in what is written. Everything else (the check, the protection, the
picker, the display) is the same, and the update is not touched. A bare literal (a `UUID` field, with nothing else)
would do less: it gives no index on the target, no type check and no field the export can name. That is why each
citation is a node with the id on it.

### A cited statement is protected

**Decided by the user** (2026-11-12): a statement used as evidence may be changed only after a confirmed warning, and
may not be removed (nor its factoid deleted) while it is cited. As follows:

- **What counts as the cited content**: the cited node and everything nested in it (its spaces, reified relations,
  conjunctions), **and the head document's own fields** (the factoid's `source`), since the source is what makes it
  evidence. Other statements of the same factoid are not part of it. On every write of a citation, a hash of this
  content (`cited_hash`) and the head's version are recorded on the `PGCitation`.
- **On every write of a head that can contain a citable class** (known from the models, so free for the rest): one
  indexed query finds the citations of its nodes, and the new content's hashes are compared with theirs. If any
  differ, or a cited node is removed:
  - the API refuses with **409**, naming each citing document (`PanglossCitedError`, with `fix=`: "edit it with
    `acknowledge_citations`, or change the citations first");
  - the request may say `acknowledge_citations: true`, and then the write goes ahead. Each changed citation is marked
    `changed_since_cited` (its hash no longer matches), and the citing documents' pages say so, with a link to
    history's compare page on the two versions;
  - **removing** a cited node, even with the flag, is refused unless no citation is left. The person changes the
    citations first. A removal would leave evidence pointing at nothing.
- **In the form**: a cited statement has a badge, "cited as evidence by 2" (chips on demand), and its fields are read
  only. **"Edit anyway"** opens a warning that names the citing documents and asks for confirmation. Saving then
  sends the flag. The Delete button of the part, cut (the clipboard gives pasted nodes new ids, so a cut and paste
  would remove the cited node), and ↧/↥ retyping to a class the citation does not allow are refused in the same way.
- **Deleting the whole cited head** (the factoid): refused (decided), through `/deletable` ("cited as evidence by
  …"), until the citations are changed.
- **Restoring** the cited head to a version without the cited node is the same refusal; restore-as-draft lists it.
- **Migrations**: a migration that changes a cited class must keep node ids (to check: does wrap/unwrap?), and a
  removal of a cited class is refused while citations to it exist. The planner knows `Cites` fields from the models.

### What else changes

| Area | What is needed |
|---|---|
| **History** | The citing snapshot holds `{type, id}`, as for an entity; a restore whose citation names a node no longer there is history's existing `reference-missing` conflict. "Nothing else refers to a nested document" (history.md) is no longer quite true, but the snapshot design holds: a nested document has no history of its own, and its head's history covers it |
| **Review** | A published document citing an unpublished one: shown as "not yet published", without the label, to readers who cannot see it (the visibility fragments exist) |
| **Pickers** | Today only entities are searched. Recommended: **"Cite…" from the cited document**, a console action on a statement in a factoid's page ("copy as citation", through the clipboard), and a search dialog of documents of the allowed class by label and by the entities they mention (`$mentions`). Review's `#` part picker is the model |
| **Search, derived, RDF** | A join through `target_id`. A derived rule may follow citations later; RDF writes a triple between the two documents' URIs (check what the export mints for nested documents) |
| **Labels** | A label template that reads a `Cites` field uses the cited label only. Cycles (A cites B cites A) are harmless |
| **Interface** | A `ReferenceChip` for a document, with its head and spaces as context; "Cited by" on the cited statement; the "changed since cited" marker; the badge, lock and warning above |
| **Export, TS types, stubs, LSP** | `Cites[...]` in each |
| **The skill and docs** | "Documents contain; entities are referred to" becomes "…documents are contained, or **cited** (`Cites`, by id), never referred to otherwise" |

### Does allowing it undermine anything?

The rule existed for two reasons, and both survive if citation is a separate kind:

- **Ownership.** A document's content is what it contains. A citation does not own, write or version what it cites,
  just as a reference to an entity does not. The difference from an entity is that the target lives inside a head that
  can rewrite it. That is the protection above, and the hash on the citation.
- **One snapshot per head.** It still holds.

What must **not** follow is that any relation to a document becomes ambiguous. `statements: list[Statement]` stays
containment. Citation is only `Cites[...]`, so the meaning of every existing model is unchanged and no migration is
needed for existing data.

## Risks and safeguards (2026-11-12)

**Decided by the user** (2026-11-12): merging **moves the references** (part 1). The pointer design (next section) and
the hybrid are rejected. Merges are expected to be infrequent and usually right, so reasonable safeguards are enough.
Projects will very likely write their own Cypher, which is the main reason against the pointer design.

Part 1 is the first operation in Pangloss that rewrites many other people's documents at once, and the first whose
undo depends on a record kept beside the data (the `PGMerge` and its moves). Most of the risk is there. Each risk
below has the way it would damage the data, and the safeguards that are **part of the work**, not later additions:
each gets a conformance test (both backends) unless said otherwise. Safeguards marked *decided* changed something
already decided, and were confirmed by the user (decision 15).

### 1. A restore makes half a merge undone

**How.** History's restore undeletes the entities an old version refers to. If "merged" were a kind of deletion,
restoring an old version of any factoid that named B would bring B back: visible, with no references (they are on A),
while its `PGMerge` still says "done". Restoring A to its version from before the merge would revert A's fields while
B's references stay on it. Restoring B itself would bring back an entity that is still marked merged.

**Safeguards.**

- **Merged is its own state**, not a deletion: `merged_into`, never the `deleted` flag. Nothing that undeletes can
  clear it; only an undo can.
- A restore of a document that refers to B **resolves B to A**, as every write does (decided 3), and says so in the
  restore dialog. It never touches B.
- Restoring **A** to a version from before an active merge, or restoring **B** at all while it is merged, is refused:
  "this entity was merged on …: undo the merge" (a new history conflict, `merged`; restore-as-draft lists it).
- Tests: each of the three restores above, before and after an undo.

### 2. A migration leaves the record of a merge stale

**How.** A move records a field name, the source node's id and its position. A migration that renames the field leaves
the undo looking for a field that no longer exists. One that removes it leaves moves with nothing to put back. One that
wraps or unwraps it, if it makes new nested nodes, leaves ids that are not there (citations, part 3, break the same
way). And a migration that skips merged entities, as it might skip deleted ones, leaves B no longer fitting the models,
so an undo brings back an entity that does not validate.

**Safeguards.**

- **Migrations treat merged entities as live data.** B is migrated like any node. A test: a field added to `Person`
  with a default, then an undo; B has the field.
- **Each `PGMerge` records the migration state** when it ran (the last migration applied of each app). An undo
  compares it with now. If a migration since then changed a model whose fields the moves record, or the class of A or
  B, the undo **does not run automatically**: it lists the moves it can still match (by node id and field, with renames
  followed when the migration says the field was renamed) and those it cannot, and a person confirms. Rewriting the
  records inside every migration was rejected: it spreads merge logic into the migration planner, for a rare case.
- **To check before building:** do wrap and unwrap migrations keep the ids of nested nodes? If not, make them keep
  them, which citations (part 3) need as well.
- A migration that removes a class, or changes `Entity` to another kind, is refused while an active merge involves
  that class ("undo the merge, or finish it", the second meaning to make it permanent: its `PGMerge` is closed and can
  no longer be undone).

### 3. A write that skips the resolution hides data

**How.** A write naming B should name A (decided 3). Any path that skips this makes a new edge to B. B is hidden, so
what the edge says disappears from every page and search, without an error. The likely places: the analytical bulk
load (it writes with the checks off), hand-written data migrations, add-ons with their own Cypher, `create_inline`
naming B by UUID, relink itself (typology's merge into a type that is merged), and the review package's
reconciliation.

**Safeguards.**

- **One place resolves ids**, in the write plan (`find_existing_entities` and what it serves): every write through the
  models goes through it. The add-on guide says that a package writing edges to entities by its own Cypher must call
  it.
- **Bulk load** resolves merged ids in its preparation (it already reads the file before writing), or refuses the file
  naming them. The choice is made when it is built; resolving is in keeping with decision 3.
- **A data check**, `pangloss check-data` (a command; also a job on `/admin`): every edge to a merged entity, other than
  `KeepOnMerge()` fields, is reported, with the head it is in, and can be moved to the survivor (each such head gets a
  version). This is what finds the paths no one thought of, including a project's own Cypher.
- Tests: a reference to B by UUID, by URL and with `create_inline` resolves to A; the bulk load does too.

### 4. An incomplete record makes an undo partial without anyone knowing

**How.** The undo can only put back what was recorded. References to an entity take many forms: plain edges, edges
with properties (`ViaEdge`), the target of a reified relation, members of a conjunction, relations inside an embedded
object, an `Unreconciled` that was reconciled, typology's `has_type`, the edges of derived facts, `PGUrl`s. One form
that the merge moves but does not record is a form an undo never brings back.

**Safeguards.**

- **Counted before and after**, in the merge itself: the edges into B (the forward edges of fields, between
  `PGIndexableNode`s; not the record-keeping edges such as `is_update_of`, nor what add-ons attach) before; after, there must be none but `KeepOnMerge()`
  fields, and the record must hold as many moves as were made. Otherwise the merge stops and is rolled back (for a
  merge in one transaction, by not committing).
- **Derived facts are not moved or recorded**: they are deleted and derived again by the worker (both entities are
  marked pending). They are a cache, not data.
- A conformance test with **every kind of relation** the demo's models have (and the test models of the conformance
  suite), each pointing at B: merge, check A has them all; undo, check B has them all again, in their positions and
  with their edge properties.

### 5. A wrong merge of a busy entity, found late

**How.** "Rome" merged into "Rome, Georgia" touches thousands of documents: each gets a version, and anyone with one of
them open is refused with a 412 when they save. Found weeks later, the undo puts back only the references recorded;
everything entered since against the survivor is mixed, and only a person can sort it. Two-person verification helps,
but two people can agree on a mistake, and one person can have two accounts.

**Safeguards.**

- **Before verifying**, the comparison page says how many heads the merge will write, and lists the ten largest kinds
  of what refers to each ("A: 4,210 factoids; B: 312 factoids, 3 places").
- **The undo screen** says how old the merge is, how many references were made to the survivor since, and that they
  will stay on the survivor; it lists them for moving by hand ("move to B").
- **A size limit** (decided): a merge that would write more than `MERGE_LIMIT` heads (default 1,000, counted as
  distinct heads over all fields; `relink` is changed to take an open transaction: decision 20) needs an admin, whatever `MERGE_DIRECTLY` says, and can then also be run from the command
  line. Below the limit **a merge is one transaction, so it is atomic**: no half-merged state can be seen, and a failure
  leaves nothing behind. Above it, the batches and the resumable `PGMerge` state described in part 1.
- **A notice to admins** of each merge carried out (on `/admin`, with the live feed), so a wrong one is seen early.

### 6. Citations used to lock someone else's data

**How.** A cited statement cannot be removed, nor its factoid deleted (decided 10). So anyone can block the removal of
any statement by citing it, and the citing document may be unpublished, so that the person blocked cannot see it.

**Safeguards.**

- **Citations from deleted documents do not count.**
- **Citations from unpublished documents warn but do not block** (decided): the blocked person is told "cited by
  a document not yet published"; the citation is marked "changed since cited" or "removed" when its document is
  published or read.
- **An admin may override** (decided): the removal goes ahead, and each citation it breaks is marked "removed
  since cited", pointing at the version in history that had it.

### 7. Warnings that mean nothing: "changed since cited" after merges and migrations

**How.** The hash of a cited statement covers the ids of the entities it refers to. A merge changes them (B becomes A)
in every cited statement that named B; a typology merge does the same with types; a migration that reshapes
statements changes every hash. After one migration every citation could say "changed since cited", and the warning
would stop meaning anything.

**Safeguards.**

- The hash is of a **normalised form**: entity ids as they resolve now (B as A), and literals as the codecs store them.
  A merge or a typology merge then changes no hash.
- **Migrations recompute the hashes** of the citations they touch, as they recompute other derived values (a migration
  is not an edit). A test: a field renamed on `Statement`; no citation is marked changed.

### 8. One careless identity claim joins two clusters

**How.** Clusters are followed whole by default (decided 8). One careless claim ("John = John", between two people of
the same name) joins two clusters, and every page and search with the toggle on mixes them. Nothing is damaged (it is a
reading), but a "Merge…" button beside a large cluster invites a large mistake.

**Safeguards.**

- The section shows **the size of the cluster**, and warns when it has more than a few members (setting, default 5) or
  contains a negative claim between two of its members.
- **Merging is of pairs only**, from the comparison page; there is no "merge the cluster".

### 9. What has been published cannot be taken back

**How.** An RDF dump made while a wrong merge stood carries `owl:sameAs` B → A to whoever downloaded it. Not
recoverable, and minor.

**Safeguard.** After an undo, B's URI dereferences to B again, and the next dump has no `sameAs`. The RDF guide says that
dumps are snapshots.

### What these add to the work

- In the merge itself: the counts before and after, the migration state on `PGMerge`, the size limit, one transaction
  below it.
- In history: the `merged` conflict, restore resolving merged ids.
- In the write plan and bulk load: one resolution, used by both.
- A command and an admin job, `pangloss check-data`, for edges to merged entities (and, with part 3, citations that
  point at nothing).
- In citations: the normalised hash, migrations recomputing it, the rules for deleted and unpublished citing documents,
  the admin override.
- In the interface: the counts on the comparison page, the age and "made since" on the undo screen, the notice to
  admins, the cluster size and warnings.

## Details settled (2026-11-12, decisions 16 to 32)

A second reading of this proposal against the code (`pangloss-cypher`, `pangloss-history`, the migrations) found
places where it contradicted itself or the code, and cases it did not cover. **Decided by the user** (2026-11-12): the
recommended choice in each. Where this section and the parts above differ, this section is right; the sentences above
that were plainly wrong have been corrected in place.

### The shape of what is stored

- **`KeepOnMerge()` fields are not resolved** (16). Decision 3 resolves every written B to A. An update rewrites the
  whole head, so the next save of a factoid holding a `SameAs` would send B's id back and make it "A is A", which is
  what `KeepOnMerge()` exists to prevent. The resolution therefore leaves these fields out, in writes and in restores.
  The autocomplete does not offer B, so only ids already there come back.
- **Two fragments** (17). `visible` decides both whether a head is listed and whether an entity shows inside a document
  (`fragments.visible`), and B has to show in the statements that still point at it. `visible` stays as it is. A new
  `listed` (`visible` and `merged_into IS NULL`) is used by lists, search, the autocomplete and incoming relations. B
  therefore shows wherever an edge still points at it, marked "merged into A": a stray edge (risk 3) is seen, not
  hidden.
- **The mark is a property** (18): `merged_into` on B, holding A's id. `PGMerge` holds `survivor` and `absorbed` as
  indexed properties. There are no edges between them. An edge `(B)-[:merged_into]->(A)` would be read as a field of B
  (the read query takes any forward edge from a root to an `:Entity`) and deleted by any update of B (the update
  deletes every forward edge of the head but `has_url`).
- **A write addressed to B itself** (19: an update, a delete, an undelete, a restore) is refused with 409, naming A.
  The version sent is B's, not A's. Only *references* to B are resolved.
- **One transaction below the limit** (20). `relink_batch` opens its own transaction, for each field and each batch,
  and a merge is several fields, A's update, B's mark, the URLs and the `PGMerge`. `relink` is changed to take an open
  transaction; `MERGE_LIMIT` counts distinct heads over all fields.

### What a merge does in the cases not covered

- **Undoing A ← B while a later A ← C stands** (21) is allowed. The references and URLs go back. A's fields are not
  restored for the person: the values from before the merge are shown beside the current ones to reconcile, and the
  same whenever A has changed since. (Decision 6 still holds for a survivor that was itself absorbed: D ← A first.)
- **A document that refers to A and to B in different fields** (22), such as a marriage with `husband=A, wife=B`: after
  the merge it says A married A. This is the same problem as two of them in one list, which relink only notices within
  one field. These documents are moved, and listed in the preview and the summary with the others. **A and B's own
  fields**: the comparison page leaves A and B out of the result's values, and relink skips A as a source, so A never
  refers to itself.
- **A collapse that breaks validation** (23): `[A, B]` under `MinLen(2)`, or shares that `SumsTo`. The preview
  validates each head as it would be after the merge. The merge is refused, naming those that fail, to be changed
  first. (Relink would otherwise record a version without content, and the next edit of the head would fail.) A
  collapse that validates goes ahead and is listed (decision 5).
- **A write naming B that races the merge** (24). B is marked first in the merge's transaction, a second pass of
  relink runs after the commit, and `check-data` finds what is left. A conformance test with a concurrent write, on each
  backend. No lock is taken by ordinary writes.
- **Deleting A while it has absorbed others** (25) is allowed (it is a flag). B's id then resolves to a deleted
  entity, and an undo is refused until A is undeleted. B's outgoing relations count as uses of what they point at, so
  that an undo does not bring back a B that refers to deleted entities.
- **Stored payloads and migrations** (26). A proposal made before a migration of either class is marked stale, to be
  proposed again. A's kept fields are offered as a draft, with what no longer validates shown.
- **The class in the route** (27). `GET /api/Poet/B` gives A as it is (a `Person`, if the survivor took the wider
  class), with `merged_from`. The SDK's `Poet.get(B)` raises a typed error that carries A's reference when A is not a
  `Poet`.
- **Zotero** (28): `before_merge` refuses when B is linked to the library and A is not; the linked item must be the
  survivor.

### Citations

- **What the hash covers** (29): the cited node and what is nested in it, and those fields of its head that the head's
  class names (`Document.Meta(cited_with=["source"])`; none by default). All of the head's fields would mean that a
  correction to a factoid's notes warns everyone who cites one of its statements.
- **A citation written while its target is removed** (30): the two writes are of different heads, so nothing makes
  them conflict. The citing write also writes a count on the cited head (which the "cited by 2" badge reads). To be
  measured.
- **Undeleting a citing document whose target is gone** (31): undeleted, the citation marked "removed since cited".
- **What may be cited** (32): any document node that `T` allows, head documents and nodes of the same head included.
  In one payload or bulk file the target has to carry its id and come first.

### Corrections that needed no decision

- The count before and after a merge is of field edges between `PGIndexableNode`s, not of every edge into B.
- B is marked at the start of a merge, above the limit too, so that writes during the batches are resolved.
- B's URLs move before A's fields are written, in the same transaction: `replace_urls` refuses a URL another entity
  has.
- The resolution follows chains (X merged into B, B into A). It is added where references are checked
  (`check_references_exist`) as well as where the entities written in a payload are found (`find_existing_entities`).
- The hash has a version, so that a change of codec or of the normal form recomputes it; the normal form has each
  entity of a list once, so a collapse changes no hash.
- `PGCitation` is a kind of node that the tree read, history's diffs, the export and migrations know.
- The undo screen says when moves cannot be matched because nested ids changed (an update that did not send them gives
  new ones). (A wrap migration can be followed: see "Measured before building", 6.)

## Measured before building (2026-11-12)

Six questions the plan left "to be measured" or "to check", tried with throwaway Cypher before anything is built.
Nothing of Pangloss was changed. The queries of a merge are those of `relink.py`, run in one transaction.

**On what.** Memgraph 3.14.0 with its usual flags (no `commit-lock-narrowing`), a copy of the large scratch database
(756,928 nodes, 1,865,529 edges: 60,000 people, 30,000 factoids, the text index and every index of the demo). Neo4j
2026.10.1, empty, for what the two databases do differently (not for times). Times are from the client, on small
responses. The scripts were in `/tmp/merge-measure/scripts` (`races.py`, `timings.py`, `cite_cost.py`, `merge_tx.py`,
`merge_live.py`); the containers were removed afterwards.

### 1. A write that races a merge (decision 24)

Two transactions, stepped by hand: a merge that marks B (`SET b.merged_into`), and a writer that makes an edge to B.

| Order | Memgraph | Neo4j |
|---|---|---|
| The merge marks B, then the writer makes its edge | the writer is refused (`Cannot resolve conflicting transactions`, a transient error, which `run_write` runs again) | **the writer is not stopped**: its edge is made, and committed after the merge. An edge to a merged B is left |
| The writer makes its edge, then the merge marks B | the merge is refused, and runs again | the mark succeeds; the writer's commit waits for the merge's, then commits. **An edge to B is left** |
| The writer checks B, the merge marks B and commits, the writer makes its edge | the writer is refused | the edge is made; a check made in or after that statement does see the mark |
| Two writers each make an edge to the same entity | both succeed | both succeed |

- **Memgraph: marking B first is enough.** Every order ends with no edge to a merged B, and the one refused runs
  again, when its check finds B merged and resolves it.
- **Neo4j: it is not.** Neo4j reads what is committed and does not refuse the second writer, so an edge made by a
  transaction that was open when the merge committed stays on B. A check by the writer before its commit closes most
  of the gap, not all of it (the merge may commit between the check and the commit). What is certain is either a lock
  of each entity a write refers to (rejected in decision 24, as it makes writes that name the same entity wait for
  each other), or the merge's second pass, run a few seconds after its commit and not at once, with `check-data`
  behind it. **Decision 24 stands as taken, with this said: on Neo4j it is the second pass that does the work, and it
  must be delayed.**

### 2. The count on a cited head (decision 30)

- **It does what was wanted, on both.** Memgraph refuses whichever of the citing write and the update of the cited
  head comes second. Neo4j makes the second wait (the update already takes the head's lock first,
  `before_replace`), and it then sees what the first wrote: the update sees the count, or the citing write finds its
  target gone. So each must read after it has written to the head, not before.
- **It costs nothing by itself**: 6.4 ms a commit without the count, 6.6 ms with it (one writer, 300 commits, each
  with a node in the text index).
- **Many writers citing one head** are refused and run again often: eight writers, 150 commits each, all citing the
  same factoid: 8,039 retries and 62 commits a second, against 78 a second without the count (eight writers
  on different heads: 84 a second, one retry). People do not do this; a bulk load of citations of one factoid would,
  and should write them in one transaction.

### 3. A merge in one transaction (decision 20)

A person B with references from N factoids (three fields, one of which narrows another), merged into a person A with
3,000: mark B and write A, record the moves, move the edges, a `PGUpdate` for each head, the versions, the URLs, the
count of what is left on B, the `PGMerge`.

| Factoids that refer to B | Edges | The transaction | The commit |
|---|---|---|---|
| 100 | 175 | 35 ms | 1 ms |
| 994 | 1,750 | 561 ms | 5 ms |
| 4,854 | 8,750 | 13,127 ms | 39 ms |

- **1,000 is a good limit.** The cost grows faster than the number of edges (each node's edge is found among all of
  B's), so five times the size is twenty-three times the time. Memory did not move (1.20 to 1.22 GiB tracked).
- **While it is open**, a save of a new document naming A, of one naming B, or of one of the factoids being moved is
  refused and runs again; saves of anything else go through. Moving edges onto A does not by itself stop writers
  naming A; writing A's fields does.
- **A and B must be written first in the transaction**, and not only for the sake of 1. With 20 saves a second naming
  A, the merge went through at the first attempt when it wrote A first (the writers waited 0.6 s, 76 retries between
  them). When it wrote A last it **never went through** in 40 attempts over 63 s.
- **A save of one of the factoids being moved, while the merge runs, makes the merge start again.** At one such save
  a second it took one or two attempts (0.6 to 1.2 s). At five a second among those 1,000 factoids it never went
  through (40 attempts). People editing do not reach that; a bulk update or a migration of those documents does. So:
  the merge runs again a few times with a growing wait, and then stops with a message saying what is being written,
  and it is refused while a bulk load or a migration is running.
- Not measured: the same on Neo4j, and the reading of each head afterwards for history (`written_form`), which
  typology's merge already does.

### 4. What `listed` costs (decisions 17 and 18)

500 of 60,000 people marked `merged_into`; each query with `NOT coalesce(n.deleted, false)` alone, and with
`AND n.merged_into IS NULL` added. The queries were written by hand in the shape of the generated ones, not taken from
them.

| Query | `visible` | `listed` |
|---|---|---|
| A page of people, by label | 26.5 ms | 28.2 ms |
| The count of people | 5.9 ms | 8.8 ms |
| Autocomplete, two words | 11.1 ms | 10.9 ms |
| The most used people (before anything is typed) | 135 ms | 134 ms |
| The people named in 200 groups' documents | 0.9 ms | 0.9 ms |

A property on the node costs a few milliseconds where every person is read, and nothing elsewhere. No index is needed.

### 5. Finding citations by `target_id` (decision 9)

`PGCitation` nodes with a label and property index on `target_id`, each citing a statement chosen at random.

| | 10,000 citations | 100,000 citations |
|---|---|---|
| Who cites the nodes of this factoid (the check on every save of a factoid) | 0.29 ms | 0.44 ms |
| The same, of a factoid nothing cites | 0.24 ms | 0.27 ms |
| 50 citing statements joined to what they cite | 2.4 ms | 0.8 ms |
| Statements that cite a statement of the year 800 | 5.6 ms | 5.8 ms |

- The check costs under half a millisecond a save, and the index is used (`ScanAllByLabelProperties` on
  `target_id`).
- **A trap, as expected**: the join written from the citation's side, `MATCH (c:PGCitation) MATCH (n:PGIndexableNode
  {id: c.target_id})`, took **250 ms** for 10,000, because Memgraph scans every node and joins. Joins have to start
  from ids already in hand (`UNWIND ids AS id MATCH (c:PGCitation {target_id: id})`), or from a few citations. The
  "cited by" search and the RDF dump need to be written that way and measured again when they exist.

### 6. Wrap and unwrap migrations and node ids (risk 2)

Read in the code (`migrations/operations.py`: `wrap_reified`, `wrap_in_semantic_space` and their unwraps), not run.

- **Wrapping keeps every id that was there.** The node that had the relation and what it pointed at keep their ids. A
  new node with a new id is put between them. **Unwrapping** deletes that node and nothing else.
- **Citations are safe**: a cited statement keeps its id through both. Nothing has to be changed in the migrations.
- **Merge moves can be followed through a wrap, not just listed for a person.** A move recorded as (node S, field F)
  is found after a wrap as S, by F, to a wrapper, by `target`, to A, and the undo can re-point the wrapper's `target`.
  After an **unwrap**, a move that was recorded on a wrapper node has lost its node. If each move also records the
  node that holds the wrapper, it can be found again. This replaces "a wrap migration ran: the moves cannot be
  matched" above.

### What follows for the plan

- Decisions 17, 18, 20 and 30 are confirmed by measurement, and the default `MERGE_LIMIT` of 1,000.
- Decision 24 holds on Memgraph as taken. On Neo4j the delayed second pass is what closes the gap (1).
- New in the work: A and B written first in the merge's transaction; the merge's retries and its refusal during bulk
  loads and migrations (3); joins on citations written from ids in hand (5); each move records the node holding a
  wrapper (6).

## Alternative considered: merging by pointer, without moving anything (rejected 2026-11-12)

Asked for by the user, after the risks of part 1 were discussed (restore undeleting B, migrations leaving the record stale, writes that skip the resolution, an incomplete record of moves): the merge that part 1 describes moves every reference from B to A
(and records the moves so they can be put back). The alternative moves **nothing**. B and every edge to it stay as
they are; B is marked as an alias of A; and **every read treats A and B as one entity**. Undoing is removing the mark.
This section works it out in full, and says what it costs everywhere, custom Cypher above all. **Rejected by the
user** (2026-11-12): projects will very likely write their own Cypher; merges will be few and seldom wrong. It is kept
for the record.

### How it would work

**The representation.** Two things on entity nodes:

- `(B)-[:merged_into]->(A)`: the merge itself, the truth (one edge per merge; kept with its `PGMerge`, who and when).
- **`canonical_id`**, a property **on every entity**, indexed: its own id, unless it is merged, and then the id of the
  entity at the end of its chain (B merged into A, A into D: both have `canonical_id = D`). It is materialised, so no
  query ever walks a chain: "the entities that are X" is `MATCH (e:Entity {canonical_id: $x})`, one index lookup,
  usually one node. Every create sets it (`canonical_id = id`); a migration sets it on the entities that exist; bulk
  load writes it.

**Merging A ← B** writes, in one transaction:

1. the `merged_into` edge and the `PGMerge`;
2. `canonical_id` of B, **and of every entity whose canonical id was B** (those merged into B before), to A's canonical
   id;
3. A's fields as chosen on the comparison page (an ordinary update, a version in history; the class may change, as
   decided);
4. a write event, so that history, derived (pending: every head that refers to any member) and the live feeds hear
   of it.

That is a handful of entity nodes, **whatever the number of references**: always atomic, always small, no batches, no
record of moves, no versions of other people's documents.

**Undoing** removes the `merged_into` edge and recomputes `canonical_id` over the subtree that hung from it (B and what
was merged into B: their root is now B). Because the edges were never moved, it is **exact**: every reference written
to B, before or after the merge, is B's again. **Undoing in any order works** (A ← B while D ← A stands: B's subtree
gets root B; A stays in D), so decision 6 could be relaxed. A's fields are restored from history (the same class-change
caveat as in part 1).

**What a reference holds.** A document that refers to B keeps `{type, id: B}` in the graph and in its history snapshot.
When read, the `ReferenceView` says both: `{type, id: B, label: <A's label>, canonical: {id: A, type}}` (the
`canonical` key only when it differs). The interface draws A's chip (linking to A) with a small mark "written as B"
when the page asks for it. **A save sends B back unchanged** (the edit view keeps the written id), so editing a
document does not quietly move its references, and undo stays exact. A **new** reference can only be made to A: the
autocomplete, the pickers and the API's resolution (decided 3) give canonical ids.

### What every read has to do

Two rules, and every query that touches an entity has to follow both:

1. **Identifying an entity** by id becomes identifying its members: `{id: $id}` becomes `{canonical_id: $id}`
   (where the reader wants "A, with what is merged into it": incoming relations, counts, search by `is`).
2. **Reaching an entity** from a document lands on the node written (B), whose fields are **B's own, dormant ones**.
   Anything that reads an entity's fields, label or class after reaching it has to hop to the canonical node first:
   `MATCH (c:Entity {id: e.canonical_id})`. Otherwise it reads B's stale values.

And a third, outside Cypher: **comparing ids** in Python or TypeScript (`ref.id == entity.id`, a set of ids) must
compare canonical ids.

### Impact, place by place

| Where | What changes |
|---|---|
| `pangloss-cypher` reads (`read_query`, `read_functions`) | Every nested reference to an entity: the hop to the canonical node for its label and `ReferenceView` fields, and the `canonical` key. One more index lookup per reference read |
| Incoming relations (`read_incoming`, `IncomingRelations`, the virtual rows, the counts) | Start from `{canonical_id: $id}`, so A's page lists what refers to A **and** B. A document referring to both shows twice (as A), marked |
| Lists, counts, "search everything" (`list_query`, `fragments.visible`) | Leave out merged entities (`canonical_id = id`). The `visible` fragment gains it, so most queries get it for free |
| Autocomplete (`autocomplete_query`) | A hit on B's label gives A (deduplicated by canonical id), marked "(merged: …)" |
| Lookups by URL (`lookup`, review's `uris.py`) | A URL of B finds B; resolve to canonical. Whose URLs a merged entity "has": A's and its members' |
| Writes (`validate_write`, `find_existing_entities`, `create_inline`) | A reference to B is **valid** (B is live data, an alias); the API's resolution to A (decided 3) is for new references. The type check: does A's class fit the field? (the merge already checked it for B's references) |
| Structured search (`search_query`) | `is`/`is_any` compare `canonical_id`. **A nested pattern on an entity's fields** (`a person born after 1300`) needs the hop, or it tests B's dormant `born`. `$mentions` and `$incoming` the same. The largest single piece of work, and where a missed hop gives wrong results silently |
| Delete and `/deletable` (`delete_node`, `fragments.uses_of`) | Uses counted over the members. Deleting B while merged: refused (undo first). Deleting A: refused while it has members, or deletes the cluster (decide) |
| `pangloss-derived` | Patterns reach B through documents: the fact must be about A, so the compiled pattern hops to canonical before the entity's class and fields are tested, and the fact's edges go to the canonical node; the fact's key uses canonical ids, so "A member of G" and "B member of G" are one fact. A merge or undo marks every head that refers to a member as pending (a count of heads, not a write to each). `read` by entity: `{canonical_id}`. `derived_visible`: a fact whose entity has been merged since it was derived is stale until the worker runs (hide it, as for a deleted entity) |
| `pangloss-typology` (`graph.py`) | "Entities of this type" (`has_type` in reverse) leaves out merged entities (B's own `has_type` is dormant); types themselves are entities: a general merge of types stays refused, typology keeps its own merge (by relink) |
| `pangloss-review` | Reconciling an `Unreconciled` picks a canonical entity (pickers). Likeness and "reconcile together" compare canonical ids. URI claims: resolve to canonical |
| `pangloss-dates` | The timeline of an entity: from its members (it uses the incoming read) |
| `pangloss-calendar`, `pangloss-admin`, users | Nothing (no entity queries) |
| `pangloss-history` | **Simpler than part 1.** Snapshots keep what was written (B); a restore of any document is fine (B exists, is not deleted: none of the undelete trap). Restoring B while merged: its dormant fields change, nothing else; allow or refuse (decide). Restoring A to before the merge: only its fields |
| Migrations | **Simpler than part 1.** B is ordinary data, migrated like any node; nothing records field names or node ids, so nothing goes stale. A **data** migration written by hand that reads entities must follow the two rules |
| Bulk load | **Simpler.** An edge to B is valid; it must only write `canonical_id` on the entities it makes |
| `pangloss-rdf` | A reference to B is written with A's URI (or B's, and B `owl:sameAs` A). B's own description: only the `sameAs` |
| Label templates | A document's stored label was made with B's label and keeps it (labels are written, not computed on read). Leave it (it is what was written), or a job that rewrites labels (versions of others' documents again, which this design avoids) |
| Interface | `ReferenceChip` takes `canonical`; the "written as B" mark; the entity page of B redirects to A; the edit view sends written ids; clipboard (copy the canonical id: a paste is a new reference); id comparisons (is this chip the page's own entity?) by canonical id; live feeds: a page of A subscribes to its members' ids too |
| Export, TS types, SDK | `canonical` in `ReferenceView` and its TS type; the SDK's equality |
| Graph embeddings (planned) | The projection collapses members into one node |
| `IdentityClaim()` (part 2) | Still needed, for a different reason: its fields are **read as written** (no canonicalisation), so "A is the same as B" does not read "A is the same as A". `KeepOnMerge()` disappears (nothing moves) |
| **Custom Cypher** (an app's own queries, `requires={"cypher"}`; a project's; data migrations) | Every one that matches an entity by id, or reads an entity's fields after reaching it from a document, must follow the two rules, **for ever**. See below |

### Custom Cypher: the real cost

Today an entity is a node: `MATCH (p:Person {id: $id})<-[:involves]-(d)` is right. Under this design it is wrong as soon
as one person has been merged into another, and **only then**. It gives A's documents without B's, and nothing fails.
And `MATCH (d:Factoid)-[:involves]->(p:Person) WHERE p.born > ...` tests B's dormant date. On a database where nothing
has been merged, every such query gives the right answer, and **every test passes**, because `canonical_id = id`
everywhere. The bugs are latent until the first merge, and then give wrong answers without an error. That runs against
"fail early and loudly".

What would contain it:

- **Fragments for both rules** in `pangloss_cypher.fragments` (`entity_members(var, param)`, `canonical(var, as_)`,
  `not_merged(var)`), as there are for `visible` and `not_deleted` now; the add-on guide says to use them.
- **An alias fixture in `pangloss-testing`**: a data set in which every entity has merged aliases and documents refer
  to them at random, so that a query that forgets a rule fails a test. Run the conformance suite, every add-on's tests
  and the e2e suite on it as well. This is what would make the design safe in the packages. A project's own queries
  are only safe if the project runs its tests on it too.
- **No static check is possible** in general: the queries are strings. A grep for `{id: $` near `:Entity`-ish labels in
  `pangloss check` would catch some.

### Compared

| | Moving references (part 1) | By pointer (this section) |
|---|---|---|
| A merge writes | every head that refers to B (a version each), in batches above 1,000 | a few entity nodes, one transaction |
| Atomic | only small merges | always |
| Undo | from the record of moves; partial if documents changed; in order | exact, any order |
| History, migrations, bulk load | each needs rules (the safeguards discussed on 2026-11-12, not yet written into this page), or data is damaged | nothing particular |
| Every read and query | unchanged: an entity is one node | two rules, everywhere, for ever |
| When a rule is missed | **data damaged** (in a few places, all in the core, checkable by invariants) | **wrong answers**, silently (in any query, including a project's own) |
| Performance | none after the merge | an index lookup per entity reached; search patterns one hop more (to measure on the 642k database) |
| Others' documents | get versions they did not write | untouched; their labels keep B's name |
| After many years | the graph is plain | aliases accumulate (unless merges are later consolidated) |

**A query builder** (a "Cypher in Python" language, such as [Pypher](https://github.com/emehrkay/Pypher), through which
every query would be written, and which would always look up the canonical entity) was suggested by the user as a way
to enforce the two rules. Not taken up: Pypher only builds strings (it does not know which nodes are entities, so it
cannot add the hops itself) and has `raw()`; a builder that knew the models would be a large new part, against the
principle that Pangloss has no Cypher query builder so that query text stays visible and tuned for each planner; and
any escape to plain Cypher brings the silent errors back. The way there, if it is ever wanted, is to grow the typed
search (`Model.Where`), which already compiles in one place, until projects need little Cypher of their own.

**A hybrid** (a merge is a pointer at first, then *consolidated* by an admin after a waiting period, by moving the
references as part 1 does, after which undo is through history only) bounds how many aliases exist, but not the rule:
every query still has to follow it, since there are always recent merges.

### My view

The pointer design is the better one for the data: it cannot damage anything, and its undo is exact. The cost is that
it changes what "an entity" means in every query, and the failures are silent wrong answers that appear only after a
merge, in queries written by anyone, including you, for as long as the project lasts. The moving design puts the
danger in one operation in the core, where a finite list of safeguards (restore, migrations, bulk load, the invariant counts) and invariant checks can
cover it, and leaves every query as it is.

So I would still choose **moving references**, with the safeguards, unless one of these is true: merges will be
frequent and often wrong (then exact undo matters more); or projects will rarely write their own Cypher (then the
alias fixture over the packages covers almost everything). Both are the user's knowledge of how Pangloss will be used,
not mine.

## How the three fit together

- The usual life of a duplicate: someone finds it is a duplicate, and **merges** (part 1). If they are wrong, they
  undo.
- The usual life of a scholarly identification: a factoid with a `SameAs` statement (part 2), citing its evidence
  (part 3). The entity page shows it at the top. When the identification is accepted, a person may **merge**. The
  statement stays (its `IdentityClaim()` edges are not moved) and records why.
- Part 1 needs nothing of parts 2 and 3 but `KeepOnMerge()`, one field marker. Part 2 is useful
  without part 3 (evidence as text, or as the factoid's source). Each can be built and used alone.

## Prevention: "did you mean…?" (later)

Noted for later, as the user asked. When a person is made (the create dialog, the companion form, the new page), the
form asks for likely existing candidates as the label and the first fields are typed. First by name (the autocomplete
with folded and variant spellings, and B-labels of merged entities resolving to survivors, from part 1). Later by the
company the new person keeps (the factoid being written), with the graph-embedding overlay of
[graph-embeddings.md](graph-embeddings.md) ("The vector of something not yet written") and the reconcile stage of
[similarity-plan.md](similarity-plan.md). It shows "Did you mean: [chip] [chip]?" with a "use this one" button.
Nothing is built until the similarity work is. Recorded in `TODO.md`.

## Order of work

1. `KeepOnMerge()` in the core and `IdentityClaim()` in the library (field markers, exported, no data).
2. Merge: `relink` taking an open transaction → preview and checks (with the validation of collapsed heads) → `PGMerge` + relink with recorded moves, the counts before and after, the migration
   state, one transaction below the size limit → one resolution of merged ids for writes and bulk load →
   reads/lists/autocomplete → undo (with the migration check) → history's `merged` conflict → `pangloss check-data`
   → conformance tests on both backends (every kind of relation; the restores; a migration between merge and undo) →
   API, SDK, CLI → proposals and verification → the comparison page, the undo screen, notices → e2e. See "Risks and
   safeguards".
3. The identity section on the entity page (interface only, over the reverse edges). `SameEntity[T]` in the library;
   the demo's factoids get one.
4. Part 3: `Cites[T]` and `PGCitation` in the model layer and export → the normalised hash → the protection check on
   write (measured), with the rules for deleted and unpublished citing documents and the admin override →
   the lock and warning in the form → the picker and chips → history/review/migrations/RDF rows.
5. Derived rule and search operator for reading through identities.

## Decisions for the user

**Decided by 2026-11-12** (✅ below). What was asked, and the choices, are kept for the record.

1. ✅ **Who may merge** (decided 2026-11-12): a per-project setting, defaulting to admins; any logged-in user may
   propose a merge, and a second logged-in user may verify it. See "Proposing and verifying a merge".
   - 1a. ✅ **Who may undo** (decided 2026-11-12): the same rule. Admins directly (as `MERGE_DIRECTLY` says);
     anyone else proposes an undo (a `PGMerge` gains `undo_proposed_by`/`when`), and a second, different logged-in
     user accepts it, which carries it out. It shows where merge proposals show.
   - 1b. ✅ **The verifier** (as the user put it in 1): any other logged-in user, until there are roles. Was: any other logged-in user, or only one with some role? *Recommended: any other
     logged-in user, as decided, until there are roles (access control is still open in `TODO.md`).*
2. ✅ **A request for a merged id (B)** (decided): answer with A, marked `merged_from`; the interface redirects its
   page.
3. ✅ **A write naming a merged id** (decided): resolve to A and say so in the response.
4. ✅ **The absorbed entity's label** (decided 2026-11-12): both. Kept on B (a name search finds A through it) and
   copied into a list field the project names (`MergeRules(label_into="aliases")`).
5. ✅ **Documents that referred to both A and B in one list** (decided): collapse to A once, and list the document
   in the merge summary.
6. ✅ **Undoing in a chain** (decided): only the most recent merge first.
7. ✅ **Identity in queries** (decided): opt-in only (page toggle, search operator, derived rule).
8. ✅ **Transitivity** (decided): **the whole cluster by default**, "one step only" as an option. See part 2,
   "Transitivity", for what joins a cluster and how a contradiction is shown.
9. ✅ **Documents citing documents** (decided): `Cites[T]`, an indexed id on a `PGCitation` node of the citing
   document, built after merge and the identity section.
10. ✅ **Protecting a cited statement** (decided 2026-11-12: (a), and deleting a cited factoid is refused). Was: (a) a change needs the confirmed warning (`acknowledge_citations`) and marks the
    citation "changed since cited"; a removal is refused until the citation is changed; (b) both refused outright
    until the citations are changed; (c) both allowed with the warning. *Recommended: (a).* And deleting the whole
    cited factoid: refused like a removal, or allowed (undoable) with the citation struck through? *Recommended:
    refused.*
11. ✅ **Names** (decided): `Cites[T]`, `IdentityClaim()`, `KeepOnMerge()`, `SameEntity[T]`.
12. ✅ **Where `SameEntity[T]` lives** (decided 2026-11-12: `pangloss-library`, with `IdentityClaim()`). Was: (a) `pangloss-library`; (b) only in the project. *Recommended: (a), with the
    section working for any field marked `IdentityClaim()` so a project's own model works too.*
13. ✅ **The survivor's class** (decided 2026-11-12): the narrower by default, the person merging may choose. See
    "When the classes differ".
14. ✅ **Sibling classes** (decided 2026-11-12: (c)). Was: (a) refuse, and say to change one entity's
    class first (the comparison page offers it); (b) the survivor takes the nearest common parent (`Person`), and
    both entities' own fields are listed as not kept; (c) a class that is both, if the models have one
    (`class PoetSoldier(Poet, Soldier)`), else (a). *Recommended: (c), which is (a) in most projects.*
15. ✅ **The safeguards marked *to confirm*** (decided 2026-11-12: all three) in "Risks and safeguards": (a) a size limit, `MERGE_LIMIT` (default
    1,000 heads), above which a merge needs an admin, and below which it is one transaction; (b) citations from
    unpublished documents warn but do not block; (c) an admin may override the protection of a cited statement.
    *Recommended: all three.*
16. ✅ **`KeepOnMerge()` fields and the resolution of merged ids** (decided 2026-11-12): not resolved.
17. ✅ **Hiding B in lists, showing it in statements** (decided): `visible` unchanged, a new `listed` fragment.
18. ✅ **How the mark is stored** (decided): a property on B; no edges.
19. ✅ **A write addressed to B itself** (decided): refused with 409, naming A.
20. ✅ **Atomicity below the limit** (decided): `relink` takes an open transaction.
21. ✅ **Undoing A ← B while A ← C stands** (decided): allowed; A's fields are reconciled by a person, never restored.
22. ✅ **A document naming A and B in different fields; A and B naming each other** (decided): moved and listed; no
    self-reference is made.
23. ✅ **A collapse that breaks validation** (decided): the merge is refused, naming the heads.
24. ✅ **A write that races the merge** (decided): mark first, a second pass, `check-data`; no lock on ordinary writes.
    Measured: enough on Memgraph; on Neo4j the second pass has to be delayed.
25. ✅ **Deleting a survivor** (decided): allowed; undo waits for an undelete.
26. ✅ **Stored payloads after a migration** (decided): proposals go stale; kept fields are a draft.
27. ✅ **The class in the route** (decided): the API gives A as it is; the SDK raises a typed error if the class does
    not fit.
28. ✅ **Zotero** (decided): the linked item must be the survivor.
29. ✅ **Head fields in the cited hash** (decided): those the head's class names (`cited_with`), none by default.
30. ✅ **A citation racing a removal** (decided): the citing write writes a count on the cited head. Measured: see
    "Measured before building".
31. ✅ **Undeleting a citing document whose target is gone** (decided): undeleted, marked "removed since cited".
32. ✅ **What may be cited** (decided): any document node `T` allows, heads and the same head included.

See "Details settled" for each.
