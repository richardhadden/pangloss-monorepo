"""What the models call to write (create, update, delete, undelete) and what users and review keep: the same for
every Cypher backend. A backend's `exposed_functions` gives these, with its reads."""

import datetime
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Literal, cast
from uuid import UUID

from pangloss_models import (
    Document,
    Entity,
    PanglossClassChangeError,
    PanglossConflictError,
    PanglossEntityInUseError,
    PanglossNotFoundError,
    PanglossVersionConflictError,
    PanglossWriteError,
    WriteEvent,
    hooks,
)
from pangloss_models.creators import (
    ToolchainRun,
    creators_asked,
    requested_creators,
    writing_as,
)
from pangloss_models.hooks import emit_write_event
from pangloss_models.model_bases.document import (
    _DocumentCreateBase,
    _DocumentCreateDBBase,
    _DocumentReferenceViewAPIMeta,
    _DocumentUpdateBase,
    _DocumentUpdateDBBase,
)
from pangloss_models.model_bases.entity import _EntityUpdateBase, _EntityUpdateDBBase
from pangloss_models.model_bases.labels import labels_for_model
from pangloss_models.write_checks import check_before_create, check_before_update
from pangloss_users import UserInDB, current_request_username
from pangloss_users.models import AccessTokenRecord
from pydantic import AnyHttpUrl

from pangloss_cypher import pending, review, users
from pangloss_cypher.build_update_query import build_replace_head_query
from pangloss_cypher.checks import check_creators_exist
from pangloss_cypher.delete_node import (
    DeletionCheck,
    DeletionResult,
    check_deletion,
    soft_delete,
    undelete,
)
from pangloss_cypher.read_functions import get_document, get_entity
from pangloss_cypher.read_incoming import fetch_incoming_relations
from pangloss_cypher.render_write import Statement, render
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
from pangloss_cypher.visibility import unpublished_visible
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


async def run_statements(tx: Transaction, statements: list[Statement]) -> None:
    """Run the statements of a write (`render_write`), in order. Each says how many rows it wrote: fewer than it was
    given is a node that was to be written to and was not found, and the write is not made (the transaction is rolled
    back by the error).

    (Not reached by any test: the user, the head and what the plan refers to are checked before, in this transaction,
    so every `MATCH` finds its node. A guard, if one ever does not.)"""
    for statement in statements:
        written = await run_write_query(tx, statement.text, statement.params)
        if not written or written[0] != statement.rows:
            raise PanglossWriteError(
                "Nothing was written: a node that the write is made to was not found"
            )


@write_transaction
async def soft_delete_node(
    tx: Transaction, cls: type[Document | Entity], id: UUID | AnyHttpUrl
) -> DeletionResult:
    result = await soft_delete(tx, cls, id)
    if result.deleted and result.id is not None:
        await pending.mark_written(tx, cls, result.id)
    return result


@read_transaction
async def check_deletable(
    tx: Transaction, cls: type[Document | Entity], id: UUID | AnyHttpUrl
) -> DeletionCheck:
    """Whether a delete of this would go through, and if not why (nothing is written)"""
    return await check_deletion(tx, cls, id)


