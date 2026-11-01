"""0006_removeindex_runpython_addindex

Accents are folded in searches (`zurich` finds "Zürich"): the text index moves from `label` to `label_folded`, the label
folded (`pangloss_models.text.fold`), which every node with a label is given here, and which the models write from now
on. (Memgraph's text index does not fold accents itself.)
"""

from pangloss_models.migrations.files import changes_from_data

dependencies = []
schema_hash = "80377d12ab28edd5acfc62d2f62023652f0d842fc6ca1befc25b2b341c62894d"

changes = changes_from_data(
    [
        {
            "change": "RemoveIndex",
            "safety": "safe",
            "index": {
                "kind": "text",
                "label": "PGIndexableNode",
                "properties": ["label"],
                "name": "label_text",
            },
        },
        {
            "change": "RunPython",
            "safety": "transforming",
            "function": "pangloss_memgraph.databases.memgraph.folding:refold_in_migration",
            "affects": [],
            "note": "the folded label of every node that has a label",
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "text",
                "label": "PGIndexableNode",
                "properties": ["label_folded"],
                "name": "label_text",
            },
        },
    ]
)
