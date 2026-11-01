"""What the models call to write (create, update, delete, undelete) and what users and review keep: the same for
every Cypher backend. A backend's `exposed_functions` gives these, with its reads."""

import datetime
from collections.abc import Awaitable, Callable
from typing import Any, Literal, cast
from uuid import UUID

from pangloss_models import hooks
from pangloss_models.exceptions import (
    PanglossConflictError,
    PanglossEntityInUseError,
    PanglossVersionConflictError,
    PanglossWriteError,
)
from pangloss_models.hooks import WriteEvent, emit_write_event
from pangloss_models.model_bases.document import (
    Document,
    _DocumentCreateBase,
    _DocumentCreateDBBase,
    _DocumentReferenceViewAPIMeta,
    _DocumentUpdateBase,
    _DocumentUpdateDBBase,
)
from pangloss_models.model_bases.entity import (
    Entity,
    _EntityUpdateBase,
    _EntityUpdateDBBase,
)
from pangloss_users import current_request_username
from pangloss_users.models import AccessTokenRecord, UserInDB
from pydantic import AnyHttpUrl

from pangloss_cypher import review, users
from pangloss_cypher.build_update_query import build_replace_head_query
from pangloss_cypher.delete_node import DeletionResult, soft_delete, undelete
from pangloss_cypher.read_functions import get_document, get_entity
from pangloss_cypher.render_write import render
from pangloss_cypher.transactions import (
    Transaction,
    dialect,
    read_transaction,
    write_transaction,
)
from pangloss_cypher.validate_write import (
    ExistingHead,
    check_ids_available,
    check_inline_entities,
    check_references_exist,
    check_urls_available,
    check_user_exists,
    find_existing_entities,
    get_existing_head,
    get_tree_meta,
    replace_urls,
)
from pangloss_cypher.write_plan import (
    ExistingEntity,
    InlineEntityKey,
    WritePlan,
    plan_create,
    plan_update,
)


# A function run inside the transaction of an update, before anything is read or written (to take a lock, and check what
# the lock keeps true: a typology's move). It may raise to stop the update
type BeforeWrite = Callable[[Transaction], Awaitable[None]]


async def run_write_query(tx: Transaction, query: str, params: dict) -> list:
    """Run a query that writes, and get its result"""
    response = await tx.run(query, **params)  # type: ignore
    return await response.value()


@write_transaction
async def soft_delete_node(
    tx: Transaction, cls: type[Document | Entity], id: UUID | AnyHttpUrl
) -> DeletionResult:
    return await soft_delete(tx, cls, id)


def announce(
    op: Literal["create", "update", "delete", "undelete"],
    model: type,
    id: UUID,
    version: int,
    payload: Any | None = None,
    created_entities: tuple[Any, ...] = (),
    restored_from: int | None = None,
) -> None:
    """Tell the listeners (`pangloss_models.hooks`) of a write that has committed"""
    emit_write_event(
        WriteEvent(
            op=op,
            model=model,
            id=id,
            version=version,
            user=current_request_username.get(),
            at=datetime.datetime.now(datetime.UTC),
            payload=payload,
            created_entities=created_entities,
            restored_from=restored_from,
        )
    )


async def delete_document(cls: type[Document], id: UUID) -> None:
    """Delete a head document (it is flagged, not removed). A document that is nested
    in another cannot be deleted."""
    result = await soft_delete_node(cls, id)
    if result.id is not None:
        announce("delete", cls, result.id, result.version)


async def delete_entity(cls: type[Entity], id: UUID | AnyHttpUrl) -> None:
    """Delete an entity that nothing refers to (it is flagged, not removed).

    If something does, it is not deleted, but marked for deletion
    (`meta.marked_for_deletion`), and a `PanglossEntityInUseError` is raised."""
    result = await soft_delete_node(cls, id)
    if result.deleted and result.id is not None:
        announce("delete", cls, result.id, result.version)
    if not result.deleted:
        raise PanglossEntityInUseError(
            f"{cls.__name__} {id} is referred to by {result.reference_count} "
            f"object{'s' if result.reference_count != 1 else ''}, so cannot be "
            "deleted. It has been marked for deletion",
            entity_id=id,
            referenced_by=result.referenced_by,
        )


