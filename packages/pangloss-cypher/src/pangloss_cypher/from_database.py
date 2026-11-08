"""What the driver (Memgraph's or Neo4j's) returns that the models do not know: its date and time types,
and its duration.

Registered with the models (`pangloss_models.hooks.from_database`) when this package is
imported, which is when the database module is bound.
"""

import datetime
from typing import Any

import neo4j.time
from pangloss_models import hooks

NEO4J_TIME_TYPES = (neo4j.time.DateTime, neo4j.time.Date, neo4j.time.Time)

# (a `timedelta` is written as a duration of days, seconds and nanoseconds; a duration with months was written
# by something else, and a month is taken as thirty days, as Cypher does when it adds one to a date)
DAYS_IN_A_MONTH = 30


def native_duration(value: neo4j.time.Duration) -> datetime.timedelta:
    return datetime.timedelta(
        days=value.months * DAYS_IN_A_MONTH + value.days,
        seconds=value.seconds,
        microseconds=value.nanoseconds // 1000,
    )


def convert_neo4j_datetimes(data: Any) -> Any:
    """Recursively convert neo4j date, time and duration objects in the data to native ones"""
    if isinstance(data, dict):
        return {k: convert_neo4j_datetimes(v) for k, v in data.items()}
    if isinstance(data, list):
        return [convert_neo4j_datetimes(v) for v in data]
    if isinstance(data, NEO4J_TIME_TYPES):
        return data.to_native()
    if isinstance(data, neo4j.time.Duration):
        return native_duration(data)
    return data


if convert_neo4j_datetimes not in hooks.from_database:
    hooks.from_database.append(convert_neo4j_datetimes)
