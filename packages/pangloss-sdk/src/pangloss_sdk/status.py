"""Is this SDK the server's? (`GET /api/sdk/version`, which anyone may ask)"""

import warnings
from typing import Any

from pangloss_sdk import protocol
from pangloss_sdk.client import AsyncClient, Client, current_async_client, current_client
from pangloss_sdk.exceptions import (
    PanglossSdkMismatch,
    PanglossSdkOutOfDateWarning,
)
from pangloss_sdk.schemas import schema_hash


def judge(client: AsyncClient | Client, response: Any) -> dict[str, Any]:
    """What the server answered, set against this SDK's manifest (raises if the server has
    no SDK or another project's; warns if it is not the same one)"""
    if response.status_code in (404, 503):
        raise PanglossSdkMismatch(
            "The server has no SDK built"
            + (f": {response.json().get('detail')}" if response.status_code == 503 else "")
        )
    protocol.check(response)
    server = response.json()
    local = client.sdk
    result: dict[str, Any] = {
        "url": client.session.url,
        "logged_in_as": client.session.username if client.session.access_token else None,
        "server": server,
        "local": local,
        "current": None,
    }
    if local is None:
        return result
    if server["project"] != local["project"]:
        raise PanglossSdkMismatch(
            f"This is the SDK of '{local['project']}', and the server is '{server['project']}'"
        )
    same_schema = server["schemaHash"] == schema_hash(local.get("schema_position", {}))
    result["current"] = same_schema and server["fingerprint"] == local["fingerprint"]
    result["same_schema"] = same_schema
    if not result["current"]:
        warnings.warn(
            "The server's models are not those of this SDK"
            + ("" if same_schema else " (its schema has moved on)")
            + ": update it",
            PanglossSdkOutOfDateWarning,
            stacklevel=3,
        )
    return result


async def check() -> dict[str, Any]:
    """Compare this SDK with the server's (async client)"""
    client = current_async_client()
    return judge(client, await client.send(protocol.server_version()))


def check_sync() -> dict[str, Any]:
    client = current_client()
    return judge(client, client.send(protocol.server_version()))
