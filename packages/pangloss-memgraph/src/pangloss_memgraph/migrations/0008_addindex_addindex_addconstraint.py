"""0008_addindex_addindex_addconstraint

A merge of two entities (`pangloss_cypher.merge`, implementation_docs/entity-identity.md): a `PGMerge` node for each, unique by its id and
found by the entity that survived and the one absorbed; and a `PGMergeMove` for each reference it moved, found by its
merge.
"""

from pangloss_models.migrations import changes_from_data

dependencies = []

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGMerge",
                "properties": ["id"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGMerge",
                "properties": ["survivor"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGMerge",
                "properties": ["absorbed"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGMergeMove",
                "properties": ["pg_merge"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "PGMerge",
                "properties": ["id"],
            },
        },
    ]
)
