"""The indexes of the nodes of vectors (not models): read by the database package, which puts them in the snapshot that
migrations are made from, so that `makemigrations` knows `migrations/0001_initial.py` makes them. (The vector indexes
come in step 2.2 of implementation_docs/similarity-build-plan.md.)"""

INDEXES = [
    # (the vectors of an item: read, replaced and deleted by its id)
    {"kind": "label+property", "label": "PGVector", "properties": ["of"]},
    # (the state of a part: its generation in use, when it was built, its signature)
    {"kind": "label+property", "label": "PGVectorState", "properties": ["part"]},
]

CONSTRAINTS: list[dict] = []
