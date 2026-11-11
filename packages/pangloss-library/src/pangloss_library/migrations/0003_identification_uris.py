"""0003_identification_uris

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = "95600ed6745e739725b82a6cdfe88d089e096676b2da3e660e6862191f5afc19"

changes = changes_from_data(
    [
        {
            "change": "AddField",
            "safety": "additive",
            "model": "Identification",
            "name": "uris",
            "field_kind": "list",
            "needs_value": True,
            "definition": {
                "name": "uris",
                "key": "uris",
                "nullable": False,
                "kind": "list",
                "item": {"type": "str", "format": "url"},
                "storage": {"kind": "property"},
            },
            "default": [],
            "from_narrowing": False,
        }
    ]
)
