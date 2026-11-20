"""`pangloss_criteria.preview(...)`, `candidates(...)`, `broken(...)`, `settled(...)` and `resolve(...)` from Python, wherever the models
are used: on the server (a backend that runs Cypher) they are the functions of `reading`, the worker and `resolving`;
with the SDK they ask the
server's API (`/api/criteria/...`), `async` or blocking as the SDK was connected, and give the same answers. As
`pangloss_derived.access` does.

(Nothing of the server is imported at module level: a client of the SDK imports this package with the models)
"""

import asyncio
import datetime
import time
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from pangloss_models import PanglossSearchError
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# -- the answers ------------------------------------------------------------------------------------------------------


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Candidate(_Camel):
    """An entity a description finds, as a chip shows it"""

    type: str
    id: UUID
    label: str | None = None


class Preview(_Camel):
    """What criteria would find, as a logged-in reader sees it"""

    count: int
    """How many they find"""
    candidates: list[Candidate]
    """The first of them by label (five: `reading.PREVIEWED`)"""
    too_broad: bool
    """They find more than a description links (`CRITERIA_MAX_CANDIDATES`)"""


class SharedDescription(_Camel):
    """A shared description a mention cites"""

    id: UUID
    label: str | None = None
    criteria: dict[str, Any] | None = None
    """`{type, where}`; None if it is not there (or deleted)"""


class CandidatesPage(_Camel):
    """A page of the candidates of a saved description, as its reader may see them"""

    count: int
    """How many its criteria find, of what the reader sees (as `candidateCount` of the read)"""
    too_broad: bool
    """They find more than are linked: those past the cap are not listed"""
    pending: bool
    """Its document has been written since the worker last worked it: the result may change"""
    evaluated_when: datetime.datetime | None
    broken: str | None
    """Why it is no longer evaluated (its criteria no longer fit the models)"""
    broken_since: str | None = None
    """`app.name` of the migration that made its criteria wrong (None if the worker found them so)"""
    page: int
    page_size: int
    candidates: list[Candidate]
    """The linked candidates the reader sees, by label"""
    criteria: dict[str, Any] | None = None
    """What it is evaluated by, `{type, where}`: its own criteria, or for a place with none of its own (`same_one`)
    those of the place of its mark in its document that holds them. None if no place does"""
    places: int = 1
    """How many places of its document describe the same one (share its mark): 1 if it has no mark"""
    shared: SharedDescription | None = None
    """The shared description it cites (or, for a place with none of its own, the place of its mark that holds
    them cites), if one: `criteria` above are then the conditions it adds to those"""


class Reference(_Camel):
    """An item, by its type and id (and its label, where it is known)"""

    type: str
    id: UUID
    label: str | None = None


class SharedListed(_Camel):
    """A shared description in a list: with how many mentions the reader may see cite it"""

    id: UUID
    label: str | None = None
    criteria: dict[str, Any] | None = None
    """`{type, where}`"""
    mentions: int = 0


class SharedPage(_Camel):
    """A page of shared descriptions, by label"""

    count: int
    page: int
    page_size: int
    results: list[SharedListed]


class Mention(_Camel):
    """A mention that cites a shared description"""

    id: UUID
    """Of its `MatchesCriteria`"""
    wording: str | None = None
    criteria: dict[str, Any] | None = None
    """Its own criteria, beside the shared ones (`{type, where}`), or None"""
    head: Reference
    """The document (or entity) it is in"""


class MentionsPage(_Camel):
    """A page of the mentions that cite a shared description, by the label of their document"""

    count: int
    page: int
    page_size: int
    results: list[Mention]


class Similar(_Camel):
    """The mentions of other documents with exactly the same criteria, and citing the same shared description"""

    count: int
    """How many mentions"""
    documents: list[Reference]
    """The first of their documents, by label (`reading.SIMILAR_SHOWN`)"""


class ShareFailed(_Camel):
    """A document `share` did not update, and why"""

    head: Reference
    detail: str


class ShareResult(_Camel):
    """What `share` did: the shared description made, how many documents now cite it, and those it could not
    update"""

    description: Reference
    updated: int
    failed: list[ShareFailed]


class BrokenDescription(_Camel):
    """A description whose criteria no longer fit the models"""

    id: UUID
    """Of its `MatchesCriteria`"""
    wording: str | None = None
    criteria: dict[str, Any] | None = None
    """`{type, where}`, as they are stored"""
    broken: str
    """Why: where in the criteria, and what is wrong"""
    broken_since: str | None = None
    """`app.name` of the migration that made them wrong (None if the worker found them so)"""
    head: Reference
    """The document (or entity) it is in"""


