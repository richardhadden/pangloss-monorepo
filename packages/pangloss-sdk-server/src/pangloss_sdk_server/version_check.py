"""Telling a client whether its SDK is the server's, and refusing its writes if its schema is
not.

A client sends `X-Pangloss-SDK` (the fingerprint of its package) and `X-Pangloss-Schema` (a hash
of the migrations it was built at). The answer has `X-Pangloss-SDK-Status`: `current`, `stale`
(a different package, the same schema: allowed) or `schema-changed`. With `SDK_STALE_WRITES =
"refuse"` (the default) a write from a client whose schema has changed is refused with 409
(`PanglossSdkOutOfDate`) before it reaches a route: it may lack a field that is now required, or
have a value that no longer exists. A read never is."""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pangloss_sdk_server import config, current

HEADER = b"x-pangloss-sdk-status"
READS = {"GET", "HEAD", "OPTIONS"}
# (not the models: a login must be possible, and the SDK itself is how to catch up)
NOT_MODELS = ("/api/users", "/api/sdk")


def status_of(fingerprint: str | None, schema: str | None) -> str | None:
    serving = current.current()
    if serving is None or fingerprint is None:
        return None
    if schema is not None and schema != serving.schema_hash:
        return "schema-changed"
    return "current" if fingerprint == serving.fingerprint else "stale"


class SdkVersionMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return

        headers = {k: v for k, v in scope["headers"]}
        fingerprint = headers.get(b"x-pangloss-sdk", b"").decode() or None
        schema = headers.get(b"x-pangloss-schema", b"").decode() or None
        status = status_of(fingerprint, schema)
        if status is None:
            await self.app(scope, receive, send)
            return

        is_write = scope["method"] not in READS and not scope["path"].startswith(
            NOT_MODELS
        )
        if (
            status == "schema-changed"
            and is_write
            and config.setting("SDK_STALE_WRITES", "refuse") == "refuse"
        ):
            body = json.dumps(
                {
                    "detail": "The models of this SDK are not the server's (its schema has "
                    "moved on): update the SDK, then write again",
                    "error": "PanglossSdkOutOfDate",
                }
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 409,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        (HEADER, status.encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        async def send_with_status(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    (HEADER, status.encode()),
                ]
            await send(message)

        await self.app(scope, receive, send_with_status)