@write_transaction
async def undelete_node(
    tx: Transaction, cls: type[Document | Entity], id: UUID | AnyHttpUrl
) -> tuple[UUID, int]:
    return await undelete(tx, cls, id)


async def undelete_document(cls: type[Document], id: UUID) -> None:
    """Restore a deleted head document. `PanglossNotDeletedError` is raised if it has
    not been deleted."""
    node_id, version = await undelete_node(cls, id)
    announce("undelete", cls, node_id, version)


async def undelete_entity(cls: type[Entity], id: UUID | AnyHttpUrl) -> None:
    """Restore a deleted entity (by id or URL). `PanglossNotDeletedError` is raised if
    it has not been deleted."""
    node_id, version = await undelete_node(cls, id)
    announce("undelete", cls, node_id, version)


@write_transaction
async def write_head_node(
    tx: Transaction,
    db_instance: _DocumentCreateDBBase,
) -> tuple[Any, ...]:
    """Write a new head node. Gives the entities that the write made as well (named in
    the document, and not there before)"""

    await check_user_exists(tx)

    plan = plan_create(db_instance)
    existing = await checked_plan(tx, plan)

    query_object = render(plan, existing)
    result = await run_write_query(
        tx, query_object.to_query_string(), query_object.params
    )
    # (not reached by any test: the user and what the plan refers to were checked above, in this
    # transaction, so every MATCH of the query finds its node. A guard, if one ever does not)
    if not result:
        raise PanglossWriteError("Nothing was written")
    return plan.created_entities(existing)


async def checked_plan(
    tx: Transaction, plan: WritePlan
) -> dict[InlineEntityKey, ExistingEntity]:
    """Check that a write can be made, before anything is written: the entities written in it are the ones there are,
    if they exist; what it refers to exists; no id or URL it gives is taken. Gives the entities written in it that
    exist (the query is different for them)"""
    existing: dict[InlineEntityKey, ExistingEntity] = {}
    if plan.inline_entities:
        existing = await find_existing_entities(tx, plan.inline_entities)
        check_inline_entities(plan.inline_entities, existing)
    await check_references_exist(tx, plan, existing)
    await check_ids_available(tx, plan, existing)
    await check_urls_available(tx, plan, existing)
    return existing


# How many times a write is tried, if it loses a race to write the same id or URL
WRITE_ATTEMPTS = 3


async def write_with_retries(write, *args):
    """Run a write, again if it breaks a uniqueness constraint when it commits.

    That is an id or URL that another write used at the same moment, after this one
    had checked that it was free. Running it again checks again: if the other write
    made an entity that this one also writes, this one now finds it and uses it; if
    it is something that cannot be shared, it is a conflict."""
    for attempt in range(1, WRITE_ATTEMPTS + 1):
        try:
            return await write(*args)
        except PanglossConflictError:
            # (on a database that reads what is committed, a conflict found by a check may be a race that was lost:
            # run again, and it is found as what it is. See `Dialect.retry_on_check_conflict`)
            if not dialect().retry_on_check_conflict or attempt == WRITE_ATTEMPTS:
                raise
        except Exception as error:
            if not dialect().is_unique_violation(error):
                raise
            if attempt == WRITE_ATTEMPTS:
                raise PanglossConflictError(
                    "An id or URL in this write was used by other writes at the "
                    "same time"
                ) from error


async def _get_head_view(cls: type[Document | Entity], id: UUID):
    if cls.__metatype__ == "Entity":
        return await get_entity(cast(type[Entity], cls), id)
    return await get_document(cast(type[Document], cls), id)


