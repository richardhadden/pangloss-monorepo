"""Writing several heads at once (`create_heads`): bound to the storage's operation when the models are initialised"""

from collections.abc import Awaitable, Callable
from typing import Any

from pangloss_models.exceptions import PanglossAwaitingInitialisation

# (the storage's `create_heads`, set by `ModelRegistry._bind_database_functions`; None for one that has none)
bound: Callable[..., Awaitable[list[Any]]] | None = None
storage_name: str | None = None


async def create_heads(
    *instances: Any, detail: bool = False, **options: Any
) -> list[Any]:
    """Create several Documents and Entities in one transaction: all of them, or none (a `Create` each, or the
    `CreateDB` it makes, so that a later one can refer to an earlier one by its id). Gives the `ReferenceView` of each,
    or with `detail` its `HeadView`. `options` are those of `save()`: `published`, `review_status`, `created_by`,
    `toolchain`, `review_assigned_to` (implementation_docs/companion-documents.md)"""
    if bound is None:
        raise PanglossAwaitingInitialisation(
            "create_heads needs the models initialised with a database"
            + (
                f": the storage {storage_name!r} cannot write several heads at once"
                if storage_name
                else ""
            )
        )
    return await bound(*instances, detail=detail, **options)
