"""0002_documents

Derived documents: a justification of a rule that derives documents keeps the id of its document (`document_id`),
and the worker finds the justification of a document by it. Written by hand (these nodes are not models).
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
                "label": "PGJustification",
                "properties": ["document_id"],
            },
        },
    ]
)
