# Citing another document

A document usually *contains* its parts: a factoid's statements are written with it and belong to it. Sometimes a
document needs to point at a statement that belongs to another document, as evidence, without copying it. That is a
**citation**.

```python
from pangloss_models import Cites, Document


class Inference(Statement):
    evidence: list[Cites[Statement]]      # statements of other factoids, named by id
```

`Cites[T]` allows any document of class `T` or a subclass, whether it is a document of its own or a part of one. Write
`Cites[Note | Factoid]` for several classes, and `Cites[Note] | None` for one citation that may be absent. Only
documents can be cited; an entity is referred to as it is.

A model that gains a `Cites` field needs a migration (`pangloss makemigrations`, then `pangloss migrate`).

## Writing and reading one

A citation is written as a reference is:

```python
await Factoid.Create(
    label="…",
    source=…,
    statements=[{"type": "Inference", "text": "They are one person", "involves": [], "places": [],
                 "evidence": [{"type": "Birth", "id": birth_id}]}],
).save()
```

What comes back is a `PGCitation`, which says what is cited as it is now:

| Field | What it is |
|---|---|
| `target_id`, `target_type`, `target_label` | The cited document |
| `target_head_id`, `target_head_type`, `target_head_label` | The document it is in (itself, if it is not a part) |
| `target_spaces` | The semantic spaces round it (`["Negative"]`) |
| `target_state` | `there`; `removed`; or `hidden`, for a reader who may not see an unpublished document |
| `changed_since_cited` | What is cited has been changed since (see below) |
| `cited_version`, `cited_label` | The version of its document, and its label, when it was cited |

Send it back as you read it when you update the citing document. A citation of something that does not exist, is
deleted, or is of a class the field does not allow is refused (`PanglossReferenceError`; 422 from the API).

## What is cited is protected

Evidence that changes under the document that relies on it is a problem, so:

- **A change** to a cited document or part is refused (`PanglossCitedError`; 409 from the API, naming the citing
  documents) unless the write acknowledges the citations. It then goes ahead, and each citation is marked
  `changed_since_cited`.
- **Removing** a cited part, or **deleting** its document, is refused until nothing cites it. An admin may override.

```python
await Factoid.Update(**data).save(acknowledge_citations=True)          # a change
await Factoid.delete(id, acknowledge_citations="removals")             # an admin's override
```

Over the API these are `?acknowledge_citations=changes` and `?acknowledge_citations=removals` (403 unless an admin).

What counts as a change: the fields of the cited part and of anything inside it, and the entities it names. Not the
rest of its document, unless the document's class says a field belongs to every part of it:

```python
class Factoid(Document):
    _meta = Document.Meta(cited_with=["source"])    # a new source is a change to each cited statement
```

A citation in a deleted document does not count. One in a document that is not yet published never refuses anything,
but is marked. Merging two entities that a cited statement names is not a change.

The mark stays until the citing document is saved with `changed_since_cited` false, which says that someone has
looked at the change. A citation whose target an admin removed reads `target_state: "removed"`; `pangloss check-data`
lists these.

`await Factoid.cited_by(id)` and `GET /api/Factoid/{id}/cited` say who cites a document and its parts.

## In the web interface

- A citation shows as the cited document's chip, linked to its place, with the document it is in beside it.
- In a form, **Add** opens a search: find the document, then choose which part of it to cite.
- A document that others cite says so above its contents ("Cited as evidence"), and in its form.
- Saving a change to something cited asks first, naming the documents that cite it; **Save anyway** marks their
  citations "changed since cited". A removal is not saved (an admin has **Remove anyway**).
- In the citing document's form, **Seen** on a marked citation takes the mark off when you save.
