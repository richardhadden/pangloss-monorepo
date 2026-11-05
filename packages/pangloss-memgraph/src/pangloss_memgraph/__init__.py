"""Pangloss on Memgraph. In a project's settings: `STORAGE = "pangloss_memgraph:storage"`"""

from pangloss_core import Capabilities, Storage

lazy from pangloss_memgraph.databases.memgraph.settings import MemgraphDatabaseSettings

__all__ = ["MemgraphDatabaseSettings", "storage"]

storage = Storage(
    name="memgraph",
    package="pangloss_memgraph.databases.memgraph",
    capabilities=Capabilities(
        snapshots=True,
        fast_bulk_load=True,
        accent_folding=True,
        deep_search=True,
        cypher=True,
    ),
)
