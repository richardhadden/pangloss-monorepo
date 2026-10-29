"""0002_addindex_createmodel_datecharacterisation_createmodel_norule

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations.files import changes_from_data

dependencies = [["pangloss_dates", "0001_initial"]]
schema_hash = "e1842fb1d98de2605d04a1fa3a0cedd1baa0d1f7288fe905ab1852ccb63272a6"

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label",
                "label": "DateCharacterisation",
                "properties": [],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "DateCharacterisation",
            "model_kind": "Entity",
            "definition": {
                "name": "DateCharacterisation",
                "kind": "Entity",
                "abstract": True,
                "parent": None,
                "typeParameters": [],
                "createWithId": False,
                "acceptUrlAsId": True,
                "requireLabel": True,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "rank",
                        "key": "rank",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "use",
                        "key": "use",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "when",
                        "key": "when",
                        "nullable": False,
                        "kind": "embedded",
                        "model": None,
                        "types": ["NoRule", "Recurrence"],
                        "storage": {
                            "kind": "embedded_node",
                            "edges": [["when", "when_reverse"]],
                        },
                    },
                ],
                "labels": ["DateCharacterisation", "Entity"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "NoRule",
            "model_kind": "Embedded",
            "definition": {
                "name": "NoRule",
                "kind": "Embedded",
                "abstract": False,
                "parent": None,
                "typeParameters": [],
                "createWithId": False,
                "acceptUrlAsId": False,
                "requireLabel": False,
                "useInSemanticSpaceLabel": True,
                "fields": [],
                "labels": ["Embedded", "NoRule"],
            },
        },
    ]
)
