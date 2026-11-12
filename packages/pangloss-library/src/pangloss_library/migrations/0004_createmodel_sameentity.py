"""0004_createmodel_sameentity

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = "a1423c18de239a442a1ff27b7c3ec1ab5700a6047f2fbfd9e983843b2e254e37"

changes = changes_from_data(
    [
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "SameEntity",
            "model_kind": "ReifiedRelationDocument",
            "definition": {
                "name": "SameEntity",
                "kind": "ReifiedRelationDocument",
                "abstract": False,
                "parent": None,
                "typeParameters": ["T"],
                "createWithId": False,
                "acceptUrlAsId": False,
                "requireLabel": True,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "argument",
                        "key": "argument",
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
                "labels": ["ReifiedRelationDocument", "SameEntity"],
            },
        }
    ]
)
