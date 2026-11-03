"""0001_initial

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations.files import changes_from_data

dependencies = []
schema_hash = "223654a9a06637b10e5dc956702f631297f409322f19383f903b6e055333254c"

changes = changes_from_data(
    [
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Likelihood",
            "model_kind": "EdgeModel",
            "definition": {
                "name": "Likelihood",
                "kind": "EdgeModel",
                "abstract": False,
                "parent": None,
                "typeParameters": [],
                "createWithId": False,
                "acceptUrlAsId": False,
                "requireLabel": True,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "percent",
                        "key": "percent",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "int"},
                        "storage": {"kind": "property"},
                    }
                ],
                "labels": ["EdgeModel", "Likelihood"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "WeightedAlternative",
            "model_kind": "Conjunction",
            "definition": {
                "name": "WeightedAlternative",
                "kind": "Conjunction",
                "abstract": False,
                "parent": None,
                "typeParameters": ["T"],
                "createWithId": False,
                "acceptUrlAsId": False,
                "requireLabel": False,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "alternatives",
                        "key": "alternatives",
                        "nullable": False,
                        "kind": "relation",
                        "many": True,
                        "reverseName": "alternatives_reverse",
                        "options": [
                            {"kind": "typeVar", "name": "T", "edgeModel": "Likelihood"}
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [["alternatives", "alternatives_reverse"]],
                        },
                    }
                ],
                "labels": ["Conjunction", "WeightedAlternative"],
            },
        },
    ]
)
