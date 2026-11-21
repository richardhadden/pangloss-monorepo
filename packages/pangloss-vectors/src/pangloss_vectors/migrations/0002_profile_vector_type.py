"""0002_profile_vector_type

The vectors of each profile by the class of their item (`PGProfileVector(type)`): the exact scan of the classes a
search is narrowed to that no group covers (`search.scan_query`, step 7a.4 of implementation_docs/similarity-build-plan.md)
finds them by it. Written by hand (these nodes are not models).
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
                "label": "PGProfileVector",
                "properties": ["type"],
            },
        },
    ]
)
