"""The indexes and unique keys of comparison's own nodes (not models): read by the database package
(`pangloss_models.indexes.installed_app_structure`), which puts them in the snapshot that migrations are made from, so
that `makemigrations` knows `migrations/0002_models.py` makes them (step 6.6).

- `PGCompareModel`: a fit of people's judgements (`fits.py`), one for each fit written, none deleted: unique by its
  `id`, and indexed by it (`pangloss compare learn --use ID`; Memgraph's unique constraints make no index). Finding
  the one in use is a scan of the label (a fit is written by hand, now and then: few of them), made on every request
  of the route (`fits.in_use_in`): no index of `in_use`, which would save a scan of so few.
"""

INDEXES = [
    {"kind": "label+property", "label": "PGCompareModel", "properties": ["id"]},
]

CONSTRAINTS = [
    {"kind": "unique", "label": "PGCompareModel", "properties": ["id"]},
]
