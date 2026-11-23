"""0003_suggested

The structure of what the worker that suggests keeps (`structure.py`; step 10.5d): `PGReconcileSuggested`, what it
saw when it wrote a suggestion, unique by the suggestion's `id` and indexed by it; `PGReconcileTried`, a stand-in it
left, unique by `stand_in` and indexed by it (Memgraph's unique constraints make no index). Written by hand (these
nodes are not models).
"""

from pangloss_models.migrations import changes_from_data

dependencies = [["pangloss_reconcile", "0002_models"]]

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGReconcileSuggested",
                "properties": ["id"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGReconcileTried",
                "properties": ["stand_in"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "PGReconcileSuggested",
                "properties": ["id"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "PGReconcileTried",
                "properties": ["stand_in"],
            },
        },
    ]
)
