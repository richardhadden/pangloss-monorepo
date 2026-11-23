"""0002_models

The structure of the fits of reconciliation's decisions (`structure.py`; step 11.5): `PGReconcileModel`, unique by
its `id`, and indexed by it (Memgraph's unique constraints make no index). Written by hand (these nodes are not
models).
"""

from pangloss_models.migrations import changes_from_data

dependencies = [["pangloss_reconcile", "0001_initial"]]

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGReconcileModel",
                "properties": ["id"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "PGReconcileModel",
                "properties": ["id"],
            },
        },
    ]
)
