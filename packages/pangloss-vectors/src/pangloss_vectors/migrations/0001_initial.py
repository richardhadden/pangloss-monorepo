"""0001_initial

The structure of the vectors: the vectors of an item by its id (`PGVector`), and the state of each part
(`PGVectorState`). Written by hand (these nodes are not models).
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
                "label": "PGVectorState",
                "properties": ["part"],
            },
        },
    ]
)
