"""0001_initial

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = "4e7829561eff44069c20c9feb711447572a581031bd96e20df10e996f679f2cd"

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {"kind": "label", "label": "MatchesCriteria", "properties": []},
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "MatchesCriteria",
            "model_kind": "ReifiedRelation",
            "definition": {
                "name": "MatchesCriteria",
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
                        "name": "anchors",
                        "key": "anchors",
                        "nullable": False,
                        "kind": "list",
                        "item": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "broken",
                        "key": "broken",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "candidate_count",
                        "key": "candidateCount",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "int"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "candidate_count_everyone",
                        "key": "candidateCountEveryone",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "int"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "criteria",
                        "key": "criteria",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str", "format": "search-pattern"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "criteria_hash",
                        "key": "criteriaHash",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "depends_on",
                        "key": "dependsOn",
                        "nullable": False,
                        "kind": "list",
                        "item": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "evaluated_when",
                        "key": "evaluatedWhen",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "datetime"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "names",
                        "key": "names",
                        "nullable": False,
                        "kind": "list",
                        "item": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "reach",
                        "key": "reach",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "shape",
                        "key": "shape",
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
                        "name": "wording",
                        "key": "wording",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                ],
                "labels": ["MatchesCriteria", "ReifiedRelation"],
            },
        },
    ]
)
