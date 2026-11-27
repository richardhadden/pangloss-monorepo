"""0001_initial

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = "6aadac79338638b9231c68c262393f7cadfc6773d396608077b4c4278d0979ad"

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {"kind": "label", "label": "EventJudgement", "properties": []},
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "EventJudgement",
            "model_kind": "Document",
            "definition": {
                "name": "EventJudgement",
                "kind": "Document",
                "abstract": True,
                "parent": None,
                "typeParameters": [],
                "createWithId": False,
                "acceptUrlAsId": False,
                "requireLabel": True,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "fields",
                        "key": "fields",
                        "nullable": False,
                        "kind": "list",
                        "item": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "note",
                        "key": "note",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "verdict",
                        "key": "verdict",
                        "nullable": False,
                        "kind": "literal",
                        "type": {
                            "type": "literal",
                            "values": [
                                "agree",
                                "disagree",
                                "two_events",
                                "carried_out",
                                "carried_out_otherwise",
                                "not_carried_out",
                                "breach",
                            ],
                        },
                        "storage": {"kind": "property"},
                    },
                ],
                "labels": ["Document", "EventJudgement"],
            },
        },
    ]
)
