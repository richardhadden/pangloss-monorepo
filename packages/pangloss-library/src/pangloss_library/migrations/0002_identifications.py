"""0002_identifications: `Identification` and `IdentificationByToolchain`

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
            "index": {
                "kind": "label",
                "label": "IdentificationByToolchain",
                "properties": [],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Identification",
            "model_kind": "ReifiedRelation",
            "definition": {
                "name": "Identification",
                "kind": "ReifiedRelation",
                "abstract": False,
                "parent": None,
                "typeParameters": ["T"],
                "createWithId": False,
                "acceptUrlAsId": False,
                "requireLabel": False,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "identified_by",
                        "key": "identifiedBy",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "target",
                        "key": "target",
                        "nullable": False,
                        "kind": "relation",
                        "many": True,
                        "reverseName": "target_reverse",
                        "options": [
                            {"kind": "typeVar", "name": "T", "edgeModel": None}
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [["target", "target_reverse"]],
                        },
                    },
                ],
                "labels": ["Identification", "ReifiedRelation"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "IdentificationByToolchain",
            "model_kind": "ReifiedRelation",
            "definition": {
                "name": "IdentificationByToolchain",
                "kind": "ReifiedRelation",
                "abstract": False,
                "parent": "Identification",
                "typeParameters": ["T"],
                "createWithId": False,
                "acceptUrlAsId": False,
                "requireLabel": False,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "identified_by",
                        "key": "identifiedBy",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "target",
                        "key": "target",
                        "nullable": False,
                        "kind": "relation",
                        "many": True,
                        "reverseName": "target_reverse",
                        "options": [
                            {"kind": "typeVar", "name": "T", "edgeModel": None}
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [["target", "target_reverse"]],
                        },
                    },
                    {
                        "name": "toolchain_version",
                        "key": "toolchainVersion",
                        "nullable": True,
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
                "labels": ["IdentificationByToolchain", "ReifiedRelation"],
            },
        },
    ]
)
