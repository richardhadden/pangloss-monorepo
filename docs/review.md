# Review: checking documents before they are published ⏳

**Status: built and tested (uncommitted until asked): the `published` flag, the package, the API routes, the commands, the guide ([guide/review](../guide/review/README.md)).** The package is `pangloss-review` (`INSTALLED_APPS = ["pangloss_review"]`). The
decisions marked **(decided)** were made by the user; **(open)** ones are still to settle; the rest follow from how
`deleted`, meta slots and `pangloss-history` already work.

## What is wanted

- A head document can be checked by another user before it is published. A document that is not published cannot be
  seen (like one that is deleted), except by those who review or wrote it.
- Status: **unchecked** (the default), **checked, errors found**, **checked, no errors found** (which publishes it).
- Comments on a document: a list of (user, date, text), optionally about one of the documents nested in it.
- A project that does not install the package sees no difference: everything is published.

## `published`: the core part

`deleted` is not a model field. It is a property of the head node that the Cypher builders test
(`NOT coalesce(n.deleted, false)`, with a nested document taking its head's): `build_read_query`,
`build_list_query` (five places), `build_search_query` (three), `build_autocomplete_query`, `validate_write`,
`build_update_query`. `published` is the same kind of thing, so it goes in the same places:

- Stored on the head node as `published`. **No property means published** (`coalesce(head.published, true)`), so
  existing data and projects without review are untouched, and nothing needs migrating.
- Read, list, search, autocomplete and "what refers to this" skip a document that is not published, or nested in
  one, exactly as for `deleted`.
- Unlike `deleted`, some people must see them. **(decided)** A user who is logged in sees unpublished documents
  (in reads, lists and searches); a request that is not logged in does not. The ContextVar
  `pangloss_users.see_unpublished` says which (default `True`, so scripts, commands and tests see everything);
  the API sets it on every request (`dependencies.set_visibility`, an app-wide dependency: a valid token is
  `True`, none or a bad one `False`, and reading is still open). The Memgraph builders pass it as the query
  parameter `$see_unpublished`. A later `only` mode (the reviewers' queue) is the review package's, not the core's.
- New documents are written `published = false` **only when the review package is installed and the class is
  reviewable** (a listener on the write event, as history does, sets it in the same transaction); otherwise
  nothing is written, which is "published".
- An unpublished document may refer to published entities, and may be referred to by other unpublished
  documents; a published document refers to entities only, so nothing published points at it. (Documents are
  never the target of a relation, so hiding one hides no edge of anything else.)
- Entities are not reviewed (they are shared, and not part of any one document).

## The review state

On the head node (plain properties, so it can be filtered and indexed): `review_status` (`unchecked`,
`errors_found`, `checked`), `reviewed_by`, `reviewed_at`. `published` is `true` exactly when the status is `checked`
(set in one transaction with it). A status change is an event of its own and is written to the history of the
document if `pangloss-history` is there.

Which documents are reviewed is a meta slot on the class, `_review_meta = ReviewMeta(reviewable=True)` (meta slots
already exist for this), inherited. **(decided)** Opt-in: the default is not reviewable, so installing the package
changes nothing until models are marked.

## Comments

Memgraph properties cannot hold a list of maps, so a comment is a node, `(:PGReviewComment)` linked to the head
document, with `id`, `username`, `at`, `text`, and optionally `target_id` and `target_label`:

- `target_id` is the id of a nested document. Nested documents have ids, so a comment can name one. What the label
  of the part was **when the comment was made** is kept in `target_label`, so a comment still reads right if the
  part is later changed.
- If the part is later removed, nothing breaks: the comment is shown as being about a part that is no longer
  there ("orphaned"). Whether an id survives an update of the document has to be checked in the update builder before
  this is promised. **(to check)**
- A comment can be marked resolved (by anyone who can comment). Comments are not edited or deleted; a resolved one
  is just hidden by default.
- Comments belong to the head document and go with it when deleted; they are not part of the document's content,
  so they do not make a history version.

## Who may review **(decided)**

Permissions are not written yet (`docs/users.md`), and users have only `admin`. Anyone may check a document. The
setting `REVIEW_ALLOW_SELF_REVIEW` is **true by default**; set to false, a user may not check a document they
created or last edited (`PGCreation` / `PGUpdate`). A "reviewer" group is added when permissions exist.

## After a published document is edited **(decided)**

Editing does not change the review state: a document that was published and checked stays so. If the change is one
that should be checked again, the person who made it sets the status back (to `unchecked`, or `errors_found`),
which unpublishes it, as the status always decides `published`. (A later improvement: an "edited since checked"
marker in the queue, from the version number; not part of the first build.)

## API (under `/api/review`, added by the package)

| Route | |
|-------|-|
| `GET /api/review/queue?status=&type=` | Documents to check (unpublished, by status), newest first |
| `GET /api/review/{id}` | Status, who and when, and the comments |
| `POST /api/review/{id}/status` | `{status, comment?}`; refused for the author unless allowed |
| `POST /api/review/{id}/comments` | `{text, target_id?}` |
| `POST /api/review/{id}/comments/{cid}/resolve` | |

and `pangloss review queue|status|publish-all` commands (`publish-all` for a project that adopts review late: it
marks the reviewable documents there as `checked`).

## Not in this package

The interface (a review page, comments next to the parts they are about): nothing is added to interface pages until
asked. Email or other notices.

## Build order

0. ✅ Ids of nested documents. An update deletes the tree under the head and writes it again, but a nested
   document in the `Update` must carry its `id` (required), so a part sent back with its id **keeps it**; a new part
   needs an id from the client; a part left out is gone. A comment's `target_id` is therefore stable as long as
   the client sends parts back unchanged (the interface does). This turned up a defect: the update **replaced all
   properties of the head node**, which would have published an unpublished document when it was edited, and lost
   the review state. `KEPT_PROPERTIES` (`published`, `review_status`, `reviewed_by`, `reviewed_at`) in
   `build_update_query.py` are now kept; tested in `test_unpublished_live.py`.
1. ✅ Core: `published` in the read, list and search builders with `$see_unpublished`, the API dependency, and `test_unpublished_live.py`. (Not filtered, on purpose: autocomplete and entities, `validate_write`, deletion's "what refers to this", which must still count an unpublished document.)
2. ✅ The package (`packages/pangloss-review`): `ReviewMeta` (slot `_review_meta`), `service` (`get_state`, `set_status`, `add_comment`, `list_comments`, `resolve_comment`, `queue`), the Memgraph side (`databases/memgraph/review.py`, `*_in_db` in `exposed_functions`), tests in `pangloss-memgraph/tests/test_review_live.py`. Two differences from the plan above: a new document is made unpublished by a **new core hook, `hooks.new_head_properties`**, called by the create query (a listener to `after_write` runs after the commit, so the document would have been visible for a moment); and the hook is installed when `pangloss_review.meta` is imported, which a model that is marked has done, so it works even if the app is not in `INSTALLED_APPS`. A document of a class that became reviewable later has no status and counts as published and checked. Documents loaded by `bulk-load` are not given the properties (they are published).
3. ✅ (done, with the meta change below) The API routes, the commands, the guide page, settings (`REVIEW_ALLOW_SELF_REVIEW`).

## Reading the state: in the `meta`, and the comments apart **(decided)**

`published` (default true) and `review_status` (`null` unless review keeps one) are in `meta` of a head view, read
by the same query as the document (`build_read_query`), so a page can show "unchecked" without another request.
They are read only: `Create` and `Update` have no review fields, the create hook sets the state, and an update keeps
it (`KEPT_PROPERTIES`). A document of a class that became reviewable later reads `reviewStatus: null`, though
`GET /api/review/{id}` says `checked`. Comments are not in the view: `GET /api/review/{id}` has them. The reference view carries them too (`meta.published`, `meta.reviewStatus`: the list, search and queue queries fill them in), and a list can be filtered by them: `?published=` and `?review_status=` on `GET /api/<Model>`, `published=` and `review_status=` on `Model.list(...)`, in the SDK and the type stubs. The filter is applied to the head document after the visibility test, so a request that is not logged in finds no unpublished document whatever it asks. Structured search can too: `published` and `review_status` are conditions of a head document's `where` (see [structured search](structured-search.md#published-and-reviewed-built-with-pangloss-review)).
`publish-all` was dropped from the plan: a document with no status counts as published already.
