"""0005_addindex_createmodel_identificationbytoolchainfromtext_creat

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = "381478be3b13e8799938d55e65932941522cc181568f672fb5b90c2e262f0933"

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label",
                "label": "IdentificationByToolchainFromText",
                "properties": [],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "IdentificationByToolchainFromText",
            "model_kind": "ReifiedRelation",
            "definition": {
                "name": "IdentificationByToolchainFromText",
                "kind": "ReifiedRelation",
                "abstract": False,
                "parent": "IdentificationByToolchain",
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
                        "name": "text",
                        "key": "text",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
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
                "labels": ["IdentificationByToolchainFromText", "ReifiedRelation"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "IdentificationFromText",
            "model_kind": "ReifiedRelation",
            "definition": {
                "name": "IdentificationFromText",
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
                        "name": "text",
                        "key": "text",
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
                "labels": ["IdentificationFromText", "ReifiedRelation"],
            },
        },
    ]
)
