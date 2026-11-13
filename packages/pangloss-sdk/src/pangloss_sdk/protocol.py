"""The requests for the model functions, and what is made of the answers.

No input or output happens here: each operation is a `Call` (what to ask), and a function
that turns the response into what the database module would have returned, or raises what
it would have raised. The async and the sync client both use these.
"""

import dataclasses
from collections.abc import Iterable
from typing import Any, Literal, Union
from uuid import UUID

from pangloss_models import Match, hooks
from pangloss_models import exceptions as models_exceptions
from pangloss_models.creators import ToolchainRun, creators_asked
from pangloss_models.autocomplete import AutocompleteItem, AutocompleteResults
from pangloss_models.model_bases.base_models import _ListItems
from pangloss_models.search import check_match
from pangloss_models.utils import get_concrete_types
from pydantic import TypeAdapter
from pydantic.alias_generators import to_snake

from pangloss_sdk.exceptions import (
    PanglossAuthenticationError,
    PanglossMergedIntoOtherClass,
    PanglossPermissionError,
    PanglossRequestError,
    PanglossSdkOutOfDate,
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
        PanglossSdkOutOfDate,
        models_exceptions.PanglossNotFoundError,
        models_exceptions.PanglossReferenceError,
        models_exceptions.PanglossWriteRefused,
        models_exceptions.PanglossConflictError,
        models_exceptions.PanglossVersionConflictError,
        models_exceptions.PanglossEntityInUseError,
        models_exceptions.PanglossClassChangeError,
        models_exceptions.PanglossMergeError,
        models_exceptions.PanglossMergeNotAllowedError,
        models_exceptions.PanglossMergeTooLargeError,
        models_exceptions.PanglossMergeBusyError,
        models_exceptions.PanglossMergedError,
        models_exceptions.PanglossCitedError,
        models_exceptions.PanglossNotDeletableError,
        models_exceptions.PanglossNotDeletedError,
        models_exceptions.PanglossUserNotFoundError,
        models_exceptions.PanglossUserDisabledError,
        models_exceptions.PanglossReadOnlyError,
        models_exceptions.PanglossSearchTimeoutError,
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
    if status >= 500 and status != 503 and str(body.get("error")) not in ERRORS_BY_NAME:
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
    if kind is models_exceptions.PanglossMergedError:
        return kind(message, merged_into=body.get("mergedInto"))
    if kind is models_exceptions.PanglossCitedError:
        return kind(
            message,
            changed=[snake_keys(row) for row in body.get("changed", [])],
            removed=[snake_keys(row) for row in body.get("removed", [])],
            fix=body.get("fix"),
        )
    if kind is models_exceptions.PanglossMergeTooLargeError:
        return kind(message, heads=body.get("heads", 0), limit=body.get("limit", 0))
    if kind is models_exceptions.PanglossWriteRefused:
        # (about a field: `[{"loc": ["body", "clauses", 0, "text"], "msg": ...}]`)
        detail = body.get("detail")
        if isinstance(detail, list) and detail and isinstance(detail[0], dict):
            loc = [
                to_snake(part) if isinstance(part, str) else part
                for part in (detail[0].get("loc") or [])[1:]
            ]
            field = loc[-1] if loc and isinstance(loc[-1], str) else None
            refused = kind(str(detail[0].get("msg", message)), field=field)
            refused.path = tuple(loc)
            return refused
        return kind(message)
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


def class_of_answer(cls: type, payload: Any) -> type:
    """The class the server says an item is (its `type`), if that is a subclass of `cls`: a read by a
    class gives an item of a subclass as that subclass"""
    from pangloss_models import ModelRegistry

    named = payload.get("type") if isinstance(payload, dict) else None
    found = ModelRegistry._model_dict.get(named) if named else None
    return found if found is not None and issubclass(found, cls) else cls


def got(cls: type, response: Any) -> Any:
    """`cls.HeadView` (or that of the subclass the item is), or None if there is no such item"""
    if response.status_code == 404:
        return None
    check(response)
    payload = response.json()
    refuse_merged_into_other_class(cls, payload)
    return class_of_answer(cls, payload).HeadView.model_validate(payload)  # type: ignore[attr-defined]


def refuse_merged_into_other_class(cls: type, payload: Any) -> None:
    """An entity that was merged is answered with its survivor, which may be of a wider class than the one asked
    for: that is not a `cls`, and is said, with the reference to it"""
    from pangloss_models import ModelRegistry

    merged_from = (payload.get("meta") or {}).get("mergedFrom")
    if not merged_from:
        return
    found = ModelRegistry._model_dict.get(payload.get("type"))
    if found is not None and issubclass(found, cls):
        return
    raise PanglossMergedIntoOtherClass(
        f"{cls.__name__} {merged_from[0]} was merged into {payload.get('type')} {payload.get('id')} "
        f"({payload.get('label')}), which is not a {cls.__name__}",
        reference={key: payload.get(key) for key in ("id", "type", "label")},
    )


def get_for_edit(cls: type, id: Any) -> Call:
    return Call("GET", f"{item_path(cls, id)}/edit", needs_login=True)


def got_for_edit(cls: type, response: Any) -> Any:
    if response.status_code == 404:
        return None
    check(response)
    payload = response.json()
    return class_of_answer(cls, payload).EditView.model_validate(payload)  # type: ignore[attr-defined]


def list_items(
    cls: type,
    search_terms: str | None = None,
    page_number: int | None = None,
    page_size: int | None = None,
    deep_search: bool = False,
    published: bool | None = None,
    review_status: str | None = None,
    used_only: bool = False,
    use_counts: bool = False,
) -> Call:
    params: dict[str, Any] = {}
    if used_only:
        params["used_only"] = "true"
    if use_counts:
        params["use_counts"] = "true"
    if search_terms is not None:
        params["q"] = search_terms
    if page_number is not None:
        params["page"] = page_number
    if page_size is not None:
        params["page_size"] = page_size
    if deep_search:
        params["deep"] = "true"
    if published is not None:
        params["published"] = "true" if published else "false"
    if review_status is not None:
        params["review_status"] = review_status
    return Call("GET", f"/api/{cls.__name__}", params=params)


def listed(cls: type, response: Any) -> Any:
    check(response)
    data = response.json()
    reference_views = [t.ReferenceView for t in get_concrete_types(cls)]  # type: ignore[attr-defined]
    adapter = TypeAdapter(list[Union[*reference_views]])  # type: ignore[valid-type]
    results = adapter.validate_python(data["results"])
    return _ListItems.model_validate({**data, "results": results})


def search(
    cls: type,
    match: Match,
    page_number: int | None = None,
    page_size: int | None = None,
    used_only: bool = False,
    use_counts: bool = False,
) -> Call:
    """The pattern is checked against the models here, as the database module would check it, so that a
    pattern that cannot be made raises `PanglossSearchError` before it is sent. (The class called on is
    its `type` if it has none.)"""
    check_match(cls, match)
    if not match.type:
        match = match.model_copy(update={"type": cls.__name__})
    body = match.model_dump(by_alias=True, exclude_unset=True, mode="json")
    if page_number is not None:
        body["page"] = page_number
    if page_size is not None:
        body["page_size"] = page_size
    if used_only:
        body["used_only"] = True
    if use_counts:
        body["use_counts"] = True
    return Call("POST", "/api/search", json=body)


def searched(cls: type, response: Any) -> Any:
    return listed(cls, response)


def autocomplete(
    search_terms: str,
    types: list[type],
    page_number: int | None = None,
    page_size: int | None = None,
) -> Call:
    params: dict[str, Any] = {"q": search_terms, "type": [t.__name__ for t in types]}
    if page_number is not None:
        params["page"] = page_number
    if page_size is not None:
        params["page_size"] = page_size
    return Call("GET", "/api/autocomplete", params=params)


def autocompleted(response: Any) -> Any:
    check(response)
    return AutocompleteResults.model_validate(response.json())


def search_everything(
    search_terms: str,
    labels: list[str] | None,
    page_number: int | None = None,
    page_size: int | None = None,
) -> Call:
    params: dict[str, Any] = {"q": search_terms}
    if labels:
        params["type"] = labels
    if page_number is not None:
        params["page"] = page_number
    if page_size is not None:
        params["page_size"] = page_size
    return Call("GET", "/api/search-everything", params=params)


def references(ids: list[UUID]) -> Call:
    return Call("POST", "/api/references", json={"ids": [str(id) for id in ids]})


def referenced(response: Any) -> list[AutocompleteItem]:
    check(response)
    return [AutocompleteItem.model_validate(item) for item in response.json()["found"]]


def snake_keys(row: dict[str, Any]) -> dict[str, Any]:
    return {to_snake(key): value for key, value in row.items()}


def write_params(
    detail: bool, published: bool | None, review_status: str | None
) -> dict[str, str] | None:
    """The query of a create or update: `detail`, and the review status asked for (with `pangloss-review`:
    `published=True` is `checked`, see `hooks.review_status_asked`)"""
    params = {"detail": "true"} if detail else {}
    asked = hooks.review_status_asked(published, review_status)
    if asked is not None:
        params["review_status"] = asked
    return params or None


def creator_params(
    created_by: Iterable[str] | str | None, toolchain: ToolchainRun | str | None
) -> dict[str, Any]:
    """The query of a create that names who made the item (an admin's: `pangloss_models.creators`)"""
    creators = creators_asked(created_by, toolchain)
    if creators is None:
        return {}
    params: dict[str, Any] = {}
    people = [creator.username for creator in creators if creator.kind == "user"]
    if people:
        params["created_by"] = people
    for creator in creators:
        if creator.kind == "toolchain":
            params["toolchain"] = creator.username
            if creator.version is not None:
                params["toolchain_version"] = creator.version
            if creator.date is not None:
                params["toolchain_date"] = creator.date.isoformat()
    return params


def create(
    instance: Any,
    detail: bool = False,
    published: bool | None = None,
    review_status: str | None = None,
    created_by: Iterable[str] | str | None = None,
    toolchain: ToolchainRun | str | None = None,
    review_assigned_to: str | None = None,
) -> Call:
    owner = instance._owner
    params = {
        **(write_params(detail, published, review_status) or {}),
        **creator_params(created_by, toolchain),
    }
    if review_assigned_to is not None:
        # (with `pangloss-review`: who is to review the new document)
        params["review_assigned_to"] = review_assigned_to
    return Call(
        "POST",
        f"/api/{owner.__name__}",
        params=params or None,
        json=instance.model_dump(mode="json", by_alias=True),
        needs_login=True,
    )


def create_with_companions(
    instance: Any,
    companions: dict[str, dict[str, Any]],
    detail: bool = False,
    **options: Any,
) -> Call:
    """`POST /api/NAME/with-companions` (implementation_docs/companion-documents.md)"""
    owner = instance._owner
    params = {
        **(write_params(detail, None, None) or {}),
        **creator_params(options.get("created_by"), options.get("toolchain")),
    }
    return Call(
        "POST",
        f"/api/{owner.__name__}/with-companions",
        params=params or None,
        json={
            "item": instance.model_dump(mode="json", by_alias=True),
            "companions": [
                {"name": name, "document": document}
                for name, document in companions.items()
            ],
        },
        needs_login=True,
    )


def created_with_companions(
    instance: Any, response: Any, detail: bool = False
) -> tuple[Any, list[Any]]:
    from pangloss_models import ModelRegistry

    check(response)
    owner = instance._owner
    answer = response.json()
    item = (owner.HeadView if detail else owner.ReferenceView).model_validate(
        answer["item"]
    )
    companions = []
    for made in answer["companions"]:
        model = ModelRegistry.all_models()[made["type"]]
        companions.append(
            (model.HeadView if detail else model.ReferenceView).model_validate(made)
        )
    return item, companions


def created(instance: Any, response: Any, detail: bool = False) -> Any:
    check(response)
    owner = instance._owner
    view = owner.HeadView if detail else owner.ReferenceView
    return view.model_validate(response.json())


def update(
    instance: Any,
    detail: bool = False,
    expected_version: int | None = None,
    published: bool | None = None,
    review_status: str | None = None,
    acknowledge_citations: Any = None,
) -> Call:
    owner = instance._owner
    # (without a version, whatever the version is: as the database module does)
    if_match = "*" if expected_version is None else f'"{expected_version}"'
    return Call(
        "PUT",
        item_path(owner, instance.id),
        params={
            **(write_params(detail, published, review_status) or {}),
            **acknowledge_params(acknowledge_citations),
        }
        or None,
        json=instance.model_dump(mode="json", by_alias=True),
        headers={"If-Match": if_match},
        needs_login=True,
    )


def updated(instance: Any, response: Any, detail: bool = False) -> Any:
    return created(instance, response, detail)


def acknowledge_params(acknowledge_citations: Any = None) -> dict[str, str]:
    """`?acknowledge_citations=` of an update or a delete: what was given, or what the block the call is in says
    (`pangloss_models.citations.acknowledging`)"""
    from pangloss_models.citations import acknowledged

    asked = acknowledge_citations or acknowledged.get()
    if not asked:
        return {}
    return {"acknowledge_citations": "changes" if asked is True else str(asked)}


def delete(cls: type, id: Any, acknowledge_citations: Any = None) -> Call:
    return Call(
        "DELETE",
        item_path(cls, id),
        params=acknowledge_params(acknowledge_citations) or None,
        needs_login=True,
    )


def cited_by(cls: type, id: Any) -> Call:
    return Call("GET", f"{item_path(cls, id)}/cited")


def cited_by_rows(response: Any) -> list[dict[str, Any]]:
    check(response)
    return [
        {to_snake(key): value for key, value in row.items()} for row in response.json()
    ]


def undelete(cls: type, id: Any) -> Call:
    return Call("POST", f"{item_path(cls, id)}/undelete", needs_login=True)


def done(response: Any) -> None:
    check(response)


def server_version() -> Call:
    """Which SDK the server has built (open to anyone)"""
    return Call("GET", "/api/sdk/version")


# --- merging entities -----------------------------------------------------------------


def merge_body(
    absorb: Any,
    values: Any = None,
    as_class: type | None = None,
    version_into: int | None = None,
    version_absorb: int | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    from pydantic_core import to_jsonable_python

    body: dict[str, Any] = {"absorb": str(absorb)}
    if values is not None:
        body["values"] = (
            values.model_dump(mode="json", by_alias=True)
            if hasattr(values, "model_dump")
            else to_jsonable_python(values)
        )
        if as_class is None and hasattr(values, "_owner"):
            as_class = values._owner
    if as_class is not None:
        body["asClass"] = as_class.__name__
    if version_into is not None:
        body["versionInto"] = version_into
    if version_absorb is not None:
        body["versionAbsorb"] = version_absorb
    if note is not None:
        body["note"] = note
    return body


def merge(cls: type, into: Any, body: dict[str, Any], step: str = "merge") -> Call:
    """`step`: `merge`, `merge/preview` or `merge/propose`"""
    return Call("POST", f"{item_path(cls, into)}/{step}", json=body, needs_login=True)


def merges_of(cls: type, id: Any) -> Call:
    return Call("GET", f"{item_path(cls, id)}/merges", needs_login=True)


def a_merge(merge_id: Any, step: str | None = None, body: dict | None = None) -> Call:
    """A merge by its id: read (no `step`), or `verify`, `reject`, `undo`, `undo/propose`, `undo/reject`"""
    if step is None:
        return Call("GET", f"/api/merges/{merge_id}", needs_login=True)
    return Call(
        "POST", f"/api/merges/{merge_id}/{step}", json=body or {}, needs_login=True
    )


def list_merges(
    states: list[str] | None, undo_proposed: bool, skip: int, limit: int
) -> Call:
    params: dict[str, Any] = {"page": skip // limit + 1, "page_size": limit}
    states = list(states or [])
    if undo_proposed:
        # (the server's `open`: those proposed, and those proposed to be undone)
        states = [state for state in states if state != "proposed"]
        params["open"] = "true"
    if states:
        params["state"] = states
    return Call("GET", "/api/merges", params=params, needs_login=True)


def merge_answer(kind: Any, response: Any) -> Any:
    """What a merge route answered, as the result the database module gives (a dataclass of
    `pangloss_models.merging`)"""
    from pangloss_models.merging import from_wire

    check(response)
    return from_wire(kind, response.json())


def merge_records(response: Any, key: str = "merges") -> list[Any]:
    from pangloss_models.merging import MergeRecord, from_wire

    check(response)
    return [from_wire(MergeRecord, item) for item in response.json()[key]]
