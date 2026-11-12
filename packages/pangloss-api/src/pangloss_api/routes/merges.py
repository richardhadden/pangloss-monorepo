"""Merging two entities that are one, and undoing a merge (implementation_docs/entity-identity.md, part 1).

For each entity class, `NAME` being its name and `{id}` the id of the entity that stays (the survivor):

| | | |
|-|-|-|
| `POST` | `/api/NAME/{id}/merge/preview` | what a merge would do, writing nothing |
| `POST` | `/api/NAME/{id}/merge`         | merge the entity `absorb` of the body into this one: for those who may merge without anyone else (`MERGE_DIRECTLY`), 403 for the rest |
| `POST` | `/api/NAME/{id}/merge/propose` | record the merge as proposed, for someone else to verify |
| `GET`  | `/api/NAME/{id}/merges`        | the merges the entity is part of, the latest first |

And for the merges themselves, by their ids:

| | | |
|-|-|-|
| `GET`  | `/api/merges`                    | the merges recorded (`state`, more than once for more; `open=true`: those waiting for someone) |
| `GET`  | `/api/merges/permissions`        | what this user may do |
| `GET`  | `/api/merges/{merge}`            | one |
| `POST` | `/api/merges/{merge}/verify`     | carry out a proposed merge: anyone but the one who proposed it |
| `POST` | `/api/merges/{merge}/reject`     | reject a proposed merge |
| `POST` | `/api/merges/{merge}/undo`       | undo a merge (`dryRun`: say what would be undone): those who may merge without anyone else, or anyone but the one who proposed the undoing |
| `POST` | `/api/merges/{merge}/undo/propose` | propose that it be undone |
| `POST` | `/api/merges/{merge}/undo/reject`  | reject that proposal |

All need a login. A merge that would write more documents than `MERGE_LIMIT` is made only by an admin.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pangloss_core import settings as core_settings
from pangloss_core import storage_of
from pangloss_models import Entity, ModelRegistry, protection_of
from pangloss_models.merging import DEFAULT_MERGE_LIMIT, to_wire
from pangloss_models.model_bases.base_models import _BaseObject
from pangloss_models.protection import changed_fields
from pydantic import ValidationError
from pangloss_users import User

from pangloss_api.dependencies import CurrentUser, get_current_user

router = APIRouter(
    prefix="/api/merges", tags=["merges"], dependencies=[Depends(get_current_user)]
)

MERGE_STATES = ("proposed", "rejected", "stale", "running", "done", "undone")
MAX_PAGE_SIZE = 500


class MergeBody(_BaseObject):
    """What is merged into the entity of the path, and how"""

    absorb: UUID
    # The fields the survivor has, as its `Update` takes them (without them: the survivor's own, the absorbed
    # entity's where it has none, and both of every list)
    values: dict[str, Any] | None = None
    # The class the survivor takes, when the two differ (without it: that of `values`, or else the narrower)
    as_class: str | None = None
    # The versions of the two entities that this was decided on (as `If-Match`): 412 if either has changed
    version_into: int | None = None
    version_absorb: int | None = None


class ProposalBody(MergeBody):
    note: str | None = None


class VerifyBody(_BaseObject):
    # (as for a merge: without them, the fields that were proposed, if neither entity has changed since)
    values: dict[str, Any] | None = None
    as_class: str | None = None
    version_into: int | None = None
    version_absorb: int | None = None


class ReasonBody(_BaseObject):
    reason: str | None = None


class NoteBody(_BaseObject):
    note: str | None = None


class UndoBody(_BaseObject):
    # The database has been migrated since the merge, and what can still be put back has been looked at
    confirm_migrated: bool = False
    # Say what would be undone, and write nothing
    dry_run: bool = False


def setting(name: str, default: Any) -> Any:
    return getattr(core_settings.__dict__.get("SETTINGS"), name, default)


def may_merge_directly(user: User) -> bool:
    """Whether the user merges, and undoes a merge, without anyone else (`MERGE_DIRECTLY`)"""
    who = setting("MERGE_DIRECTLY", "admin")
    return who == "any" or (who == "admin" and user.admin)


def operation(name: str) -> Any:
    """A merge operation of the storage, which may not have it"""
    found = getattr(storage_of().operations, name, None)
    if found is None:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED,
            detail="The storage of this project cannot merge entities",
        )
    return found


def class_named(name: str | None, values: dict[str, Any] | None) -> Any:
    """The class the survivor is to take: the one named, or the one the values given are of"""
    name = name or (values or {}).get("type")
    if name is None:
        return None
    model = ModelRegistry.all_models().get(name)
    if not (isinstance(model, type) and issubclass(model, Entity)):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"There is no entity class '{name}'",
        )
    return model


async def refuse_protected_changes(
    model: Any, survivor: UUID, values: dict[str, Any] | None, as_class: Any
) -> None:
    """Refuse (403) fields chosen for the survivor that change what something other than a person keeps up to date
    (a Zotero item's own fields), as an update of it is refused"""
    if values is None or model is None:
        return
    stored = await model.get_for_edit(survivor)
    if stored is None:
        return
    target: Any = as_class or ModelRegistry.all_models().get(stored.type)
    if target is None or not protection_of(target).read_only:
        return
    try:
        chosen = target.Update(**{**values, "id": survivor})
    except ValidationError:
        return  # (the merge says what is wrong with them)
    changed = changed_fields(target, chosen, stored)
    if changed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"{', '.join(changed)} cannot be changed here: kept up to date by something else",
        )


