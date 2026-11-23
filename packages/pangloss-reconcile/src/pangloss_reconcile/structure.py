"""The indexes and unique keys of reconciliation's own nodes (not models): read by the database package
(`pangloss_models.indexes.installed_app_structure`), which puts them in the snapshot that migrations are made from, so
that `makemigrations` knows `migrations/0001_initial.py` makes them (`decisions.py`; step 11.4 of
implementation_docs/similarity-build-plan.md).

- `PGReconcileShown`: what the stored route offered, one for each stand-in and user (unique on both: the `MERGE` of a
  second request finds the first's); found by its stand-in when it is resolved (the index of `stand_in`);
- `PGReconcileExample`: what was offered and what was chosen of it, one for each stand-in (unique). Indexed by
  `stand_in` too, for the `MERGE` that replaces an earlier one: Memgraph's unique constraints make no index. Reading
  them all is a scan of the label, for which no label+property index would serve.
"""

INDEXES = [
    {"kind": "label+property", "label": "PGReconcileShown", "properties": ["stand_in"]},
    {
        "kind": "label+property",
        "label": "PGReconcileExample",
        "properties": ["stand_in"],
    },
]

CONSTRAINTS = [
    {
        "kind": "unique",
        "label": "PGReconcileShown",
        "properties": ["stand_in", "user"],
    },
    {"kind": "unique", "label": "PGReconcileExample", "properties": ["stand_in"]},
]
