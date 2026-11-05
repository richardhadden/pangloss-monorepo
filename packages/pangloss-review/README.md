# pangloss-review

Optional. Documents are checked by a user before they are published. Add `"pangloss_review"` to `INSTALLED_APPS`
and mark the models to review:

```python
from pangloss_review import ReviewMeta


class Letter(Document):
    _review_meta = ReviewMeta(reviewable=True)
```

A new `Letter` is then written unpublished (`published: false`, status `unchecked`); only logged-in users see it.
Another user sets its status to `checked` (published) or `errors_found`, and anyone can comment on it, or on a part
of it. The design is in [docs/review.md](../../docs/review.md).

Settings (optional): `REVIEW_ALLOW_SELF_REVIEW` (default `True`; when false, a user cannot check a document they
created or last edited).

With `pangloss_interface` installed, a reviewed document has a review button in its console, which opens a panel with
the status and the comments, kept up to date while the page is open (`#` in a comment chooses a part of the
document), and `/review` lists the documents to check (`src/pangloss_review/interface/`, an interface module;
`interface_config.py` links it from the navigation bar; [docs/review-interface.md](../../docs/review-interface.md)).

Guide: [guide/review](../../guide/review/README.md).
