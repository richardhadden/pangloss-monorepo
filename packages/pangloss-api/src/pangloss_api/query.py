"""Query parameters: in either case, and only those a route has.

The JSON of the API is camelCase and a request may be in either case; so may the names of its query parameters
(`?pageSize=100` is `?page_size=100`): `QueryNames` rewrites them before the request is routed. And a parameter a
route does not have is refused (422) with the names it has: left alone, a misspelt `?pagesize=100` gave the first
50 with no word of why.

An entity can be read at one of its URLs (`GET /api/Person/http://example.com/people?id=5`), and the query string
is then the URL's: nothing in it is renamed or refused (so the route's own `incoming_limit` is in snake_case there).

A route that reads other parameters from the request itself (a field of a class given as a parameter) is marked
`@checks_own_parameters` and calls `refuse_unknown_parameters(request, also=...)` with what it reads.
"""

import re
from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import parse_qsl, urlencode

from fastapi import Request
from fastapi.dependencies.models import Dependant
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel
from starlette.types import ASGIApp, Receive, Scope, Send

CAPITAL = re.compile(r"(?<=[a-z0-9])([A-Z])")
# (a URL as the last part of the path: a server may have merged the slashes of "http://")
URL_IN_PATH = re.compile(r"/https?:/", re.IGNORECASE)
CHECKS_ITS_OWN = "_pangloss_checks_own_parameters"
DECLARED = "_pangloss_query_parameters"


def to_snake(name: str) -> str:
    return CAPITAL.sub(lambda found: "_" + found.group(1).lower(), name)


def query_is_of_a_url(path: str) -> bool:
    return URL_IN_PATH.search(path) is not None


def in_snake_case(query_string: bytes) -> bytes:
    """The query string with its names in snake_case (the same object if they all are)"""
    if not any(65 <= byte <= 90 for byte in query_string):
        return query_string
    pairs = parse_qsl(query_string.decode("latin-1"), keep_blank_values=True)
    renamed = [(to_snake(name), value) for name, value in pairs]
    if renamed == pairs:
        return query_string
    return urlencode(renamed).encode("latin-1")


class QueryNames:
    """`?pageSize=` is read as `?page_size=`: only the names are changed, never a value"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope.get("query_string")
            and not query_is_of_a_url(scope["path"])
        ):
            scope["query_string"] = in_snake_case(scope["query_string"])
        await self.app(scope, receive, send)


def checks_own_parameters[F: Callable[..., Any]](endpoint: F) -> F:
    """The route reads parameters it does not declare, and refuses the ones it does not know itself
    (`refuse_unknown_parameters`)"""
    setattr(endpoint, CHECKS_ITS_OWN, True)
    return endpoint


def names_in(dependant: Dependant) -> set[str]:
    names: set[str] = set()
    for field in dependant.query_params:
        annotation = field.field_info.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            # (a model as the parameters: its fields are the names)
            names.update(
                info.alias or name for name, info in annotation.model_fields.items()
            )
        else:
            names.add(getattr(field, "validation_alias", None) or field.alias)
    for inner in dependant.dependencies:
        names |= names_in(inner)
    return names


def declared_parameters(route: APIRoute) -> frozenset[str]:
    """The names of the query parameters of the route and of everything it depends on (worked out once, and kept
    on the route)"""
    found = getattr(route, DECLARED, None)
    if found is None:
        found = frozenset(names_in(route.dependant))
        setattr(route, DECLARED, found)
    return found


def refuse_unknown_parameters(request: Request, also: Iterable[str] = ()) -> None:
    route = request.scope.get("route")
    if not isinstance(route, APIRoute) or query_is_of_a_url(request.url.path):
        return
    known = declared_parameters(route) | set(also)
    unknown = [
        name for name in dict.fromkeys(request.query_params) if name not in known
    ]
    if not unknown:
        return
    has = ", ".join(sorted(known)) or "none"
    raise RequestValidationError(
        [
            {
                "type": "unknown_parameter",
                "loc": ("query", name),
                "msg": f"Unknown query parameter '{name}'. This route has: {has}",
                "input": request.query_params[name],
            }
            for name in unknown
        ]
    )


async def known_parameters(request: Request) -> None:
    """A dependency of every route: a query parameter the route does not have is a 422"""
    route = request.scope.get("route")
    if getattr(getattr(route, "endpoint", None), CHECKS_ITS_OWN, False):
        return
    refuse_unknown_parameters(request)
