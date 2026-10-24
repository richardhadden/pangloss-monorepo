"""A request id for each request, and a line in the log of how it went.

The id is the `X-Request-ID` the client sent (if it is short and plain), or one made here; it
is put on every log record made while the request is dealt with (`pangloss_core.logs.request_id`)
and sent back in `X-Request-ID`. A request is logged when it is done, at DEBUG, or at WARNING if
it took longer than `SLOW_REQUEST_MS`. The query string is not logged (it can hold search terms).
"""

import logging
import re
import time
import uuid

from pangloss_core import settings as core_settings
from pangloss_core.logs import request_id
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("pangloss.api.requests")

PLAIN_ID = re.compile(r"^[\w.-]{1,64}$")


def slow_request_ms() -> int:
    settings = core_settings.__dict__.get("SETTINGS")
    return getattr(settings, "SLOW_REQUEST_MS", 2000)


class RequestLogger:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        sent = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        identifier = sent if PLAIN_ID.match(sent) else uuid.uuid4().hex
        token = request_id.set(identifier)
        status = 0
        started = time.monotonic()

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = identifier
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            elapsed = (time.monotonic() - started) * 1000
            level = logging.WARNING if elapsed > slow_request_ms() else logging.DEBUG
            logger.log(
                level,
                "%s %s -> %s in %.0f ms%s",
                scope["method"],
                scope["path"],
                status or "(no response)",
                elapsed,
                " (slow)" if level == logging.WARNING else "",
            )
            request_id.reset(token)
