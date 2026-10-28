# Review: checking documents before they are published

`pangloss-review` lets a document be checked by another user before the public sees it. Add `"pangloss_review"` to
`INSTALLED_APPS`, and say which models are reviewed:

```python
from pangloss_models.model_bases.document import Document
from pangloss_review.meta import ReviewMeta


class Letter(Document):
    _review_meta = ReviewMeta(reviewable=True)
    title: str
```

A subclass of `Letter` is reviewed too. A model with no `_review_meta` is not: its documents are published as
they are saved, so installing the package changes nothing until you mark models.

## What happens

- A new `Letter` is **unpublished** and its status is `unchecked`. People who are logged in see it, with the
  rest of the data; a request that is not logged in does not (it is "not found", like a deleted document).
  Nothing about review is sent when you create or update a document: `Letter.Create(...)` is as it was.
- Someone sets its status: `checked` (no errors found) **publishes** it; `errors_found` does not, and
  `unchecked` takes it back. By default anyone may check, even the author; set `REVIEW_ALLOW_SELF_REVIEW = False`
  and a user cannot check a document they created or last edited.
- **Editing does not change the status.** A published, checked document stays so when it is edited. If the
  change should be checked again, the person who made it sets the status back to `unchecked`, which unpublishes
  it.
- Anyone logged in can **comment** on a document, or on a part of it (a nested document: give its `id` as
  `targetId`). A comment keeps what the part was called when it was made, and can be marked resolved.

## Reading it

The state is in the `meta` of a document that is read: `published` and `reviewStatus` (`null` for a model that is
not reviewed); a list and a search carry them too, in each item's `meta`, and a list can be filtered:
`GET /api/Letter?published=false&review_status=unchecked` (in Python, `Letter.list(published=False, review_status="unchecked")`).
A search can use them as well: `{"type": "Letter", "where": {"review_status": {"eq": "unchecked"}}}`.
What is not published is not listed for a request that is not logged in, whatever it asks. Its comments are a separate request, so that reading a document stays light:

| | |
|-|-|
| `GET /api/review/queue?status=unchecked&type=Letter` | The documents to check, oldest change first (`status` can be repeated) |
| `GET /api/review/{id}` | The state and the open comments (`?resolved=true`: all) |
| `POST /api/review/{id}/status` | `{"status": "checked", "comment": "optional"}` |
| `POST /api/review/{id}/comments` | `{"text": "...", "targetId": "<id of a part>"}` (`targetId` is optional) |
| `POST /api/review/{id}/comments/{commentId}/resolve` | |

All of them need a login. Errors: `404` (no such document, or not a reviewed class, or no such comment), `403`
(you may not check your own work, if that is off), `422` (the part is not in the document).

From Python, `pangloss_review.service` does the same (`get_state`, `set_status`, `add_comment`, `list_comments`,
`resolve_comment`, `queue`). On the command line: `pangloss review queue`, `pangloss review show <id>`,
`pangloss review set <id> checked --user ann`.

## Loading data that is already right

Data made outside the system, and known to be correct, need not wait to be checked. Say so when you save it:

```python
await Letter.Create(label="...", title="...").save(published=True)          # checked: published at once
await Letter.Update(id=id, ...).save(review_status="errors_found")          # or any of the three statuses
```

- Or in the document itself, for a load in which some items are checked and some are not: `Letter.Create(..., review_status="checked")` (`reviewStatus` in JSON, and a line of a `bulk-load` file can have `"review_status": "checked"`). What the document says wins over what the call says.
- `published=True` is `review_status="checked"`, `published=False` is `"unchecked"`; give one or the other.
- It is written with the document, in one request, as `?review_status=checked` on the `POST`/`PUT` of the API; the
  reviewer shown is the user who saved it.
- Without it, a new document is `unchecked` and an update leaves the state alone, as before.
- It works for documents of reviewed classes only; for any other it is ignored (so a mixed load needs no `if`).
- If `REVIEW_ALLOW_SELF_REVIEW` is false, asking for a status is refused (403): the writer is the author.
- In a script on the server, `with pangloss_review.meta.with_status("checked"): ...` does the same for what is
  saved inside the block.

## Things to know

- A document written before you marked its class has no status, and counts as
  published and checked.
- Entities are not reviewed.
- If a part of a document is removed, comments about it stay, and say what it was called.
