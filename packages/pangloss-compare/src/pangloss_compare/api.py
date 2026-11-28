"""What the app adds to the server (implementation_docs/compare.md, "The route"):

    GET /api/compare/{type}/{ref}
        the comparison of the statement `ref` (its id) of the class `type` (its own or one above it) with the
        statements it is paired with, as the reader may see them (`compare.compare`, `Comparison.as_json`):
        `{statement, pairs, more, model}`, each pair with what is worked out of the two (and what a person's newest
        judgement overrides of it), how it was found, and every judgement of it, newest first. A 404, the same for
        each, where there is none: no class `type`, an id that is not there or not of `type`, a class that is not
        compared, a statement the reader may not see. An id that is not one is a 422, as at `GET /api/NAME/{id}`.
        Anyone may read it; what the reader may see is as at `GET /api/NAME/{id}`. It writes nothing. `near` is null.

    GET /api/compare/{type}/{ref}?near=true
        the same, but `pairs` holds only the pairs through near entities (`compare.compare_near`, step 6.4), each
        `found: "near"` and its reasons the field, the entity the statement names, the entity near it and the score;
        `near` is `{profile, k, floor, state}` (`state`: `ok`, `pending`, `rebuild_due`, or `none` where there is no
        profile or `pangloss-vectors` is not installed). Asked apart, since each search costs far more than the pairs
        by rule. The same 404s.

    GET /api/compare/{type}/{ref}?other=ID
        the same, but `pairs` holds only the entry of `ref` with the statement `ID` (`compare.compare_pair`, step
        7.5), whether or not the rule or the near entities find it and whatever the cut: what the maths says of the two
        as they are (`found: "asked"`, no reasons) and every judgement of the pair; none where `ID` is not a statement
        the reader may see of a compared class. For the page of two side by side. The same 404s; not with `near`.

A judgement is written by the ordinary `POST /api/NAME` of the project's class below `EventJudgement` (logged in, as
every write)."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

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


def _ids(text: str, most: int) -> list[UUID]:
    """The ids of `?others=`, separated by commas: a 422 where there is none, one is not a UUID, or there are more
    than `most`"""
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        raise HTTPException(422, detail="Name at least one other statement")
    if len(parts) > most:
        raise HTTPException(
            422, detail=f"Ask for at most {most} other statements at once"
        )
    try:
        return [UUID(part) for part in parts]
    except ValueError:
        raise HTTPException(
            422, detail="Each other statement is named by its id (a UUID)"
        ) from None


@router.get("/{model_name}/{ref}", operation_id="compare_statement")
async def compare_statement(
    model_name: str,
    ref: UUID,
    near: Annotated[
        bool,
        Query(
            description="Only the pairs through near entities: statements naming an entity near one this statement "
            "names, each pair one event only if the two entities are one"
        ),
    ] = False,
    other: Annotated[
        UUID | None,
        Query(
            description="Only the pair of this statement with the statement of this id, found or not (with what "
            "the maths says of the two, and every judgement of them)"
        ),
    ] = None,
    others: Annotated[
        str | None,
        Query(
            description="Only the pairs of this statement with each of these statements (ids, separated by commas; "
            "at most 50), found or not"
        ),
    ] = None,
) -> dict[str, Any]:
    """A statement compared with the statements it is paired with: how each stands to it, and what people said"""
    from pangloss_core import backend
    from pangloss_models import ModelRegistry

    from pangloss_compare.compare import (
        MOST_OTHERS,
        compare,
        compare_near,
        compare_pair,
        compare_pairs,
    )

    asked = _asked_class(model_name)
    if asked is None:
        raise none_for(model_name, ref)
    if near and other is not None:
        raise HTTPException(
            422,
            detail="Ask for the pairs through near entities or for one other statement, not both",
        )
    if others is not None and (near or other is not None):
        raise HTTPException(
            422,
            detail="Ask for several other statements alone, not with one other or the pairs through near entities",
        )
    asked_others = None if others is None else _ids(others, MOST_OTHERS)
    visible = backend.current().unpublished_visible()
    if asked_others is not None:
        found = await compare_pairs(ref, asked_others, visible)
    elif other is not None:
        found = await compare_pair(ref, other, visible)
    else:
        found = await (compare_near if near else compare)(ref, visible)
    own = None if found is None else ModelRegistry._model_dict.get(found.statement.type)
    if found is None or not isinstance(own, type) or not issubclass(own, asked):
        raise none_for(model_name, ref)
    return found.as_json()