def announce(
    op: Literal["create", "update", "delete", "undelete"],
    model: type,
    id: UUID,
    version: int,
    payload: Any | None = None,
    created_entities: tuple[Any, ...] = (),
    restored_from: int | None = None,
    changed_class_from: type | None = None,
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
            changed_class_from=changed_class_from,
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
    node_id, version = await undelete(tx, cls, id)
    await pending.mark_written(tx, cls, node_id)
    return node_id, version


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
    await check_creators_exist(tx)

    plan = plan_create(db_instance)
    existing = await checked_plan(tx, plan)

    await run_statements(tx, render(plan, existing))
    created = plan.created_entities(existing)
    await pending.mark_written(tx, db_instance._owner, db_instance.id, created)
    return created


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
    created_by: Iterable[str] | str | None = None,
    toolchain: ToolchainRun | str | None = None,
    review_assigned_to: str | None = None,
):
    """Create a Document or Entity. Returns its `ReferenceView`, or, if `detail`, its
    `HeadView`.

    `created_by` (usernames) and `toolchain` (a `ToolchainRun`, or the name of one): those the item is recorded as
    made by, instead of the user of the write, who is recorded as having uploaded it (`pangloss_models.creators`).
    Each must be a user, the toolchain one of kind `toolchain`. (Over the API only an admin may.)

    `review_assigned_to`: with `pangloss-review`, the user who is to review the new document.

    With `pangloss-review`, a new document of a reviewed class is `unchecked` (not published) unless
    `published=True` (it is `checked`) or a `review_status` is given."""
    # (what the call names, or what is asked around it: `writing_as`, as the API does. Known while the model for the
    # database is made: a validator of a class may say who wrote a part, as the library's `Identification` does)
    creators = creators_asked(created_by, toolchain) or requested_creators.get()
    with writing_as(creators):
        db_instance: _DocumentCreateDBBase = cast(
            _DocumentCreateDBBase, instance._to_db_model()
        )
    await check_before_create(db_instance)
    with (
        hooks.requesting_review_status(
            hooks.review_status_asked(published, review_status)
        ),
        writing_as(creators),
        hooks.requesting_review_assignee(review_assigned_to),
    ):
        created_entities = await write_with_retries(write_head_node, db_instance)

    owner = cast(type[Document | Entity], instance._owner)
    announce("create", owner, db_instance.id, 1, db_instance, created_entities)
    if detail:
        return await _get_head_view(owner, db_instance.id)
    return owner.ReferenceView(
        **db_instance.model_dump(),
        meta=_DocumentReferenceViewAPIMeta(
            created_by=creators or current_request_username.get(),
            uploaded_by=current_request_username.get() if creators else None,
        ),
    )


type Referrers = set[tuple[str, str, str]]


async def referrers(tx: Transaction, cls: type[Entity], id: UUID) -> Referrers:
    """What refers to an entity, read as being of `cls`: (the name of the relation, the type and id of what holds it)"""
    incoming, _ = await fetch_incoming_relations(tx, cls, id)
    return {
        (name, str(item["type"]), str(item["id"]))
        for name, items in incoming.items()
        for item in items
    }


async def check_class_change(
    tx: Transaction, db_instance: _EntityUpdateDBBase, old: type
) -> Referrers:
    """That the head is an entity of exactly the class `old`, which it is to be changed from. Gives what refers to it"""
    new = db_instance._owner
    if old.__metatype__ != "Entity" or new.__metatype__ != "Entity":
        raise PanglossClassChangeError(
            f"Only an entity can change its class, not a {old.__name__} into a {new.__name__}"
        )
    result = await tx.run(
        "MATCH (head:HeadNode {id: $id}) RETURN head.type AS type",
        id=str(db_instance.id),
    )
    found = await result.value()
    if not found:
        raise PanglossNotFoundError(
            f"There is no {old.__name__} with id {db_instance.id}"
        )
    if found[0] != old.__name__:
        raise PanglossClassChangeError(
            f"{db_instance.id} is a {found[0]}, not a {old.__name__}, so its class cannot be changed from "
            f"{old.__name__}"
        )
    return await referrers(tx, cast(type[Entity], old), db_instance.id)


async def check_references_kept(
    tx: Transaction, db_instance: _EntityUpdateDBBase, before: Referrers
) -> None:
    """After a change of class, in its transaction: that everything that referred to the entity still does, read as
    the new class (a relation that cannot hold it is not read). Raises, so that nothing is changed, if not"""
    new = cast(type[Entity], db_instance._owner)
    lost = before - await referrers(tx, new, db_instance.id)
    if lost:
        which = ", ".join(
            f"{type_name} {id} ({name})" for name, type_name, id in sorted(lost)
        )
        raise PanglossClassChangeError(
            f"{db_instance.id} cannot become a {new.__name__}: it is referred to by a relation that cannot hold "
            f"a {new.__name__}: {which}"
        )


