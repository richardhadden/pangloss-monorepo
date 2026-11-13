# Status and roadmap

What works and what does not, in one page (rewritten 2026-11-10 from the status lines of the other pages; before
that it was of 2026-10-30). Each row links to the page with the detail; [the guides](../guide/README.md) show how to
use what works; what is outstanding as tasks is in [`TODO.md`](../TODO.md).

✅ built and tested · 🚧 partly built, the gaps said · ⏳ planned

Nothing is published: Pangloss is used from a checkout of this repository ([publishing](publishing.md) ⏳).

## The core

| | What | Not built |
|---|---|---|
| ✅ | **Declaring models** ([models](models.md), [relations](relations.md)): `Document`, `Entity`, `Embedded`, `Trait`, `NonHeritableTrait`, `EdgeModel`, `ReifiedRelation`, `SemanticSpace`, `Conjunction`; `Meta` options, inheritance, generics; `ViaEdge`, field binding, `Fulfils`, optional relations and embedded objects (`Person \| None`) | Lists of embedded objects; plain `dict` (use a `TypedDict`); the `"subtract"` wrapper; `Relation[Subject, Object]` is a placeholder |
| ✅ | **Literals** ([models](models.md)): pydantic's standard types through one registry (`pangloss_models.literals`), enums as plain values, lists, sets, tuples, `TypedDict`, `X \| None`; defaults and `Annotated` constraints carried to the generated models | |
| 🚧 | **Label templates** ([label templates](label-templates.md)): `Meta(label_template=...)` works a label out from what an item holds, nested documents first, in Python on every write and in the form as it is filled in (locked, a pencil to write it by hand); `label_auto`; `Formatter`s (a date) | Not measured on a large database; formatters only in English; the demo has no templates; see the page's "As built" |
| ✅ | **Companion documents** ([companion documents](companion-documents.md)): `Entity.Meta(companions=...)`: documents offered with a new entity in the dialog that makes it and on its own page, copying from the document behind, with the entity in each part; written with it in one transaction (`create_heads`, `POST /api/NAME/with-companions`, `save_with_companions`) if anything in them is filled in | Parts through wrappers; companions of a document made in a dialog; a text of each companion's own; offered for an existing entity |
| ✅ | **Generated models** ([generated models](generated-models.md)): `Create`, `Update`, `View`, `HeadView`, `EditView`, `ReferenceSet`, `ReferenceView`, the database models, `Where` and `Order`; validators once, `@create_validator`, `@before_create`, methods | |
| ✅ | **What a mistake in the models says** ([modelling DX](modelling-dx.md), [language server](language-server.md)): `PanglossModelError` naming model, field and fix; `pangloss check`; `pangloss-lsp` with its Zed extension | The VS Code extension compiles and has not been run |
| ✅ | **Storage** ([database abstraction](database-abstraction.md), [Memgraph](memgraph.md), [Neo4j](neo4j-implementation.md)): one implementation for Cypher databases (`pangloss-cypher`) with a dialect each; one conformance suite both pass; create, replace-on-update with a version check, flag-delete and undelete, reads, lists; accents folded in search on both | A backend that is not Cypher ([RDF report](rdf-oxigraph-feasibility.md)); removing deleted nodes for good |
| ✅ | **Bulk load** ([large data](large-data.md)): a JSON Lines file into an empty database, on either backend | Only entities with ids of their own can be referred to from a file |
| 🚧 | **Migrations** ([migrations](migrations.md)): `makemigrations`, `migrate` (forwards, backwards, dry run, batches, backup), `squashmigrations`, `check-data`; the API does not start with migrations pending | See its "Progress" |
| ✅ | **Search**: lists with text and [deep search](deep-search.md); [autocomplete](autocomplete.md); [structured search](structured-search.md) by a JSON pattern, typed in Python as [`Model.Where`](search-where-implementation.md); "search everything" | Deep search is still slow on a large database (a scan of the text index) |
| ✅ | **REST API** ([API](api.md)): CRUD for every document and entity, `If-Match` on updates, login by token or cookie, sessions that end, personal access tokens, CORS; routes and background tasks from installed apps | |
| 🚧 | **Users** ([users](users.md)): create, password (Argon2id), admin, disable; pages for users in the interface | Permissions beyond logged in / admin and a token's `read` / `write` |
| ✅ | **Command line** ([reference](cli.md), [every command](../guide/cli.md)): projects and apps from templates, the server, type stubs, commands from installed apps | |
| ✅ | **SDK** ([SDK](sdk.md)): a project's models as a package its server builds, checks and serves; async and blocking; `sdk-demo/` runs it from a clean environment | |
| ✅ | **Settings and logging** ([settings](settings.md), [logging](logging.md)) | |

## The interface

🚧 `pangloss-interface` ([architecture](interface.md), [still to document](interface-to-document.md)): a Solid 2.0
application rendered on the server, made from an export of the models.

