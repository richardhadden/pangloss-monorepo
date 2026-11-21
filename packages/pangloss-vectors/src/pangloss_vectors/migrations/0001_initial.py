"""0001_initial

The structure of the vectors: the vectors of a part of an item, by its id and by generation (`PGVector`); the state of
each part (`PGVectorState`); the vectors of each profile (`PGProfileVector`), as those of a part; and the state of each
profile (`PGVectorProfile`). Written by hand (these nodes are not models). The vector indexes are not here: they follow
the project's models, and are in the project's migrations (`structure.indexes`).
"""

from pangloss_models.migrations import changes_from_data

dependencies = []

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGVector",
                "properties": ["of"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGVector",
                "properties": ["generation"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGVectorState",
                "properties": ["part"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGProfileVector",
                "properties": ["of"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGProfileVector",
                "properties": ["generation"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGVectorProfile",
                "properties": ["profile"],
            },
        },
    ]
)
