"""0003_addindex

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations.files import changes_from_data

dependencies = []
schema_hash = "6527a718568bc42508cf9453a920ae68aef510ebde4554d6444c17e16f87077c"

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGIndexableNode",
                "properties": ["head_node_id"],
            },
        }
    ]
)