def answer(result: Any, code: int = status.HTTP_200_OK) -> JSONResponse:
    return JSONResponse(to_wire(result), status_code=code)


def add_merge_routes(router: APIRouter, model: type[Entity], item: str, ItemId: Any):
    """The routes of a merge into an entity of the class, at its id (they come before the route that reads the
    entity, which takes the rest of the path)"""
    name = model.__name__

    @router.post(
        f"{item}/merge/preview",
        operation_id=f"preview_merge_{name}",
        dependencies=[Depends(get_current_user)],
    )
    async def preview_merge(id: ItemId, body: MergeBody):  # type: ignore[valid-type]
        """What the merge would do, and whether it can be made (`possible`; if not, `refused` says why): the
        class and the fields the survivor would have, how many documents and entities would be written, how many
        refer to each of the two by their class, and the documents that name both. Nothing is written"""
        return answer(
            await model.merge_preview(
                absorb=body.absorb,
                into=id,
                values=body.values,
                as_class=class_named(body.as_class, body.values),
            )
        )

    @router.post(
        f"{item}/merge/propose",
        status_code=status.HTTP_201_CREATED,
        operation_id=f"propose_merge_{name}",
        dependencies=[Depends(get_current_user)],
    )
    async def propose_merge(id: ItemId, body: ProposalBody):  # type: ignore[valid-type]
        """Record the merge as proposed, with the fields chosen and a note: someone else verifies it (which
        carries it out) or rejects it. The merge is checked now, and again then. Nothing else is written"""
        await refuse_protected_changes(
            model, id, body.values, class_named(body.as_class, body.values)
        )
        return answer(
            await model.propose_merge(
                absorb=body.absorb,
                into=id,
                values=body.values,
                as_class=class_named(body.as_class, body.values),
                note=body.note,
            ),
            status.HTTP_201_CREATED,
        )

    @router.post(f"{item}/merge", operation_id=f"merge_{name}")
    async def merge(id: ItemId, body: MergeBody, user: CurrentUser):  # type: ignore[valid-type]
        """Merge the entity `absorb` into this one: everything that refers to it refers to this one, which has
        the fields given; it is kept, marked as merged, and can be brought back (`POST /api/merges/{merge}/undo`).
        403 for a user who may not merge without anyone else (`MERGE_DIRECTLY`): they propose it"""
        if not may_merge_directly(user):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="You may propose this merge, for someone else to verify (POST .../merge/propose): "
                "merging without that is not for every user in this project",
            )
        await refuse_protected_changes(
            model, id, body.values, class_named(body.as_class, body.values)
        )
        return answer(
            await model.merge(
                absorb=body.absorb,
                into=id,
                values=body.values,
                as_class=class_named(body.as_class, body.values),
                version_into=body.version_into,
                version_absorb=body.version_absorb,
                allow_large=user.admin,
            )
        )

    @router.get(
        f"{item}/merges",
        operation_id=f"merges_of_{name}",
        dependencies=[Depends(get_current_user)],
    )
    async def merges_of_entity(id: ItemId):  # type: ignore[valid-type]
        """The merges the entity is part of, as the one that stayed or the one absorbed, the latest first: those
        proposed, rejected and undone too"""
        return JSONResponse({"merges": to_wire(await model.merges(id))})


