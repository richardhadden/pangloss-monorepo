# pangloss-review

Optional. Documents are checked by a user before they are published. Add `"pangloss_review"` to `INSTALLED_APPS`
and mark the models to review:

```python
from pangloss_review.meta import ReviewMeta


class Letter(Document):
    _review_meta = ReviewMeta(reviewable=True)
```

A new `Letter` is then written unpublished (`published: false`, status `unchecked`); only logged-in users see it.
Another user sets its status to `checked` (published) or `errors_found`, and anyone can comment on it, or on a part
of it. The design is in [docs/review.md](../../docs/review.md).

Settings (optional): `REVIEW_ALLOW_SELF_REVIEW` (default `True`; when false, a user cannot check a document they
created or last edited).

Guide: [guide/review](../../guide/review/README.md).