async def create_head_node(
    instance: _DocumentCreateBase,
    detail: bool = False,
    published: bool | None = None,
    review_status: str | None = None,
):
    """Create a Document or Entity. Returns its `ReferenceView`, or, if `detail`, its
    `HeadView`.

    With `pangloss-review`, a new document of a reviewed class is `unchecked` (not published) unless
    `published=True` (it is `checked`) or a `review_status` is given."""
    db_instance: _DocumentCreateDBBase = cast(
        _DocumentCreateDBBase, instance._to_db_model()
    )
    with hooks.requesting_review_status(
        hooks.review_status_asked(published, review_status)
    ):
        created_entities = await write_with_retries(write_head_node, db_instance)

    owner = cast(type[Document | Entity], instance._owner)
    announce("create", owner, db_instance.id, 1, db_instance, created_entities)
    if detail:
        return await _get_head_view(owner, db_instance.id)
    return owner.ReferenceView(
        **db_instance.model_dump(),
        meta=_DocumentReferenceViewAPIMeta(created_by=current_request_username.get()),
    )


@write_transaction
async def replace_head_node(
    tx: Transaction,
    db_instance: _DocumentUpdateDBBase | _EntityUpdateDBBase,
    expected_version: int | None = None,
    before_write: BeforeWrite | None = None,
) -> tuple[ExistingHead, tuple[Any, ...]]:
    """Replace everything below a head node, and its properties, with the new
    version. All checks are made before anything is deleted, and if anything
    fails the transaction is rolled back.

    If `expected_version` is given, the update is only made if that is the version
    of the head node now. (Two updates at once are safe: both read the version, but
    both write to the head node, so the second is made to run again by the
    database, and then finds the new version.)

    `before_write` is run first, in the transaction."""

    await check_user_exists(tx)
    if before_write is not None:
        await before_write(tx)
    await dialect().before_replace(tx, db_instance.id)
    existing_head = await get_existing_head(tx, db_instance.id, db_instance.type)
    if expected_version is not None and existing_head.version != expected_version:
        raise PanglossVersionConflictError(
            f"{db_instance.type} {db_instance.id} is at version "
            f"{existing_head.version}, not {expected_version}: it has been updated "
            "since it was read",
            current_version=existing_head.version,
        )
    previous_meta = await get_tree_meta(tx, db_instance.id)

    plan = plan_update(db_instance, previous_meta)
    existing = await checked_plan(tx, plan)

    replace_query, replace_params = build_replace_head_query(db_instance)

    # (a guard, as in `write_head_node`: the head was read above, in this transaction)
    if not await run_write_query(tx, replace_query, replace_params):
        raise PanglossWriteError("Nothing was updated")

    # (the URLs of an entity are nodes it does not own, so they are replaced apart)
    urls = getattr(db_instance, "urls", None)
    if urls is not None:
        await replace_urls(tx, db_instance.id, [str(url) for url in urls])

    query_object = render(plan, existing)
    # (a guard, as in `write_head_node`)
    if not await run_write_query(
        tx, query_object.to_query_string(), query_object.params
    ):
        raise PanglossWriteError("Nothing was written")

    return existing_head, plan.created_entities(existing)


async def update_head_node(
    instance: _DocumentUpdateBase | _EntityUpdateBase,
    detail: bool = False,
    expected_version: int | None = None,
    restored_from: int | None = None,
    published: bool | None = None,
    review_status: str | None = None,
    before_write: BeforeWrite | None = None,
):
    """Replace a Document or Entity (and, for a Document, everything nested in it)
    with the given version.

    With `pangloss-review`, an update leaves the review state as it is unless `published` (`True` is `checked`,
    `False` is `unchecked`) or `review_status` is given.

    `restored_from` is only for what listens to writes (history): that this update puts
    back that earlier version.

    `expected_version` is the `meta.version` that the new version was made from:
    if someone has updated it since, `PanglossVersionConflictError` is raised and
    nothing is written. Without it, the update is made whatever the version.

    `before_write` is run inside the transaction, before anything is read (see `BeforeWrite`)."""
    db_instance = cast(
        _DocumentUpdateDBBase | _EntityUpdateDBBase, instance._to_db_model()
    )
    with hooks.requesting_review_status(
        hooks.review_status_asked(published, review_status)
    ):
        existing_head, created_entities = await write_with_retries(
            replace_head_node, db_instance, expected_version, before_write
        )

    owner = cast(type[Document | Entity], instance._owner)
    announce(
        "update",
        owner,
        db_instance.id,
        existing_head.version + 1,
        db_instance,
        created_entities,
        restored_from,
    )
    if detail:
        return await _get_head_view(owner, db_instance.id)
    return owner.ReferenceView(
        **db_instance.model_dump(),
        meta=_DocumentReferenceViewAPIMeta(
            created_by=existing_head.created_by,
            created_when=existing_head.created_when,
            updated_by=current_request_username.get(),
            updated_when=datetime.datetime.now(datetime.UTC),
        ),
    )