class BrokenPage(_Camel):
    """A page of the descriptions that are broken, by the label of their document"""

    count: int
    page: int
    page_size: int
    results: list[BrokenDescription]


class Resolved(_Camel):
    """A description resolved: the document it was in, written again with the entity in its place"""

    head: Reference
    """The head document (or entity) the description was in"""
    entity: Reference
    """What took its place"""
    version: int
    """The version of the head that this write made"""


def storage_kind() -> str:
    """`cypher` (the server), `api` (the SDK) or `api_sync` (the blocking SDK)"""
    from pangloss_core import storage_of

    storage = storage_of()
    if storage.capabilities.cypher:
        return "cypher"
    return "api_sync" if storage.package.endswith("api_sync") else "api"


# -- the API ----------------------------------------------------------------------------------------------------------


def preview_call(
    criteria: Any, named: Iterable[UUID | str], description: UUID | str | None = None
) -> Any:
    from pangloss_sdk.protocol import Call

    from pangloss_criteria.pattern import SearchPattern

    body: dict[str, Any] = {
        "criteria": None if criteria is None else SearchPattern(criteria).data,
        "named": [str(id) for id in named],
    }
    if description is not None:
        body["description"] = str(description)
    return Call("POST", "/api/criteria/preview", json=body, needs_login=True)


def shared_call(
    types: Iterable[str] | None, q: str | None, page: int, page_size: int
) -> Any:
    from pangloss_sdk.protocol import Call

    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if types:
        params["types"] = ",".join(types)
    if q:
        params["q"] = q
    return Call("GET", "/api/criteria/shared", params=params)


def mentions_call(id: UUID | str, page: int, page_size: int) -> Any:
    from pangloss_sdk.protocol import Call

    return Call(
        "GET",
        f"/api/criteria/shared/{id}/mentions",
        params={"page": page, "page_size": page_size},
    )


def similar_call(
    type: str | None,
    where: Any,
    description: UUID | str | None,
    except_: UUID | str | None,
) -> Any:
    from pangloss_sdk.protocol import Call

    return Call(
        "POST",
        "/api/criteria/similar",
        json={
            "type": type,
            "where": where or {},
            "description": None if description is None else str(description),
            "except": None if except_ is None else str(except_),
        },
        needs_login=True,
    )


def share_call(label: str, pattern: Any, except_: UUID | str | None = None) -> Any:
    from pangloss_sdk.protocol import Call

    from pangloss_criteria.pattern import SearchPattern

    data = SearchPattern(pattern).data
    return Call(
        "POST",
        "/api/criteria/share",
        json={
            "label": label,
            "type": data["type"],
            "where": data["where"],
            "except": None if except_ is None else str(except_),
        },
        needs_login=True,
    )


def share_from(response: Any) -> "ShareResult":
    """The answer of a share; what the server refused is raised as there"""
    from pangloss_sdk.protocol import body_of, check

    body = body_of(response)
    if response.status_code == 422 and body.get("error") == "PanglossSearchError":
        raise PanglossSearchError(str(body.get("detail")))
    check(response)
    return ShareResult.model_validate(response.json())


def candidates_call(id: UUID | str, page: int, page_size: int) -> Any:
    from pangloss_sdk.protocol import Call

    return Call(
        "GET",
        f"/api/criteria/{id}/candidates",
        params={"page": page, "page_size": page_size},
    )


def broken_call(page: int, page_size: int) -> Any:
    from pangloss_sdk.protocol import Call

    return Call(
        "GET",
        "/api/criteria/broken",
        params={"page": page, "page_size": page_size},
        needs_login=True,
    )


def settled_call(head_id: Any) -> Any:
    from pangloss_sdk.protocol import Call

    return Call("GET", f"/api/criteria/settled/{head_id}", needs_login=True)


def entity_of(entity: Any) -> Reference:
    """An entity as it may be given: `{"type": ..., "id": ...}`, or anything with a `type` and an `id` (a read of
    one, its `ReferenceView`)"""
    if isinstance(entity, Reference):
        return entity
    if isinstance(entity, dict):
        return Reference.model_validate(entity)
    return Reference(type=entity.type, id=entity.id)


