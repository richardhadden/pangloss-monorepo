# pangloss-reconcile

Reconciliation for Pangloss: for each stand-in of a document (review's `Unreconciled`: someone named and not yet
identified), the entities it may be, found and scored by the parts of similarity (`pangloss-vectors`), without
writing anything.

```python
INSTALLED_APPS = [
    ...,
    "pangloss_vectors",
    "pangloss_fastrp",
    "pangloss_names",
    "pangloss_reconcile",
]
RECONCILE_PROFILE = "who"  # the profile candidates are found and scored by
```

- `POST /api/reconcile/candidates`: a `Create` payload, checked as its create would be, and nothing written.
- `GET /api/reconcile/candidates/{id}`: a stand-in already stored, by its id.

The reference is `implementation_docs/reconcile.md`.
