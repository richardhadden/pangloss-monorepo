"""0004_addindex_addconstraint

The lock node of `lock(tx, key)` (see `pangloss_core.backend`): one node for each key, unique.
"""

from pangloss_models.migrations.files import changes_from_data

dependencies = []
schema_hash = "f5220b196fcc189e10a5ade51085da4b1123a0ee2f4f7aacd652b804e29095d7"

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGLock",
                "properties": ["key"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "PGLock",
                "properties": ["key"],
            },
        },
    ]
)