def resolve_call(id: UUID | str, entity: Reference, version: int | None) -> Any:
    from pangloss_sdk.protocol import Call

    body: dict[str, Any] = {"entity": {"type": entity.type, "id": str(entity.id)}}
    if version is not None:
        body["version"] = version
    return Call("POST", f"/api/criteria/{id}/resolve", json=body, needs_login=True)


def resolved_from(response: Any) -> Resolved:
    """The answer of a resolve; what the server refused is raised as there (`PanglossNotFoundError` for a 404,
    `PanglossVersionConflictError`, `PanglossWriteRefused`, ...)"""
    from pangloss_sdk.protocol import check

    check(response)
    return Resolved.model_validate(response.json())


def answer(response: Any) -> Any:
    """The JSON of a response; None for a 404. Criteria the server refuses are a `PanglossSearchError`, as there"""
    from pangloss_sdk.protocol import body_of, check

    if response.status_code == 404:
        return None
    body = body_of(response)
    if response.status_code == 422 and body.get("error") == "PanglossSearchError":
        raise PanglossSearchError(str(body.get("detail")))
    check(response)
    return response.json()


def preview_from(data: Any) -> Preview:
    return Preview.model_validate(data)


def page_from(data: Any) -> CandidatesPage | None:
    return None if data is None else CandidatesPage.model_validate(data)


def broken_from(data: Any) -> BrokenPage:
    return BrokenPage.model_validate(data)


def settled_from(head_id: Any, data: Any) -> bool:
    if data is None:
        raise PanglossSearchError(f"There is no head {head_id}")
    return bool(data["settled"])


def timed_out(head_id: Any, timeout: float) -> TimeoutError:
    return TimeoutError(
        f"The descriptions of {head_id} were not evaluated in {timeout} s: is the criteria worker running?"
    )


# -- async: the server, or the SDK ------------------------------------------------------------------------------------


async def preview_async(
    criteria: Any,
    named: Iterable[UUID | str] = (),
    description: UUID | str | None = None,
) -> Preview:
    if storage_kind() == "api":
        from pangloss_sdk.client import current_async_client

        response = await current_async_client().send(
            preview_call(criteria, named, description)
        )
        return preview_from(answer(response))
    from pangloss_criteria import reading

    return await reading.preview(criteria, named, description)


