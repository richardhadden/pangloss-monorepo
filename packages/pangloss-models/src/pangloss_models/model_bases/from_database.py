"""Making what the database returns fit the models that read it"""

from typing import Any

import neo4j


def unwrap_single_item_lists(cls: Any, data: Any) -> Any:
    """Single relations and embedded objects come back from the database as lists of
    one: take the item out"""
    for k, v in data.items():
        if not isinstance(v, list):
            continue
        if k in cls._meta.fields.relation_fields:
            if cls._meta.fields.relation_fields[k].wrapper is not None:
                continue
        elif k not in cls._meta.fields.embedded_fields:
            continue
        if len(v) > 1:
            raise ValueError(
                f"{cls.__name__}.{k}: More than one value returned for field"
            )
        data[k] = v[0]
    return data


def convert_neo4j_datetimes(data: Any) -> Any:
    """Recursively convert neo4j DateTime objects in a dict."""
    if isinstance(data, dict):
        return {k: convert_neo4j_datetimes(v) for k, v in data.items()}
    if isinstance(data, list):
        return [convert_neo4j_datetimes(v) for v in data]
    if isinstance(data, (neo4j.time.DateTime, neo4j.time.Date, neo4j.time.Time)):
        return data.to_native()
    return data
