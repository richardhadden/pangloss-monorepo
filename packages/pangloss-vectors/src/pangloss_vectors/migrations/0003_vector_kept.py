"""0003_vector_kept

What a part keeps with a generation of its vectors (`PGVectorKept(part)`): text its rebuild worked out over every item
that its refresh and overlay need, such as the name part's table of rarity (`store.keep`, `store.kept`; step 8.3 of
implementation_docs/similarity-build-plan.md). Found by its part: without an index Memgraph would scan every node for
the label. Written by hand (these nodes are not models).
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
                "label": "PGVectorKept",
                "properties": ["part"],
            },
        },
    ]
)
