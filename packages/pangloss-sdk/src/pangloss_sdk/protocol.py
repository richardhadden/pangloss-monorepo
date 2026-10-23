"""The requests for the model functions, and what is made of the answers.

No input or output happens here: each operation is a `Call` (what to ask), and a function
that turns the response into what the database module would have returned, or raises what
it would have raised. The async and the sync client both use these.
"""

import dataclasses
from typing import Any, Literal, Union
from uuid import UUID

from pangloss_models import exceptions as models_exceptions
from pangloss_models.model_bases.base_models import _ListItems
from pangloss_models.utils import get_concrete_types
from pydantic import TypeAdapter

from pangloss_sdk.exceptions import (
    PanglossAuthenticationError,
    PanglossPermissionError,
    PanglossRequestError,
    PanglossServerError,
)


@dataclasses.dataclass
class Call:
    method: Literal["GET", "POST", "PUT", "DELETE"]
    path: str
    params: dict[str, Any] | None = None
    json: Any = None
    headers: dict[str, str] | None = None
    # Known to need a login: it is asked for before the request, not after a refusal
    needs_login: bool = False

    @property
    def is_read(self) -> bool:
        """Safe to send again after a network error (nothing was changed)"""
        return self.method == "GET"


# --- errors ---------------------------------------------------------------------------


# The server names the error in its answer (`error`): the class is what is raised
ERRORS_BY_NAME: dict[str, type[Exception]] = {
    cls.__name__: cls
    for cls in (
        models_exceptions.PanglossNotFoundError,
        models_exceptions.PanglossReferenceError,
        models_exceptions.PanglossConflictError,
        models_exceptions.PanglossVersionConflictError,
        models_exceptions.PanglossEntityInUseError,
        models_exceptions.PanglossNotDeletableError,
        models_exceptions.PanglossNotDeletedError,
        models_exceptions.PanglossUserNotFoundError,
        models_exceptions.PanglossUserDisabledError,
        models_exceptions.PanglossReadOnlyError,
        models_exceptions.PanglossWriteError,
    )
}

# (without a name: what the status says)
ERRORS_BY_STATUS: dict[int, type[Exception]] = {
    404: models_exceptions.PanglossNotFoundError,
    409: models_exceptions.PanglossConflictError,
    412: models_exceptions.PanglossVersionConflictError,
    503: models_exceptions.PanglossReadOnlyError,
}


def body_of(response: Any) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def message_of(response: Any, body: dict) -> str:
    detail = body.get("detail")
    if isinstance(detail, str):
        return detail
    if detail is not None:
        return str(detail)
    return response.text[:300] or f"HTTP {response.status_code}"


def error_for(response: Any) -> Exception:
    """The exception for a response that is not a success"""
    status = response.status_code
    body = body_of(response)
    message = message_of(response, body)

    if status == 401:
        return PanglossAuthenticationError(message)
    if status >= 500 and status != 503:
        return PanglossServerError(message, status)

    kind = ERRORS_BY_NAME.get(str(body.get("error")))
    if kind is None and status == 403:
        return PanglossPermissionError(message)
    if kind is None:
        kind = ERRORS_BY_STATUS.get(status)
    if kind is None:
        if status in (400, 422, 428):
            return PanglossRequestError(message, status)
        return PanglossServerError(message, status)

    if kind is models_exceptions.PanglossVersionConflictError:
        return kind(message, current_version=body.get("currentVersion"))
    if kind is models_exceptions.PanglossEntityInUseError:
        return kind(
            message,
            entity_id=None,
            referenced_by=body.get("referencedBy", []),
        )
    return kind(message)


def check(response: Any) -> None:
    if not response.is_success:
        raise error_for(response)


# --- the operations -------------------------------------------------------------------


def item_path(cls: type, id: UUID | Any) -> str:
    # (an entity's URL goes in the path as it is, with its query string)
    return f"/api/{cls.__name__}/{id}"


def get(cls: type, id: Any) -> Call:
    return Call("GET", item_path(cls, id))


def got(cls: type, response: Any) -> Any:
    """`cls.HeadView`, or None if there is no such item"""
    if response.status_code == 404:
        return None
    check(response)
    return cls.HeadView.model_validate(response.json())  # type: ignore[attr-defined]


def get_for_edit(cls: type, id: Any) -> Call:
    return Call("GET", f"{item_path(cls, id)}/edit", needs_login=True)


def got_for_edit(cls: type, response: Any) -> Any:
    if response.status_code == 404:
        return None
    check(response)
    return cls.EditView.model_validate(response.json())  # type: ignore[attr-defined]


def list_items(
    cls: type,
    search_terms: str | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    deep_search: bool = False,
) -> Call:
    params: dict[str, Any] = {}
    if search_terms is not None:
        params["q"] = search_terms
    if page_number is not None:
        params["page"] = page_number
    if page_size is not None:
        params["page_size"] = page_size
    if deep_search:
        params["deep"] = "true"
    return Call("GET", f"/api/{cls.__name__}", params=params)


def listed(cls: type, response: Any) -> Any:
    check(response)
    data = response.json()
    reference_views = [t.ReferenceView for t in get_concrete_types(cls)]  # type: ignore[attr-defined]
    adapter = TypeAdapter(list[Union[*reference_views]])  # type: ignore[valid-type]
    results = adapter.validate_python(data["results"])
    return _ListItems.model_validate({**data, "results": results})


def create(instance: Any, detail: bool = False) -> Call:
    owner = instance._owner
    return Call(
        "POST",
        f"/api/{owner.__name__}",
        params={"detail": "true"} if detail else None,
        json=instance.model_dump(mode="json", by_alias=True),
        needs_login=True,
    )


def created(instance: Any, response: Any, detail: bool = False) -> Any:
    check(response)
    owner = instance._owner
    view = owner.HeadView if detail else owner.ReferenceView
    return view.model_validate(response.json())


def update(
    instance: Any, detail: bool = False, expected_version: int | None = None
) -> Call:
    owner = instance._owner
    # (without a version, whatever the version is: as the database module does)
    if_match = "*" if expected_version is None else f'"{expected_version}"'
    return Call(
        "PUT",
        item_path(owner, instance.id),
        params={"detail": "true"} if detail else None,
        json=instance.model_dump(mode="json", by_alias=True),
        headers={"If-Match": if_match},
        needs_login=True,
    )


def updated(instance: Any, response: Any, detail: bool = False) -> Any:
    return created(instance, response, detail)


def delete(cls: type, id: Any) -> Call:
    return Call("DELETE", item_path(cls, id), needs_login=True)


def undelete(cls: type, id: Any) -> Call:
    return Call("POST", f"{item_path(cls, id)}/undelete", needs_login=True)


def done(response: Any) -> None:
    check(response)