# ---------------------------------------------------------------------------
# Users (see `pangloss_users.service`)
# ---------------------------------------------------------------------------


@write_transaction
async def create_user_in_db(tx: Transaction, user: UserInDB) -> None:
    await users.create_user(tx, user)


@read_transaction
async def get_user_in_db(tx: Transaction, username: str) -> UserInDB | None:
    return await users.get_user(tx, username)


@read_transaction
async def get_user_in_db_by_email(tx: Transaction, email: str) -> UserInDB | None:
    return await users.get_user_by_email(tx, email)


@read_transaction
async def list_users_in_db(tx: Transaction) -> list[UserInDB]:
    return await users.list_users(tx)


@write_transaction
async def update_user_in_db(
    tx: Transaction, username: str, changes: dict[str, Any]
) -> UserInDB:
    return await users.update_user(tx, username, changes)


@write_transaction
async def revoke_session_in_db(
    tx: Transaction, jti: str, expires: datetime.datetime
) -> None:
    await users.revoke_session(tx, jti, expires)


@read_transaction
async def is_session_revoked_in_db(tx: Transaction, jti: str) -> bool:
    return await users.is_session_revoked(tx, jti)


@write_transaction
async def create_access_token_in_db(tx: Transaction, record: AccessTokenRecord) -> None:
    await users.create_access_token(tx, record)


@read_transaction
async def get_access_token_in_db_by_hash(
    tx: Transaction, token_hash: str
) -> AccessTokenRecord | None:
    return await users.get_access_token_by_hash(tx, token_hash)


@read_transaction
async def list_access_tokens_in_db(
    tx: Transaction, username: str
) -> list[AccessTokenRecord]:
    return await users.list_access_tokens(tx, username)


@write_transaction
async def delete_access_token_in_db(tx: Transaction, username: str, id: str) -> bool:
    return await users.delete_access_token(tx, username, id)


@write_transaction
async def touch_access_token_in_db(
    tx: Transaction, id: str, when: datetime.datetime
) -> None:
    await users.touch_access_token(tx, id, when)


# Review (`pangloss-review`)


@read_transaction
async def get_review_state_in_db(tx: Transaction, id: UUID) -> dict[str, Any] | None:
    return await review.get_review_state(tx, id)


@write_transaction
async def set_review_status_in_db(
    tx: Transaction, id: UUID, status: str, published: bool, user: str
) -> dict[str, Any] | None:
    return await review.set_review_status(tx, id, status, published, user)


@write_transaction
async def add_review_comment_in_db(
    tx: Transaction, id: UUID, username: str, text: str, target_id: UUID | None
) -> dict[str, Any] | str | None:
    return await review.add_review_comment(tx, id, username, text, target_id)


@read_transaction
async def list_review_comments_in_db(
    tx: Transaction, id: UUID, include_resolved: bool
) -> list[dict[str, Any]]:
    return await review.list_review_comments(tx, id, include_resolved)


@write_transaction
async def resolve_review_comment_in_db(
    tx: Transaction, id: UUID, comment_id: UUID, user: str
) -> dict[str, Any] | None:
    return await review.resolve_review_comment(tx, id, comment_id, user)


@read_transaction
async def review_queue_in_db(
    tx: Transaction, statuses: list[str], type: str | None, page: int, page_size: int
) -> dict[str, Any]:
    return await review.review_queue(tx, statuses, type, page, page_size)
