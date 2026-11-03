"""The indexes and unique keys of the nodes of derived relations (not models): read by the database package, which puts
them in the snapshot that migrations are made from, so that `makemigrations` knows `migrations/0001_initial.py` makes
them."""

INDEXES = [
    {"kind": "label+property", "label": "PGDerived", "properties": ["key"]},
    {"kind": "label+property", "label": "PGJustification", "properties": ["key"]},
    # (the justifications of a rule: a rule built again, or removed; the graph of a type of rule)
    {"kind": "label+property", "label": "PGJustification", "properties": ["rule"]},
    {"kind": "label+property", "label": "PGDeriveRule", "properties": ["name"]},
    {"kind": "label+property", "label": "PGDeriveWorker", "properties": ["kind"]},
]

CONSTRAINTS = [
    {"kind": "unique", "label": "PGDerived", "properties": ["key"]},
    {"kind": "unique", "label": "PGJustification", "properties": ["key"]},
    {"kind": "unique", "label": "PGDeriveRule", "properties": ["name"]},
    {"kind": "unique", "label": "PGDeriveWorker", "properties": ["kind"]},
]