@router.get("/permissions", operation_id="merge_permissions")
async def permissions(user: CurrentUser):
    """What this user may do: merge and undo without anyone else (`direct`), or propose and verify; and how
    many documents a merge may write before it needs an admin"""
    return {
        "direct": may_merge_directly(user),
        "large": user.admin,
        "limit": setting("MERGE_LIMIT", DEFAULT_MERGE_LIMIT),
    }


@router.get("", operation_id="list_merges")
async def list_merges(
    state: Annotated[
        list[str] | None,
        Query(description=f"Only those in this state ({', '.join(MERGE_STATES)})"),
    ] = None,
    open: Annotated[
        bool,
        Query(
            description="Those waiting for someone: proposed, or proposed to be undone"
        ),
    ] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
):
    unknown = [s for s in state or [] if s not in MERGE_STATES]
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"'{unknown[0]}' is not a state of a merge: {', '.join(MERGE_STATES)}",
        )
    states = [*(state or []), *(["proposed"] if open else [])]
    merges, count = await operation("list_merges")(
        states=states or None,
        undo_proposed=open,
        skip=(page - 1) * page_size,
        limit=page_size,
    )
    return JSONResponse(
        {
            "results": to_wire(merges),
            "count": count,
            "page": page,
            "pageSize": page_size,
        }
    )


@router.get("/{merge_id}", operation_id="get_merge")
async def get_merge(merge_id: UUID):
    return answer(await operation("get_merge")(merge_id))


@router.post("/{merge_id}/verify", operation_id="verify_merge")
async def verify_merge(
    merge_id: UUID, user: CurrentUser, body: VerifyBody | None = None
):
    """Carry out a merge that someone else proposed, with the fields they chose, or with those given here and the
    versions they were decided on. 403 for the one who proposed it; 412 if an entity has changed since it was
    proposed and no fields are given"""
    body = body or VerifyBody()
    if body.values is not None:
        proposal = await operation("get_merge")(merge_id)
        await refuse_protected_changes(
            ModelRegistry.all_models().get(proposal.survivor_type_before),
            proposal.survivor,
            body.values,
            class_named(body.as_class, body.values),
        )
    return answer(
        await operation("verify_merge")(
            merge_id,
            values=body.values,
            as_class=class_named(body.as_class, body.values),
            version_into=body.version_into,
            version_absorb=body.version_absorb,
            allow_large=user.admin,
        )
    )


@router.post("/{merge_id}/reject", operation_id="reject_merge")
async def reject_merge(merge_id: UUID, body: ReasonBody | None = None):
    return answer(
        await operation("reject_merge")(merge_id, body.reason if body else None)
    )


@router.post("/{merge_id}/undo", operation_id="undo_merge")
async def undo_merge(merge_id: UUID, user: CurrentUser, body: UndoBody | None = None):
    """Undo a merge: what it moved goes back to the entity it absorbed, where that can still be done (the rest is
    listed), and that entity is itself again. For those who may merge without anyone else; for the rest, only if
    someone else proposed that it be undone (403 otherwise). `dryRun` says what would be done, for anyone"""
    body = body or UndoBody()
    return answer(
        await Entity.unmerge(
            merge_id,
            confirm_migrated=body.confirm_migrated,
            dry_run=body.dry_run,
            accepting=not body.dry_run and not may_merge_directly(user),
        )
    )


@router.post("/{merge_id}/undo/propose", operation_id="propose_undo_merge")
async def propose_undo(merge_id: UUID, body: NoteBody | None = None):
    """Propose that the merge be undone: someone else accepts (by undoing it) or rejects that"""
    return answer(
        await operation("propose_unmerge")(merge_id, body.note if body else None)
    )


@router.post("/{merge_id}/undo/reject", operation_id="reject_undo_merge")
async def reject_undo(merge_id: UUID, body: ReasonBody | None = None):
    return answer(
        await operation("reject_unmerge")(merge_id, body.reason if body else None)
    )