| | What | Not built |
|---|---|---|
| ✅ | Home with search everything, a project's own pages ([homepage](homepage-and-pages.md)); navigation; list pages (virtualised, search, deep search); item pages with what refers to an item | |
| ✅ | Forms to make and edit any item, with [validation](interface-features.md#form-validation-in-the-interface), [unsaved-changes warning and stash](interface-features.md#unsaved-changes-and-stashed-items), cut, copy and paste, narrowing and widening a nested document ([implied types](implied-types.md) 🚧) | A suggestion to narrow without being asked |
| ✅ | [The search form](search-form.md) of a list | `$derived` |
| ✅ | [Interface modules](interface-modules-implementation.md): an app's own pages, cards and sections, and [the hooks](interface-features.md#interface-hooks-the-timeline-in-pangloss-dates-the-derived-section-in-pangloss-derived) they use | Edit cards |
| 🚧 | [Translations](translations.md): files for each app and project, the commands, every fixed text a slot | See the page |
| ✅ | [Look and feel](look-and-feel.md): one button, one table, one badge | |
| ✅ | Browser tests (`e2e/`, with `e2e/COVERAGE.md`), on the built interface and the development build | |

## Optional packages

| | Package | What | Not built |
|---|---|---|---|
| ✅ | `pangloss-history` ([history](history.md)) | Every version, diff, restore, also after the models have changed; a panel and a compare page in the interface | Reconciling a draft in the interface; purge |
| ✅ | `pangloss-review` ([review](review.md), [the update of 2026-11-10](review-update-plan.md)) | Unpublished until published; comments on a document or a part; a panel in the interface; tasks given to people (documents to check, unreconciled mentions, identifications a toolchain suggested), reconciled and confirmed singly or with others like them | Notices by email |
| ✅ | Several creators, toolchains ([users](users.md#toolchains-and-who-made-an-item-)) | `meta.created_by` is a list; an admin uploads in the names of people and a toolchain (a user that cannot log in) | Naming others on an update |
| ✅ | `pangloss-dates` ([dates](dates-implementation.md); the wider first design: [dates.md](dates.md)) | Uncertain dates, ranges, periods, recurrence, Julian and Gregorian; `Dateable`, a timeline on the item page | Probability maths, relative dates |
| 🚧 | `pangloss-calendar` ([calendar](calendar-implementation.md)) | Days, months, years, feasts by rule or by hand, Easter, the date-first query; pages for years, a month, a day | See the sections that say "Not done" |
| 🚧 | `pangloss-typology` ([typology](typology-implementation.md)) | Vocabularies in a hierarchy, moved and merged safely; a live drag-and-drop tree | The tree picker; `$under` in a search |
| ✅ | `pangloss-derived` ([derived](derived.md)) | Rules that derive relations from documents, kept up to date by a worker | Recursion, aggregates |
| 🚧 | `pangloss-zotero` ([Zotero](zotero.md), [as sources](zotero-sources.md)) | A library kept in the database, one way; items as sources and subjects | **Never run against the real Zotero** |
| 🚧 | `pangloss-rdf` ([RDF](rdf.md), [plan](rdf-export-plan.md)) | Every item as RDF, a generated ontology, mixins for CIDOC-CRM | See the plan's "As built" |
| 🚧 | `pangloss-admin` ([admin](admin.md)) | `/admin` and long-running jobs in a process of their own; the RDF dump is the first job | See the page |
| ✅ | `pangloss-library` ([shares](shares-plan.md), [identity](entity-identity.md)) | Ready-made models: `WeightedAlternative`, `Likelihood`, `Identification`; `SameEntity[T]` and `IdentityClaim()` (a statement that two entities are one), with a section on an entity's page listing what it is said to be the same as. Reading through them, only when asked: the cluster of an entity (`pangloss_library.clusters`, `GET /api/identity/{id}/cluster`), its size and warnings on the page, what is said of the others shown on the page (`?same=all`), and the search key `$same_as` | A derived relation for identity; `$same_as` in the search form; the cost on a large database, measured |
| ✅ | Citations ([duplicate entities](entity-identity.md), part 3) | `Cites[T]`: a document names another, or a part of one, by id (a `PGCitation` node of the citing document). Checked when written; what is cited cannot be changed without `acknowledge_citations` (each citation is then marked changed) nor removed or deleted, but by an admin; `GET /api/NAME/{id}/cited`; in the interface, chips, a picker, "cited as evidence" and the question on saving. Not built: the lock in the form, RDF, search and derived rules through citations |
| 🚧 | Merging entities ([duplicate entities](entity-identity.md)) | `Entity.merge` and `unmerge` on both backends: references moved and recorded, the absorbed entity kept and its id resolved in reads and writes, `KeepOnMerge()`. The API (`/api/NAME/{id}/merge`, `/api/merges`), the SDK, `pangloss merge`/`unmerge`/`merges`; a merge proposed by one user and verified by another (`MERGE_DIRECTLY`); history refuses the restores a standing merge rules out; `pangloss check-data --move-merged`. In the interface (a module of `pangloss_interface`): **Merge with…** on an entity, the comparison page, proposals verified or rejected, the undo screen, `/merges`, notices on the entities, the merges made lately and a check job on `/admin` | Proposals in the review queue; a "move to B" action after an undo; the autocomplete marking a merged label; `owl:sameAs` in RDF; citations |
| ✅ | `pangloss-testing` ([backend-neutral add-ons](backend-neutral-addons.md)) | Fixtures for either backend; the conformance suite | |

## Measured

On about 640,000 nodes: [large data](large-data.md), [the two backends compared](backend-comparison.md),
[profiled](backend-profiling.md), [derived relations](derived.md#measured), and
[structured search](structured-search.md).

## Open design questions

- How to tell specific, multi-tenant and generic roles apart ("Prime Minister of the UK", "poet laureate", "prime
  minister"), and when an activity should become a role: [`notes/modelling.md`](../notes/modelling.md).
- Access control: reads need no login and a write needs only a login. Whether that is intended is in
  [`TODO.md`](../TODO.md).
- A trial of DozerDB, listed and not run: [dozerdb-trial.md](dozerdb-trial.md).
