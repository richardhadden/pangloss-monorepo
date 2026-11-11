"""0003_uri_claims

Written by hand (2026-11-11): the URIs that parts of documents name (an unreconciled mention, an identification a
toolchain suggested) are found by nodes of their own, `PGUriClaim` (`pangloss_review.uris`): their two indexes, and
the claims of the parts there are. (Of the library's `IdentificationByToolchain` and of `Unreconciled`; a project
with its own subclasses of the first runs `pangloss review index-uris` once.) The models do not change.
"""

from pangloss_models.migrations import changes as c
from pangloss_models.migrations import changes_from_data

dependencies = []
schema_hash = "2c3a165fb814f5e94e83746a907e29484f48269df37fdef12986f785fcfc6d15"

MAKE = """
MATCH (part:{label})
WHERE size(coalesce(part.uris, [])) > 0
UNWIND part.uris AS uri
CREATE (:PGUriClaim {{uri: uri, part_id: part.id, head_id: part.head_node_id, kind: '{kind}'}})
"""

changes = changes_from_data(
    [
        {
            "change": "AddIndex",
            "safety": "safe",
            "index": {
                "kind": "label+property",
                "label": "PGUriClaim",
                "properties": [name],
            },
        }
        for name in ("uri", "head_id")
    ]
    + [
        c.RunCypher(
            query=MAKE.format(label=label, kind=kind),
            reverse_query=f"MATCH (claim:PGUriClaim {{kind: '{kind}'}}) DELETE claim",
            dialect=dialect,
            affects=[],
            note=f"the URIs that each {label} names, to be found by",
        )
        for label, kind in (
            ("Unreconciled", "mention"),
            ("IdentificationByToolchain", "suggestion"),
        )
        for dialect in ("memgraph", "neo4j")
    ]
)