async def shared_async(
    types: Iterable[str] | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> SharedPage:
    if storage_kind() == "api":
        from pangloss_sdk.client import current_async_client

        response = await current_async_client().send(
            shared_call(types, q, page, page_size)
        )
        return SharedPage.model_validate(answer(response))
    from pangloss_criteria import reading

    return await reading.shared_descriptions(types, q, page, page_size)


async def shared_mentions_async(
    id: UUID | str, page: int = 1, page_size: int = 25
) -> MentionsPage | None:
    if storage_kind() == "api":
        from pangloss_sdk.client import current_async_client

        response = await current_async_client().send(mentions_call(id, page, page_size))
        data = answer(response)
        return None if data is None else MentionsPage.model_validate(data)
    from pangloss_criteria import reading

    return await reading.shared_mentions(id, page, page_size)


async def similar_async(
    type: str | None,
    where: Any = None,
    description: UUID | str | None = None,
    except_: UUID | str | None = None,
) -> Similar:
    if storage_kind() == "api":
        from pangloss_sdk.client import current_async_client

        response = await current_async_client().send(
            similar_call(type, where, description, except_)
        )
        return Similar.model_validate(answer(response))
    from pangloss_criteria import reading

    return await reading.similar(type, where, description, except_)


async def share_async(
    label: str, pattern: Any, except_: UUID | str | None = None
) -> ShareResult:
    if storage_kind() == "api":
        from pangloss_sdk.client import current_async_client

        return share_from(
            await current_async_client().send(share_call(label, pattern, except_))
        )
    from pangloss_criteria import sharing

    return await sharing.share(label, pattern, except_)


async def candidates_async(
    id: UUID | str, page: int = 1, page_size: int = 25
) -> CandidatesPage | None:
    if storage_kind() == "api":
        from pangloss_sdk.client import current_async_client

        response = await current_async_client().send(
            candidates_call(id, page, page_size)
        )
        return page_from(answer(response))
    from pangloss_criteria import reading

    return await reading.candidates(id, page, page_size)


async def broken_async(page: int = 1, page_size: int = 25) -> BrokenPage:
    if storage_kind() == "api":
        from pangloss_sdk.client import current_async_client

        response = await current_async_client().send(broken_call(page, page_size))
        return broken_from(answer(response))
    from pangloss_criteria import reading

    return await reading.broken(page, page_size)


async def settled_async(
    head_id: Any, timeout: float = 10.0, poll: float = 0.02
) -> None:
    if storage_kind() == "api":
        from pangloss_sdk.client import current_async_client

        deadline = time.monotonic() + timeout
        while not settled_from(
            head_id,
            answer(await current_async_client().send(settled_call(head_id))),
        ):
            if time.monotonic() >= deadline:
                raise timed_out(head_id, timeout)
            await asyncio.sleep(poll)
        return
    from pangloss_criteria import worker

    await worker.settled(head_id, timeout, poll)


async def resolve_async(
    id: UUID | str, entity: Any, version: int | None = None
) -> Resolved:
    if storage_kind() == "api":
        from pangloss_sdk.client import current_async_client

        response = await current_async_client().send(
            resolve_call(id, entity_of(entity), version)
        )
        return resolved_from(response)
    from pangloss_criteria import resolving

    return await resolving.resolve(id, entity_of(entity), version)


# -- blocking: the SDK connected with `sync=True` ---------------------------------------------------------------------


def preview_sync(
    criteria: Any,
    named: Iterable[UUID | str] = (),
    description: UUID | str | None = None,
) -> Preview:
    from pangloss_sdk.client import current_client

    return preview_from(
        answer(current_client().send(preview_call(criteria, named, description)))
    )


def shared_sync(
    types: Iterable[str] | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> SharedPage:
    from pangloss_sdk.client import current_client

    return SharedPage.model_validate(
        answer(current_client().send(shared_call(types, q, page, page_size)))
    )


def shared_mentions_sync(
    id: UUID | str, page: int = 1, page_size: int = 25
) -> MentionsPage | None:
    from pangloss_sdk.client import current_client

    data = answer(current_client().send(mentions_call(id, page, page_size)))
    return None if data is None else MentionsPage.model_validate(data)


def similar_sync(
    type: str | None,
    where: Any = None,
    description: UUID | str | None = None,
    except_: UUID | str | None = None,
) -> Similar:
    from pangloss_sdk.client import current_client

    return Similar.model_validate(
        answer(current_client().send(similar_call(type, where, description, except_)))
    )


def share_sync(
    label: str, pattern: Any, except_: UUID | str | None = None
) -> ShareResult:
    from pangloss_sdk.client import current_client

    return share_from(current_client().send(share_call(label, pattern, except_)))


def candidates_sync(
    id: UUID | str, page: int = 1, page_size: int = 25
) -> CandidatesPage | None:
    from pangloss_sdk.client import current_client

    return page_from(
        answer(current_client().send(candidates_call(id, page, page_size)))
    )


def broken_sync(page: int = 1, page_size: int = 25) -> BrokenPage:
    from pangloss_sdk.client import current_client

    return broken_from(answer(current_client().send(broken_call(page, page_size))))


def settled_sync(head_id: Any, timeout: float = 10.0, poll: float = 0.02) -> None:
    from pangloss_sdk.client import current_client

    deadline = time.monotonic() + timeout
    while not settled_from(
        head_id, answer(current_client().send(settled_call(head_id)))
    ):
        if time.monotonic() >= deadline:
            raise timed_out(head_id, timeout)
        time.sleep(poll)


def resolve_sync(id: UUID | str, entity: Any, version: int | None = None) -> Resolved:
    from pangloss_sdk.client import current_client

    return resolved_from(
        current_client().send(resolve_call(id, entity_of(entity), version))
    )


# -- what the package gives ---------------------------------------------------------------------------------------------


def preview(
    criteria: Any,
    named: Iterable[UUID | str] = (),
    description: UUID | str | None = None,
) -> Any:
    """What criteria would find if a description with them were saved now: `Preview` (`count`, the first five
    `candidates` by label, `too_broad`). `named`: the ids of the entities the document being edited names, which
    are never candidates. `description`: the id of a shared description it cites, whose criteria are evaluated with
    these (which may then be none). A coroutine, or with the blocking SDK the answer. Raises `PanglossSearchError`
    for criteria a description could not store. Over the API it needs a login"""
    if storage_kind() == "api_sync":
        return preview_sync(criteria, named, description)
    return preview_async(criteria, named, description)


def shared(
    types: Iterable[str] | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> Any:
    """A page of the shared descriptions (`Description`) the reader may see, by label: of one of the classes named
    in `types` or one below (all, without), whose label holds `q`, each with how many mentions cite it:
    `SharedPage`. A coroutine, or with the blocking SDK the answer"""
    if storage_kind() == "api_sync":
        return shared_sync(types, q, page, page_size)
    return shared_async(types, q, page, page_size)


def shared_mentions(id: UUID | str, page: int = 1, page_size: int = 25) -> Any:
    """A page of the mentions that cite a shared description, by the label of their document, in the documents the
    reader may see: `MentionsPage`, or None if there is no such shared description. A coroutine, or with the
    blocking SDK the answer"""
    if storage_kind() == "api_sync":
        return shared_mentions_sync(id, page, page_size)
    return shared_mentions_async(id, page, page_size)


def similar(
    type: str | None,
    where: Any = None,
    description: UUID | str | None = None,
    except_: UUID | str | None = None,
) -> Any:
    """How many mentions in other documents (not `except_`, the id of a head) have exactly these criteria of their
    own (`type`, `where`) and cite the same shared description (`description`, or none), and the first of their
    documents: `Similar`. A coroutine, or with the blocking SDK the answer. Over the API it needs a login"""
    if storage_kind() == "api_sync":
        return similar_sync(type, where, description, except_)
    return similar_async(type, where, description, except_)


def share(label: str, pattern: Any, except_: UUID | str | None = None) -> Any:
    """Make criteria a shared description: a `Description` of that label with the criteria (`pattern`: `{type,
    where}`, a `Where` or a `SearchPattern`), and every document holding mentions whose own criteria are exactly
    these and that cite nothing updated (by the user, as any edit) to cite it instead. A document that cannot be
    updated is left, and said (`failed`). Raises `PanglossSearchError` for criteria that could not be stored, or if
    more documents than `sharing.MAX_DOCUMENTS` would be touched. Gives `ShareResult`. A coroutine, or with the
    blocking SDK the answer. Over the API it needs a login"""
    if storage_kind() == "api_sync":
        return share_sync(label, pattern, except_)
    return share_async(label, pattern, except_)


def candidates(id: UUID | str, page: int = 1, page_size: int = 25) -> Any:
    """A page of the linked candidates of a saved description (the id of its `MatchesCriteria`), by label, as the
    reader sees them: `CandidatesPage`, or None if there is no such description the reader may see. A coroutine, or
    with the blocking SDK the answer"""
    if storage_kind() == "api_sync":
        return candidates_sync(id, page, page_size)
    return candidates_async(id, page, page_size)


def broken(page: int = 1, page_size: int = 25) -> Any:
    """A page of the descriptions whose criteria no longer fit the models (a migration made them wrong, or the worker
    found them so), in the documents the reader may see, by the label of their document: `BrokenPage`. A coroutine,
    or with the blocking SDK the answer. Over the API it needs a login"""
    if storage_kind() == "api_sync":
        return broken_sync(page, page_size)
    return broken_async(page, page_size)


def settled(head_id: Any, timeout: float = 10.0, poll: float = 0.02) -> Any:
    """Wait until the mark a save left on a head is completed: the descriptions in it have their first result since
    that save. `save()` returns before the candidates are there; a script or a test that reads them waits with this.
    Raises `TimeoutError` if the worker has not done it in `timeout` seconds (it may not be running). A coroutine, or
    with the blocking SDK it waits. Over the API it needs a login"""
    if storage_kind() == "api_sync":
        return settled_sync(head_id, timeout, poll)
    return settled_async(head_id, timeout, poll)


def resolve(id: UUID | str, entity: Any, version: int | None = None) -> Any:
    """Resolving, "This is…": the entity takes the place of the description `id` (the id of its `MatchesCriteria`) in its
    document, which is written again as an update (a new version, by the user: the description stays in its history).
    `entity` is `{"type": ..., "id": ...}` or a read of one; it need not be a candidate, but it must be what the field
    takes (`PanglossWriteRefused` if not). `version`: the version of the document the choice was made on
    (`PanglossVersionConflictError` if it has changed since); without it, the version read now. Gives `Resolved`.
    `PanglossNotFoundError` if there is no description of the id that the reader may see. A coroutine, or with the
    blocking SDK the answer. Over the API it needs a login"""
    if storage_kind() == "api_sync":
        return resolve_sync(id, entity, version)
    return resolve_async(id, entity, version)
