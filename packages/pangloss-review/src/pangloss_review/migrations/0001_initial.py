"""0001_initial

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = "2c3a165fb814f5e94e83746a907e29484f48269df37fdef12986f785fcfc6d15"

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {"kind": "label", "label": "Unreconciled", "properties": []},
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "Unreconciled",
                "properties": ["label_key"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Unreconciled",
            "model_kind": "Document",
            "definition": {
                "name": "Unreconciled",
                "kind": "Document",
                "abstract": False,
                "parent": None,
                "typeParameters": [],
                "createWithId": False,
                "acceptUrlAsId": False,
                "requireLabel": True,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "label_key",
                        "key": "labelKey",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "unreconciled_type",
                        "key": "unreconciledType",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "uris",
                        "key": "uris",
                        "nullable": False,
                        "kind": "list",
                        "item": {"type": "str", "format": "url"},
                        "storage": {"kind": "property"},
                    },
                ],
                "labels": ["Document", "Unreconciled"],
            },
        },
    ]
)
