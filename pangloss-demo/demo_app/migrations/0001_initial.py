"""0001_initial

Made by `pangloss makemigrations`; the answers a change needs may be filled in here.
"""

from pangloss_models.migrations.files import changes_from_data

dependencies = []
schema_hash = "621b9cba549634eeb287b41ee493496171a437548b6f5ea3ee36f74b99649bb8"

changes = changes_from_data(
    [
        {
            "change": "CreateEnum",
            "safety": "safe",
            "enum": "ActivityType",
            "definition": {
                "name": "ActivityType",
                "members": [
                    {"name": "BATTLE", "value": "battle"},
                    {"name": "CEREMONY", "value": "ceremony"},
                    {"name": "CORRESPONDENCE", "value": "correspondence"},
                    {"name": "JOURNEY", "value": "journey"},
                    {"name": "MEETING", "value": "meeting"},
                ],
            },
        },
        {
            "change": "CreateEnum",
            "safety": "safe",
            "enum": "Precision",
            "definition": {
                "name": "Precision",
                "members": [
                    {"name": "DAY", "value": "day"},
                    {"name": "DECADE", "value": "decade"},
                    {"name": "MONTH", "value": "month"},
                    {"name": "YEAR", "value": "year"},
                ],
            },
        },
        {
            "change": "CreateEnum",
            "safety": "safe",
            "enum": "Role",
            "definition": {
                "name": "Role",
                "members": [
                    {"name": "LEADER", "value": "leader"},
                    {"name": "MESSENGER", "value": "messenger"},
                    {"name": "PARTICIPANT", "value": "participant"},
                    {"name": "WITNESS", "value": "witness"},
                ],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Activity",
            "model_kind": "Document",
            "definition": {
                "name": "Activity",
                "kind": "Document",
                "abstract": False,
                "parent": "Statement",
                "typeParameters": [],
                "createWithId": False,
                "acceptUrlAsId": False,
                "requireLabel": True,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "activity_type",
                        "key": "activityType",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "enum", "enum": "ActivityType"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "carried_out_by",
                        "key": "carriedOutBy",
                        "nullable": False,
                        "kind": "relation",
                        "many": False,
                        "reverseName": "carried_out",
                        "options": [
                            {
                                "kind": "entity",
                                "type": "Group",
                                "edgeModel": "Certainty",
                            },
                            {
                                "kind": "entity",
                                "type": "Person",
                                "edgeModel": "Certainty",
                            },
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [
                                ["carried_out_by", "carried_out"],
                                ["involves", "involves_reverse"],
                            ],
                        },
                    },
                    {
                        "name": "date",
                        "key": "date",
                        "nullable": False,
                        "kind": "embedded",
                        "model": "Date",
                        "types": ["Date"],
                        "storage": {
                            "kind": "embedded_node",
                            "edges": [["date", "date_reverse"]],
                        },
                    },
                    {
                        "name": "participants",
                        "key": "participants",
                        "nullable": False,
                        "kind": "relation",
                        "many": True,
                        "reverseName": "participants_reverse",
                        "options": [
                            {
                                "kind": "reifiedRelation",
                                "type": "InRole",
                                "edgeModel": None,
                                "params": {
                                    "T": {
                                        "typeVar": "T",
                                        "options": [
                                            {
                                                "kind": "entity",
                                                "type": "Group",
                                                "edgeModel": None,
                                            },
                                            {
                                                "kind": "entity",
                                                "type": "Person",
                                                "edgeModel": None,
                                            },
                                        ],
                                    }
                                },
                            }
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [["participants", "participants_reverse"]],
                        },
                    },
                    {
                        "name": "places",
                        "key": "places",
                        "nullable": False,
                        "kind": "relation",
                        "many": True,
                        "reverseName": "places_reverse",
                        "options": [
                            {"kind": "entity", "type": "Place", "edgeModel": None}
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [["places", "places_reverse"]],
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
                        "name": "year",
                        "key": "year",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "int"},
                        "storage": {"kind": "property"},
                    },
                ],
                "labels": ["Activity", "Document", "Statement"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "AtPage",
            "model_kind": "ReifiedRelation",
            "definition": {
                "name": "AtPage",
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
                        "name": "page",
                        "key": "page",
                        "nullable": False,
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
                "labels": ["AtPage", "ReifiedRelation"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Causes",
            "model_kind": "Conjunction",
            "definition": {
                "name": "Causes",
                "kind": "Conjunction",
                "abstract": False,
                "parent": None,
                "typeParameters": ["TCause", "TResult"],
                "createWithId": False,
                "acceptUrlAsId": False,
                "requireLabel": False,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "cause",
                        "key": "cause",
                        "nullable": False,
                        "kind": "relation",
                        "many": False,
                        "reverseName": "cause_reverse",
                        "options": [
                            {"kind": "typeVar", "name": "TCause", "edgeModel": None}
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [["cause", "cause_reverse"]],
                        },
                    },
                    {
                        "name": "result",
                        "key": "result",
                        "nullable": False,
                        "kind": "relation",
                        "many": False,
                        "reverseName": "result_reverse",
                        "options": [
                            {"kind": "typeVar", "name": "TResult", "edgeModel": None}
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [["result", "result_reverse"]],
                        },
                    },
                ],
                "labels": ["Causes", "Conjunction"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Certainty",
            "model_kind": "EdgeModel",
            "definition": {
                "name": "Certainty",
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
                        "name": "level",
                        "key": "level",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "int"},
                        "storage": {"kind": "property"},
                    }
                ],
                "labels": ["Certainty", "EdgeModel"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Date",
            "model_kind": "Embedded",
            "definition": {
                "name": "Date",
                "kind": "Embedded",
                "abstract": False,
                "parent": None,
                "typeParameters": [],
                "createWithId": False,
                "acceptUrlAsId": False,
                "requireLabel": False,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "precision",
                        "key": "precision",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "enum", "enum": "Precision"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "when",
                        "key": "when",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "date"},
                        "storage": {"kind": "property"},
                    },
                ],
                "labels": ["Date", "Embedded"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Factoid",
            "model_kind": "Document",
            "definition": {
                "name": "Factoid",
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
                        "name": "source",
                        "key": "source",
                        "nullable": False,
                        "kind": "relation",
                        "many": False,
                        "reverseName": "source_reverse",
                        "options": [
                            {
                                "kind": "reifiedRelation",
                                "type": "AtPage",
                                "edgeModel": None,
                                "params": {
                                    "T": {
                                        "typeVar": "T",
                                        "options": [
                                            {
                                                "kind": "entity",
                                                "type": "Source",
                                                "edgeModel": None,
                                            }
                                        ],
                                    }
                                },
                            }
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [["source", "source_reverse"]],
                        },
                    },
                    {
                        "name": "statements",
                        "key": "statements",
                        "nullable": False,
                        "kind": "relation",
                        "many": True,
                        "reverseName": "statements_reverse",
                        "options": [
                            {
                                "kind": "conjunction",
                                "type": "Causes",
                                "edgeModel": None,
                                "params": {
                                    "TCause": {
                                        "typeVar": "TCause",
                                        "options": [
                                            {
                                                "kind": "document",
                                                "type": "Activity",
                                                "edgeModel": None,
                                            },
                                            {
                                                "kind": "document",
                                                "type": "Transfer",
                                                "edgeModel": None,
                                            },
                                        ],
                                    },
                                    "TResult": {
                                        "typeVar": "TResult",
                                        "options": [
                                            {
                                                "kind": "document",
                                                "type": "Activity",
                                                "edgeModel": None,
                                            },
                                            {
                                                "kind": "document",
                                                "type": "Transfer",
                                                "edgeModel": None,
                                            },
                                        ],
                                    },
                                },
                            },
                            {"kind": "document", "type": "Activity", "edgeModel": None},
                            {"kind": "document", "type": "Transfer", "edgeModel": None},
                            {
                                "kind": "semanticSpace",
                                "type": "Hypothetical",
                                "edgeModel": None,
                                "params": {
                                    "T": {
                                        "typeVar": "T",
                                        "options": [
                                            {
                                                "kind": "document",
                                                "type": "Activity",
                                                "edgeModel": None,
                                            },
                                            {
                                                "kind": "document",
                                                "type": "Transfer",
                                                "edgeModel": None,
                                            },
                                        ],
                                    }
                                },
                            },
                            {
                                "kind": "semanticSpace",
                                "type": "Negative",
                                "edgeModel": None,
                                "params": {
                                    "T": {
                                        "typeVar": "T",
                                        "options": [
                                            {
                                                "kind": "document",
                                                "type": "Activity",
                                                "edgeModel": None,
                                            },
                                            {
                                                "kind": "document",
                                                "type": "Transfer",
                                                "edgeModel": None,
                                            },
                                        ],
                                    }
                                },
                            },
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [["statements", "statements_reverse"]],
                        },
                    },
                    {
                        "name": "year",
                        "key": "year",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "int"},
                        "storage": {"kind": "property"},
                    },
                ],
                "labels": ["Document", "Factoid"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Group",
            "model_kind": "Entity",
            "definition": {
                "name": "Group",
                "kind": "Entity",
                "abstract": False,
                "parent": None,
                "typeParameters": [],
                "createWithId": False,
                "acceptUrlAsId": True,
                "requireLabel": True,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "name",
                        "key": "name",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    }
                ],
                "labels": ["Agent", "Entity", "Group"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Hypothetical",
            "model_kind": "SemanticSpace",
            "definition": {
                "name": "Hypothetical",
                "kind": "SemanticSpace",
                "abstract": False,
                "parent": None,
                "typeParameters": ["T"],
                "createWithId": False,
                "acceptUrlAsId": False,
                "requireLabel": False,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "contents",
                        "key": "contents",
                        "nullable": False,
                        "kind": "relation",
                        "many": True,
                        "reverseName": "contents_reverse",
                        "options": [
                            {"kind": "typeVar", "name": "T", "edgeModel": None}
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [["contents", "contents_reverse"]],
                        },
                    }
                ],
                "labels": ["Hypothetical", "SemanticSpace"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "InRole",
            "model_kind": "ReifiedRelation",
            "definition": {
                "name": "InRole",
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
                        "name": "role",
                        "key": "role",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "enum", "enum": "Role"},
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
                "labels": ["InRole", "ReifiedRelation"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Negative",
            "model_kind": "SemanticSpace",
            "definition": {
                "name": "Negative",
                "kind": "SemanticSpace",
                "abstract": False,
                "parent": None,
                "typeParameters": ["T"],
                "createWithId": False,
                "acceptUrlAsId": False,
                "requireLabel": False,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "contents",
                        "key": "contents",
                        "nullable": False,
                        "kind": "relation",
                        "many": True,
                        "reverseName": "contents_reverse",
                        "options": [
                            {"kind": "typeVar", "name": "T", "edgeModel": None}
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [["contents", "contents_reverse"]],
                        },
                    }
                ],
                "labels": ["Negative", "SemanticSpace"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Person",
            "model_kind": "Entity",
            "definition": {
                "name": "Person",
                "kind": "Entity",
                "abstract": False,
                "parent": None,
                "typeParameters": [],
                "createWithId": True,
                "acceptUrlAsId": True,
                "requireLabel": True,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "aliases",
                        "key": "aliases",
                        "nullable": False,
                        "kind": "list",
                        "item": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "born",
                        "key": "born",
                        "nullable": False,
                        "kind": "embedded",
                        "model": "Date",
                        "types": ["Date"],
                        "storage": {
                            "kind": "embedded_node",
                            "edges": [["born", "born_reverse"]],
                        },
                    },
                    {
                        "name": "known_as",
                        "key": "knownAs",
                        "nullable": False,
                        "kind": "annotatedValue",
                        "model": "WithCertainty",
                        "valueType": {"type": "str"},
                        "storage": {"kind": "map_property"},
                    },
                ],
                "labels": ["Agent", "Entity", "Person"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Place",
            "model_kind": "Entity",
            "definition": {
                "name": "Place",
                "kind": "Entity",
                "abstract": False,
                "parent": None,
                "typeParameters": [],
                "createWithId": False,
                "acceptUrlAsId": True,
                "requireLabel": True,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "coordinates",
                        "key": "coordinates",
                        "nullable": True,
                        "kind": "literal",
                        "type": {
                            "type": "typedDict",
                            "fields": {
                                "latitude": {"type": "float"},
                                "longitude": {"type": "float"},
                            },
                        },
                        "storage": {"kind": "property"},
                    }
                ],
                "labels": ["Entity", "Place"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Source",
            "model_kind": "Entity",
            "definition": {
                "name": "Source",
                "kind": "Entity",
                "abstract": False,
                "parent": None,
                "typeParameters": [],
                "createWithId": True,
                "acceptUrlAsId": True,
                "requireLabel": True,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "author",
                        "key": "author",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "edition_price",
                        "key": "editionPrice",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "decimal"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "written",
                        "key": "written",
                        "nullable": True,
                        "kind": "literal",
                        "type": {"type": "date"},
                        "storage": {"kind": "property"},
                    },
                ],
                "labels": ["Entity", "Source"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Statement",
            "model_kind": "Document",
            "definition": {
                "name": "Statement",
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
                        "name": "date",
                        "key": "date",
                        "nullable": False,
                        "kind": "embedded",
                        "model": "Date",
                        "types": ["Date"],
                        "storage": {
                            "kind": "embedded_node",
                            "edges": [["date", "date_reverse"]],
                        },
                    },
                    {
                        "name": "involves",
                        "key": "involves",
                        "nullable": False,
                        "kind": "relation",
                        "many": True,
                        "reverseName": "involves_reverse",
                        "options": [
                            {"kind": "entity", "type": "Group", "edgeModel": None},
                            {"kind": "entity", "type": "Person", "edgeModel": None},
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [["involves", "involves_reverse"]],
                        },
                    },
                    {
                        "name": "places",
                        "key": "places",
                        "nullable": False,
                        "kind": "relation",
                        "many": True,
                        "reverseName": "places_reverse",
                        "options": [
                            {"kind": "entity", "type": "Place", "edgeModel": None}
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [["places", "places_reverse"]],
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
                        "name": "year",
                        "key": "year",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "int"},
                        "storage": {"kind": "property"},
                    },
                ],
                "labels": ["Document", "Statement"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "Transfer",
            "model_kind": "Document",
            "definition": {
                "name": "Transfer",
                "kind": "Document",
                "abstract": False,
                "parent": "Statement",
                "typeParameters": [],
                "createWithId": False,
                "acceptUrlAsId": False,
                "requireLabel": True,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "date",
                        "key": "date",
                        "nullable": False,
                        "kind": "embedded",
                        "model": "Date",
                        "types": ["Date"],
                        "storage": {
                            "kind": "embedded_node",
                            "edges": [["date", "date_reverse"]],
                        },
                    },
                    {
                        "name": "given_by",
                        "key": "givenBy",
                        "nullable": False,
                        "kind": "relation",
                        "many": False,
                        "reverseName": "gave",
                        "options": [
                            {"kind": "entity", "type": "Group", "edgeModel": None},
                            {"kind": "entity", "type": "Person", "edgeModel": None},
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [
                                ["given_by", "gave"],
                                ["involves", "involves_reverse"],
                            ],
                        },
                    },
                    {
                        "name": "given_to",
                        "key": "givenTo",
                        "nullable": False,
                        "kind": "relation",
                        "many": False,
                        "reverseName": "received",
                        "options": [
                            {"kind": "entity", "type": "Group", "edgeModel": None},
                            {"kind": "entity", "type": "Person", "edgeModel": None},
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [["given_to", "received"]],
                        },
                    },
                    {
                        "name": "item",
                        "key": "item",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "str"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "places",
                        "key": "places",
                        "nullable": False,
                        "kind": "relation",
                        "many": True,
                        "reverseName": "places_reverse",
                        "options": [
                            {"kind": "entity", "type": "Place", "edgeModel": None}
                        ],
                        "storage": {
                            "kind": "edge",
                            "edges": [["places", "places_reverse"]],
                        },
                    },
                    {
                        "name": "quantity",
                        "key": "quantity",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "decimal"},
                        "storage": {"kind": "property"},
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
                        "name": "year",
                        "key": "year",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "int"},
                        "storage": {"kind": "property"},
                    },
                ],
                "labels": ["Document", "Statement", "Transfer"],
            },
        },
        {
            "change": "CreateModel",
            "safety": "safe",
            "model": "WithCertainty",
            "model_kind": "AnnotatedValue",
            "definition": {
                "name": "WithCertainty",
                "kind": "AnnotatedValue",
                "abstract": False,
                "parent": None,
                "typeParameters": ["T"],
                "createWithId": False,
                "acceptUrlAsId": False,
                "requireLabel": True,
                "useInSemanticSpaceLabel": True,
                "fields": [
                    {
                        "name": "certainty",
                        "key": "certainty",
                        "nullable": False,
                        "kind": "literal",
                        "type": {"type": "int"},
                        "storage": {"kind": "property"},
                    },
                    {
                        "name": "value",
                        "key": "value",
                        "nullable": False,
                        "kind": "typeVar",
                        "typeVar": "T",
                        "storage": {"kind": "property"},
                    },
                ],
                "labels": ["AnnotatedValue", "WithCertainty"],
            },
        },
    ]
)