@write_transaction
async def replace_head_node(
    tx: Transaction,
    db_instance: _DocumentUpdateDBBase | _EntityUpdateDBBase,
    expected_version: int | None = None,
    before_write: BeforeWrite | None = None,
    changing_class_from: type | None = None,
) -> tuple[ExistingHead, tuple[Any, ...]]:
    """Replace everything below a head node, and its properties, with the new
    version. All checks are made before anything is deleted, and if anything
    fails the transaction is rolled back.

    If `expected_version` is given, the update is only made if that is the version
    of the head node now. (Two updates at once are safe: both read the version, but
    both write to the head node, so the second is made to run again by the
    database, and then finds the new version.)

    `before_write` is run first, in the transaction.

    `changing_class_from`: the class of the entity now, which becomes the class of `db_instance` (see
    `update_head_node`)."""

    await check_user_exists(tx)
    await check_creators_exist(tx)
    if before_write is not None:
        await before_write(tx)
    referred_by: Referrers = set()
    head_type = db_instance.type
    if changing_class_from is not None:
        referred_by = await check_class_change(
            tx, cast(_EntityUpdateDBBase, db_instance), changing_class_from
        )
        head_type = changing_class_from.__name__
    await dialect().before_replace(tx, db_instance.id)
    existing_head = await get_existing_head(tx, db_instance.id, head_type)
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

    replace_query, replace_params = build_replace_head_query(
        db_instance,
        remove_labels=labels_for_model(changing_class_from, "Entity")
        if changing_class_from is not None
        else (),
    )

    # (a guard, as in `run_statements`: the head was read above, in this transaction)
    if not await run_write_query(tx, replace_query, replace_params):
        raise PanglossWriteError("Nothing was updated")

    # (the URLs of an entity are nodes it does not own, so they are replaced apart)
    urls = getattr(db_instance, "urls", None)
    if urls is not None:
        await replace_urls(tx, db_instance.id, [str(url) for url in urls])

    await run_statements(tx, render(plan, existing))

    if changing_class_from is not None:
        await check_references_kept(
            tx, cast(_EntityUpdateDBBase, db_instance), referred_by
        )

    created = plan.created_entities(existing)
    await pending.mark_written(tx, db_instance._owner, db_instance.id, created)
    return existing_head, created


async def update_head_node(
    instance: _DocumentUpdateBase | _EntityUpdateBase,
    detail: bool = False,
    expected_version: int | None = None,
    restored_from: int | None = None,
    published: bool | None = None,
    review_status: str | None = None,
    before_write: BeforeWrite | None = None,
    changing_class_from: type | None = None,
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

    `before_write` is run inside the transaction, before anything is read (see `BeforeWrite`).

    `changing_class_from`: the entity is now of that class, and becomes one of this class, in place: it keeps its id,
    its URLs and what refers to it. Refused (`PanglossClassChangeError`) if it is not of that class, or if something
    refers to it by a relation that cannot hold this class."""
    db_instance = cast(
        _DocumentUpdateDBBase | _EntityUpdateDBBase, instance._to_db_model()
    )
    # (as it is now: read before the write's transaction; one made meanwhile is refused by `expected_version`)
    await check_before_update(
        db_instance,
        lambda: _get_head_view(
            changing_class_from or cast(type[Document | Entity], instance._owner),
            db_instance.id,
        ),
    )
    with hooks.requesting_review_status(
        hooks.review_status_asked(published, review_status)
    ):
        existing_head, created_entities = await write_with_retries(
            replace_head_node,
            db_instance,
            expected_version,
            before_write,
            changing_class_from,
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
        changing_class_from,
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


@read_transaction
async def list_user_items_in_db(
    tx: Transaction, username: str, page: int, page_size: int
) -> dict[str, Any]:
    return await users.list_user_items(
        tx, username, page, page_size, unpublished_visible()
    )


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
    tx: Transaction,
    statuses: list[str],
    type: str | None,
    page: int,
    page_size: int,
    assigned_to: str | None = None,
    words: list[str] | None = None,
) -> dict[str, Any]:
    return await review.review_queue(
        tx, statuses, type, page, page_size, assigned_to, words
    )


@write_transaction
async def assign_review_in_db(
    tx: Transaction, id: UUID, assignee: str | None, by: str
) -> dict[str, Any] | str | None:
    return await review.assign_review(tx, id, assignee, by)
