"""0004_shared_descriptions

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = "e73cd3a4aab1be89d409199b9aa39457beeb46eea7fd34a1398813c342b76940"

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {"kind": "label", "label": "Description", "properties": []},
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {"kind": "label", "label": "PGCitation", "properties": []},
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGCitation",
                "properties": ["target_head_id"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGCitation",
                "properties": ["target_id"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Description",
            "model_kind": "Document",
            "definition": {
                "name": "Description",
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
                        "name": "criteria",
                        "key": "criteria",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "str", "format": "search-pattern"},
                        "storage": {"kind": "property"},
                    }
                ],
                "labels": ["Description", "Document"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "PGCitation",
            "model_kind": "Document",
            "definition": {
                "name": "PGCitation",
                "kind": "Document",
                "abstract": False,
                "parent": None,
                "typeParameters": [],
                "createWithId": False,
                "acceptUrlAsId": False,
                "requireLabel": False,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "changed_since_cited",
                        "key": "changedSinceCited",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "bool"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "cited_hash",
                        "key": "citedHash",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "cited_label",
                        "key": "citedLabel",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "cited_version",
                        "key": "citedVersion",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "int"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "target_head_id",
                        "key": "targetHeadId",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str", "format": "uuid"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "target_head_label",
                        "key": "targetHeadLabel",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "target_head_type",
                        "key": "targetHeadType",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "target_id",
                        "key": "targetId",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "str", "format": "uuid"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "target_label",
                        "key": "targetLabel",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "target_spaces",
                        "key": "targetSpaces",
                        "nullable": False,
                        "kind": "list",
                        "item": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "target_state",
                        "key": "targetState",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "target_type",
                        "key": "targetType",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                ],
                "labels": ["Document", "PGCitation"],
            },
        },
        {
            "change": "AddField",
            "safety": "safe",
            "model": "MatchesCriteria",
            "name": "description",
            "field_kind": "relation",
            "needs_value": False,
            "definition": {
                "name": "description",
                "key": "description",
                "nullable": True,
                "kind": "relation",
                "many": False,
                "reverseName": "description_reverse",
                "options": [
                    {"kind": "document", "type": "PGCitation", "edgeModel": None}
                ],
                "storage": {
                    "kind": "edge",
                    "edges": [["description", "description_reverse"]],
                },
            },
            "default": None,
            "from_narrowing": False,
        },
        {
            "change": "AddField",
            "safety": "additive",
            "model": "MatchesCriteria",
            "name": "stands_for",
            "field_kind": "list",
            "needs_value": True,
            "definition": {
                "name": "stands_for",
                "key": "standsFor",
                "nullable": False,
                "kind": "list",
                "item": {"type": "str"},
                "storage": {"kind": "property"},
            },
            "default": [],
            "from_narrowing": False,
        },
    ]
)
