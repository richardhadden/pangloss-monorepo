# Review: checking documents before they are published

`pangloss-review` lets a document be checked by another user before the public sees it. Add `"pangloss_review"` to
`INSTALLED_APPS`, and say which models are reviewed:

```python
from pangloss_models import Document
from pangloss_review import ReviewMeta


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
- Someone sets its status: `published` (checked, no errors found) **publishes** it; `errors_found` does not, and
  `unchecked` takes it back. (Until 2026-11-10 the status was called `checked`: that name is still taken when you
  write a document, set a status or filter a list by it (a search needs the new name), and `pangloss migrate`
  renames what is stored.) By default anyone may check, even the author; set `REVIEW_ALLOW_SELF_REVIEW = False`
  and a user cannot check a document they created or last edited.
- **Editing does not change the status.** A published document stays so when it is edited. If the
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
| `POST /api/review/{id}/status` | `{"status": "published", "comment": "optional"}` |
| `POST /api/review/{id}/assign` | `{"username": "ann"}` (or `null`): who is to review it; see [Tasks](#tasks-and-who-they-are-given-to) |
| `POST /api/review/{id}/comments` | `{"text": "...", "targetId": "<id of a part>"}` (`targetId` is optional) |
| `POST /api/review/{id}/comments/{commentId}/resolve` | |

All of them need a login. Errors: `404` (no such document, or not a reviewed class, or no such comment), `403`
(you may not check your own work, if that is off), `422` (the part is not in the document).

From Python, `pangloss_review.service` does the same (`get_state`, `set_status`, `add_comment`, `list_comments`,
`resolve_comment`, `queue`). On the command line: `pangloss review queue`, `pangloss review show <id>`,
`pangloss review set <id> published --user ann`.

## Loading data that is already right

Data made outside the system, and known to be correct, need not wait to be checked. Say so when you save it:

```python
await Letter.Create(label="...", title="...").save(published=True)          # published at once
await Letter.Update(id=id, ...).save(review_status="errors_found")          # or any of the three statuses
```

- Or in the document itself, for a load in which some items are checked and some are not: `Letter.Create(..., review_status="published")` (`reviewStatus` in JSON, and a line of a `bulk-load` file can have `"review_status": "published"`). What the document says wins over what the call says.
- `published=True` is `review_status="published"`, `published=False` is `"unchecked"`; give one or the other.
- It is written with the document, in one request, as `?review_status=published` on the `POST`/`PUT` of the API; the
  reviewer shown is the user who saved it.
- Without it, a new document is `unchecked` and an update leaves the state alone, as before.
- It works for documents of reviewed classes only; for any other it is ignored (so a mixed load needs no `if`).
- If `REVIEW_ALLOW_SELF_REVIEW` is false, asking for a status is refused (403): the writer is the author.
- In a script on the server, `with pangloss_review.meta.with_status("published"): ...` does the same for what is
  saved inside the block.

## Tasks, and who they are given to

Three things are tasks of review, each a tab of the **Review** page (`/review`):

| Task | Is | Ends when |
|---|---|---|
| A document to check | A reviewed document that is `unchecked` or has `errors_found` | It is published |
| A mention to reconcile | An `Unreconciled` in a document (below), published or not | An entity is put in its place |
| An identification to confirm | An `IdentificationByToolchain` in a document (below) | A person confirms it |

A task is not a record of its own: the document, the mention or the suggestion *is* the task while it is there, so
there is nothing to keep in step. What is recorded is **who a document is given to**, and its mentions and
suggestions are that person's tasks too:

```python
await Letter.Create(...).save(review_assigned_to="ann")          # with the upload (an admin's, for someone else)
```

Over the API that is `?review_assigned_to=ann` on the `POST`, and `POST /api/review/{id}/assign` afterwards. Anyone may
take a task for themselves, whoever has it (the **Take** button), or give up their own; only an admin gives one to
someone else. The lists take `?assigned_to=me`, a username (another person's: for an admin) or `none`, and the page has
the same choice ("Tasks of"); `GET /api/review/tasks/summary` counts each kind.

## Uploading for others, and with a toolchain

Data is often made by a person and turned into documents by a program. An admin can upload it in their names:

```python
from pangloss_models import ToolchainRun

await Factoid.Create(...).save(
    created_by=["ann"],                                             # one person or several
    toolchain=ToolchainRun("extractor", version="1.2", date=date(2026, 11, 1)),
    review_assigned_to="bob",
)
```

`meta.created_by` of every item is a list of its makers, people first (`{username, kind, version, date}`), and
`meta.uploaded_by` is the admin who wrote it. A **toolchain** is a user that cannot log in: make it once with
`pangloss users create-toolchain extractor` (or **New toolchain** on the admin page). Its version and date belong to
each upload, not to the toolchain. Over the API: `?created_by=ann&toolchain=extractor&toolchain_version=1.2&toolchain_date=2026-11-01`,
for an admin only.

## Someone the source names who is not identified: `Unreconciled`

A program that reads sources often cannot say which person a name is: there is no one like it yet, or too many. Say
which entity classes may be left open, and every relation that takes one also takes an `Unreconciled` in its place:

```python
class Person(Entity):
    _review_meta = ReviewMeta(allow_unreconciled=True)


class Activity(Document):
    carried_out_by: Person                                     # takes a Person, or an Unreconciled
    witnessed_by: Annotated[Person, NoUnreconciled()]          # this one does not
