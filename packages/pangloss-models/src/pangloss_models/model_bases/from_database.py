"""Making what the database returns fit the models that read it"""

from typing import Any


def unwrap_single_item_lists(cls: Any, data: Any) -> Any:
    """Single relations and embedded objects come back from the database as lists of
    one: take the item out. (Anything but a dict is a model already: left as it is.)"""
    if not isinstance(data, dict):
        return data
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
