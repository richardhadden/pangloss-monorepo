"""0001_initial

The structure of reconciliation's own nodes (`structure.py`): what the stored route offered (`PGReconcileShown`,
unique by stand-in and user, found by its stand-in) and what was chosen of it (`PGReconcileExample`, unique by
stand-in, and indexed by it). Written by hand (these nodes are not models).
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
                "label": "PGReconcileShown",
                "properties": ["stand_in"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGReconcileExample",
                "properties": ["stand_in"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "PGReconcileShown",
                "properties": ["stand_in", "user"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "PGReconcileExample",
                "properties": ["stand_in"],
            },
        },
    ]
)
