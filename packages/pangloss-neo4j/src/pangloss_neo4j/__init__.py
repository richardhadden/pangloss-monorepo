"""Pangloss on Neo4j. In a project's settings: `STORAGE = "pangloss_neo4j:storage"`"""

from pangloss_core.storage import Capabilities, Storage

storage = Storage(
    name="neo4j",
    package="pangloss_neo4j.databases.neo4j",
    capabilities=Capabilities(
        snapshots=False,
        fast_bulk_load=False,
        accent_folding=True,
        deep_search=True,
        cypher=True,
    ),
)
