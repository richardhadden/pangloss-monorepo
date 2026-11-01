"""Applying migrations to a Neo4j database: `pangloss_cypher.migrations`, with what is Neo4j's in its dialect
(`migration_dialect`: how a map is stored, the indexes and constraints)."""

from pangloss_cypher.migrations import *  # noqa: F403
from pangloss_cypher.migrations import __all__ as __all__
