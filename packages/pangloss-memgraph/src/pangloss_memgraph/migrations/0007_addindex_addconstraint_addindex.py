"""0007_addindex_addconstraint_addindex

The work a write leaves pending for an installed app (`pangloss_cypher.pending`): one `PGPending` node for each kind of
work and head node, unique by its key; and a label index, as a worker claims them by label.
"""

from pangloss_models.migrations.files import changes_from_data

dependencies = []

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGPending",
                "properties": ["key"],
            },
        },
        {
            "change": "AddConstraint",
            "safety": "additive",
            "constraint": {
                "kind": "unique",
                "label": "PGPending",
                "properties": ["key"],
            },
        },
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {"kind": "label", "label": "PGPending", "properties": []},
        },
    ]
)
