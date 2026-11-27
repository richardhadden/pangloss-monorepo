"""What the app adds to the server (implementation_docs/compare.md, "The route"):

    GET /api/compare/{type}/{ref}
        the comparison of the statement `ref` (its id) of the class `type` (its own or one above it) with the
        statements it is paired with, as the reader may see them (`compare.compare`, `Comparison.as_json`):
        `{statement, pairs, more, model}`, each pair with what is worked out of the two (and what a person's newest
        judgement overrides of it), how it was found, and every judgement of it, newest first. A 404, the same for
        each, where there is none: no class `type`, an id that is not there or not of `type`, a class that is not
        compared, a statement the reader may not see. An id that is not one is a 422, as at `GET /api/NAME/{id}`.
        Anyone may read it; what the reader may see is as at `GET /api/NAME/{id}`. It writes nothing.

A judgement is written by the ordinary `POST /api/NAME` of the project's class below `EventJudgement` (logged in, as
every write)."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/api/compare", tags=["compare"])


def none_for(name: str, ref: UUID) -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND,
        detail=f"There is no comparison of a {name} with id {ref}",
    )


def _asked_class(name: str) -> type | None:
    """A class of documents (or a trait) by its name, or None"""
    from pangloss_models import Entity, ModelRegistry

    model = ModelRegistry._model_dict.get(name)
    if (
        not name.isidentifier()
        or not isinstance(model, type)
        or issubclass(model, Entity)
    ):
        return None
    return model


@router.get("/{model_name}/{ref}", operation_id="compare_statement")
async def compare_statement(model_name: str, ref: UUID) -> dict[str, Any]:
    """A statement compared with the statements it is paired with: how each stands to it, and what people said"""
    from pangloss_core import backend
    from pangloss_models import ModelRegistry

    from pangloss_compare.compare import compare

    asked = _asked_class(model_name)
    if asked is None:
        raise none_for(model_name, ref)
    found = await compare(ref, backend.current().unpublished_visible())
    own = None if found is None else ModelRegistry._model_dict.get(found.statement.type)
    if found is None or not isinstance(own, type) or not issubclass(own, asked):
        raise none_for(model_name, ref)
    return found.as_json()
