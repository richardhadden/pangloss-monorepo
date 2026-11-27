"""0002_models

The structure of the fits of people's judgements (`structure.py`; step 6.6): `PGCompareModel`, unique by its `id`,
and indexed by it (Memgraph's unique constraints make no index). Written by hand (these nodes are not models), as
`pangloss_reconcile`'s `0002_models`.
"""

from pangloss_models.migrations import changes_from_data

dependencies = [["pangloss_compare", "0001_initial"]]

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGCompareModel",
                "properties": ["id"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "PGCompareModel",
                "properties": ["id"],
            },
        },
    ]
)