```

```python
Activity(label="Lunch", carried_out_by={
    "type": "Unreconciled", "unreconciled_type": "Person", "label": "John Smith",
    "uris": ["https://example.org/people/123"],
})
```

- It is **part of the document** that mentions it, one for each mention: not an entity, not in the list of people.
  `unreconciled_type` must be a class the relation takes that allows it (a subclass too).
- On a page it is a chip with a **spanner**; in a form, a row with its label, its type and the same spanner. The
  spanner opens a dialog: find the entity (or make one with **+**), and **Reconcile**. The entity takes the mention's
  place by an ordinary update of the document (a new version, in its history, by you), and is given the mention's
  URIs that it does not have (one that another entity has is not moved, and you are told).
- The dialog lists **other mentions that may be the same**: the same entity class, and the same label but for case,
  accents and spacing (ticked), or one much like it (shown with how alike, not ticked). Those you tick are reconciled
  with the same entity in the background.
- A model can narrow what is offered together, on the class of the head document: the names of fields that must
  hold the same entities, or a function of the two documents.

  ```python
  class Factoid(Document):
      _review_meta = ReviewMeta(reviewable=True, reconcile_together=("source",))   # only within one source
  ```

- In the form of its document, reconciling is one more change of the form: the entity is put in the mention's
  place there, whatever else has been changed, and is saved with the rest. So someone working through a document
  reconciles each mention as they reach it, and saves once. The entity is given the mention's URIs at once, and
  the others ticked, in other documents, are reconciled at once in the background (those of the same document are
  changed in the form with it). On the page of reconciliations (`/review/reconciliations`) it is
  the saved document that is changed, at once.
- From Python: `pangloss_review.reconcile` (`list_mentions`, `similar`, `reconcile`); over the API,
  `GET /api/review/unreconciled`, `GET .../{id}/similar`, `POST .../{id}/reconcile {"entity": {"type", "id"}, "also": [ids]}` (with `"inForm": true`, its own document is
  left to the form that holds the change).

## An identification that a toolchain suggested

`pangloss-library` has `Identification[T]` (a name in a source that has been identified, and by whom: the server
says who, from whoever saves it) and `IdentificationByToolchain[T]`, the same made by a toolchain, perhaps with
several candidates and how likely each is (`WeightedAlternative`), and URIs for who it is:

```python
class Transfer(Statement):
    given_by: Person | Identification[WeightedAlternative[Person]] | IdentificationByToolchain[WeightedAlternative[Person]]
```

With review installed, each `IdentificationByToolchain` is a task. A person corrects it in the form as any other
part, and presses the yellow button in its bar, "Confirm identification" (before or after): it becomes an
`Identification` in the form, one more change of the form, and is saved with everything else that was changed.
So someone working through a document confirms each suggestion as they reach it, and saves once. When the document
is saved the server says who identified it (whoever saved), and gives the URIs.

The URIs are for whoever it is. A suggestion confirmed with one candidate gives them to that entity. One confirmed
with several candidates still open has nobody to give them to: the identification keeps them (its form shows them,
and they cannot be changed there), and when the document is later saved with one candidate left, that candidate is
given them.

Two things are asked about first, in a dialog. If it has one candidate and URIs, the URIs would go to that entity
when the document is saved: the dialog says who and which, so that they are not given to the wrong one (the URIs
are those the toolchain gave, as they are saved). And if suggestions in other documents have the same candidates,
each about as likely (within ten points), the dialog lists them: those you tick are given the identification the
form holds: those of the same document in the form, with it, and those of other documents at once and in the
background, whether or not the form is then saved. Otherwise the button confirms at once.

**The same URI.** A toolchain may give a mention or a suggestion URIs for who is meant (`uris`). Two that name
the same URI are of the same person, even where no one can say yet who that is in the database, so they are
offered first and ticked, whatever they are called and whoever their candidates are:

- confirming a suggestion offers the other suggestions of its URI (given the same identification), and, where it
  has one candidate, the unreconciled mentions of its URI (reconciled with that candidate);
- reconciling a mention offers the other mentions of its URI, and the suggestions of it (confirmed as the entity
  it is reconciled with, and no other);
- an entity that already has the URI is put forward to reconcile with; a suggestion whose candidates do not
  include that entity says so.

In a form, the URIs of a suggestion are shown and cannot be changed. After a bulk load, `pangloss review
index-uris` makes the index the URIs are found by.

A document saved in any other way with a suggestion written as an identification (the same `id`, another `type`:
a script, the API) is confirmed in the same way.

`/review/identifications` lists what is left. Nothing is confirmed from that table, where it would not have been
looked at: a row opens the form of its document at the suggestion. Over the API:
`GET /api/review/identifications`, `GET .../{id}/similar`, `POST .../{id}/confirm {"also": [ids]}` (the saved
suggestion, at once: an update of its document), `POST .../{id}/give {"also": [ids], "target": [...]}` (only the
others).

### Your own kind of suggestion

A project can subclass both, to say more of an identification. The suggestion names the class a confirmed one
becomes (`confirmed_as`); the fields the two share are kept, and what only the suggestion has is dropped. A field
that takes the suggestion has to take that class too.

```python
class Reading[T](Identification[T]):
    note: str | None = None


class SuggestedReading[T](IdentificationByToolchain[T]):
    confirmed_as = Reading
    note: str | None = None
    model: str | None = None      # of the suggestion only


class Transfer(Statement):
    given_by: Person | Reading[WeightedAlternative[Person]] | SuggestedReading[WeightedAlternative[Person]]
```

`confirmed_as` is `Identification` unless a subclass says otherwise, and is checked when the models are
initialised: it has to be an `Identification` that is not itself a suggestion.

## Things to know

- A document written before you marked its class has no status, and counts as
  published and checked.
- Entities are not reviewed.
- If a part of a document is removed, comments about it stay, and say what it was called.
- What is done "in the background" is done by the server after it has answered, one document at a time. If the
  server stops, what was not done is still a task, and is offered again.
