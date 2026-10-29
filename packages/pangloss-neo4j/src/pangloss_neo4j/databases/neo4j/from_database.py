"""What the Neo4j driver returns that the models do not know: its date and time types.

Registered with the models (`pangloss_models.hooks.from_database`) when this package is
imported, which is when the database module is bound.
"""

from typing import Any

import neo4j.time
from pangloss_models import hooks

NEO4J_TIME_TYPES = (neo4j.time.DateTime, neo4j.time.Date, neo4j.time.Time)


def convert_neo4j_datetimes(data: Any) -> Any:
    """Recursively convert neo4j date and time objects in the data to native ones"""
    if isinstance(data, dict):
        return {k: convert_neo4j_datetimes(v) for k, v in data.items()}
    if isinstance(data, list):
        return [convert_neo4j_datetimes(v) for v in data]
    if isinstance(data, NEO4J_TIME_TYPES):
        return data.to_native()
    return data


if convert_neo4j_datetimes not in hooks.from_database:
    hooks.from_database.append(convert_neo4j_datetimes)
