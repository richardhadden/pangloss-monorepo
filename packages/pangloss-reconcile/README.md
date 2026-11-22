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
- An interface module (`interface/`): in review's reconcile dialog (the place `reconcileCandidates`), the best
  candidates of the mention under "Suggested", each with its score, whom it is also named with, and Choose. Its
  tests run in a built project (`npx vitest run --root modules/pangloss_reconcile` in `.pangloss/interface`); the
  e2e suite does that.

The reference is `implementation_docs/reconcile.md`.
