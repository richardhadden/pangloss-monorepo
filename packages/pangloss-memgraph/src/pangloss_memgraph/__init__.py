"""Pangloss on Memgraph. In a project's settings: `STORAGE = "pangloss_memgraph:storage"`"""

from pangloss_core.storage import Capabilities, Storage

storage = Storage(
    name="memgraph",
    package="pangloss_memgraph.databases.memgraph",
    capabilities=Capabilities(
        snapshots=True,
        fast_bulk_load=True,
        accent_folding=False,
        deep_search=True,
        cypher=True,
    ),
)
