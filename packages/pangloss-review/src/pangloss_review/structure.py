"""The indexes of review's own nodes (not models): read by the database package, which puts them in the snapshot that
migrations are made from, so that `makemigrations` knows `migrations/0003_uri_claims.py` makes them."""

# (`uris.LABEL`: a URI that a part of a document names, found by the URI, and replaced by its head)
INDEXES = [
    {"kind": "label+property", "label": "PGUriClaim", "properties": ["uri"]},
    {"kind": "label+property", "label": "PGUriClaim", "properties": ["head_id"]},
]

CONSTRAINTS: list[dict] = []
