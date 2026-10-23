"""The shape of the models, to compare what a client has with what the server has"""

import hashlib
import json
from typing import Any

from pangloss_models.model_registry import ModelRegistry


def canonical(value: Any) -> Any:
    """A schema with the members of its unions and its required fields in a fixed order: the
    order of the members of a union differs from one process to the next (it comes from a
    set), and means nothing for what is accepted"""
    if isinstance(value, dict):
        return {
            key: sorted((canonical(v) for v in item), key=lambda v: json.dumps(v, sort_keys=True, default=str))
            if key in ("anyOf", "oneOf", "required") and isinstance(item, list)
            else canonical(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [canonical(v) for v in value]
    return value


def head_model_schemas(module_names: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """The JSON schema of the generated models of each registered Document and Entity (of
    the given modules, if any): to compare what a client makes with what the server has"""
    out: dict[str, dict[str, Any]] = {}
    for model in ModelRegistry._models:
        if getattr(model, "__metatype__", None) not in ("Document", "Entity"):
            continue
        if module_names is not None and model.__module__ not in module_names:
            continue
        schemas: dict[str, Any] = {}
        for kind in ("Create", "Update", "HeadView", "EditView", "ReferenceView", "ReferenceSet"):
            cls = getattr(model, kind, None)
            if cls is None or "<locals>" in model.__qualname__:
                continue
            try:
                schemas[kind] = canonical(cls.model_json_schema(by_alias=True))
            except Exception as error:  # (the same on both sides, or a difference)
                schemas[kind] = f"error: {type(error).__name__}"
        out[model.__name__] = schemas
    return out


def schema_hash(position: dict[str, str]) -> str:
    """A short hash of where the migrations are (`{app: last migration}`): what a client
    and a server compare to know whether they have the same schema"""
    canonical_text = json.dumps(position, sort_keys=True)
    return hashlib.sha256(canonical_text.encode()).hexdigest()[:16]
