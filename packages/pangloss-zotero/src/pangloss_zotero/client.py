"""Talking to Zotero's web API (https://www.zotero.org/support/dev/web_api/v3/start).

Only what the sync needs: the versions of what changed since a version, the items for some keys, and what was
deleted since a version. Zotero asks that a client sends its key and API version, sends the version it has
(`If-Modified-Since-Version`), and waits when it says so (`Backoff`, `Retry-After`)."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Self

import httpx2 as httpx

from pangloss_zotero import config

logger = logging.getLogger("pangloss.zotero.client")

API_VERSION = "3"
MAX_ATTEMPTS = 5
MAX_WAIT = 300.0


class ZoteroError(Exception):
    pass


class ZoteroAuthError(ZoteroError):
    """The key is wrong, or cannot read the library (not tried again)"""


class ZoteroClient:
    def __init__(
        self,
        api_key: str | None,
        base_url: str = config.DEFAULT_API_URL,
        *,
        http: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        headers = {"Zotero-API-Version": API_VERSION}
        if api_key:
            headers["Zotero-API-Key"] = api_key
        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.AsyncClient(headers=headers, timeout=30.0)
        self._own_http = http is None
        self.sleep = sleep
        self._backoff_until = 0.0

    async def close(self) -> None:
        if self._own_http:
            await self.http.aclose()

    async def __aenter__(self) -> ZoteroClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def request(
        self, path: str, params: dict[str, Any] | None = None, since: int | None = None
    ) -> httpx.Response:
        """A GET, waiting as Zotero says. `since` is sent as the version already held: `304` then means
        nothing has changed."""
        headers = {}
        if since:
            headers["If-Modified-Since-Version"] = str(since)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            loop = asyncio.get_running_loop()
            if self._backoff_until > loop.time():
                await self.sleep(self._backoff_until - loop.time())
            try:
                response = await self.http.get(
                    f"{self.base_url}{path}", params=params, headers=headers
                )
            except httpx.TransportError as error:
                if attempt == MAX_ATTEMPTS:
                    raise ZoteroError(
                        f"Zotero could not be reached: {error}"
                    ) from error
                await self.sleep(min(2.0**attempt, MAX_WAIT))
                continue
            if backoff := response.headers.get("Backoff"):
                self._backoff_until = loop.time() + min(float(backoff), MAX_WAIT)
            if response.status_code in (401, 403):
                raise ZoteroAuthError(
                    f"Zotero refused the key for {path} ({response.status_code})"
                )
            if response.status_code in (429, 503):
                wait = min(
                    float(response.headers.get("Retry-After", 2.0**attempt)), MAX_WAIT
                )
                logger.warning(
                    "Zotero said to wait %.0f s (%s)", wait, response.status_code
                )
                if attempt == MAX_ATTEMPTS:
                    raise ZoteroError(f"Zotero is busy ({response.status_code})")
                await self.sleep(wait)
                continue
            if response.status_code == 304:
                return response
            if response.status_code >= 400:
                raise ZoteroError(f"Zotero answered {response.status_code} for {path}")
            return response
        raise ZoteroError("unreachable")  # pragma: no cover

    async def item_versions(
        self, library: str, since: int = 0
    ) -> tuple[dict[str, int], int]:
        """({key: version} of the top-level items changed since `since`, trashed ones too; the library's
        version now). Nothing changed: ({}, `since`)"""
        response = await self.request(
            f"/{library}/items/top",
            {"format": "versions", "since": since, "includeTrashed": 1},
            since=since,
        )
        if response.status_code == 304:
            return {}, since
        version = int(response.headers.get("Last-Modified-Version", since))
        return {k: int(v) for k, v in response.json().items()}, version

    async def library_version(self, library: str) -> int:
        """The version the library is at now"""
        response = await self.request(
            f"/{library}/items/top", {"format": "versions", "limit": 1, "since": 2**62}
        )
        return int(response.headers.get("Last-Modified-Version", 0))

    async def items(self, library: str, keys: list[str]) -> list[dict[str, Any]]:
        """The items for up to 50 keys, with their formatted citation and bibliography and CSL JSON"""
        if len(keys) > config.BATCH_SIZE:
            raise ValueError(f"at most {config.BATCH_SIZE} keys at a time")
        response = await self.request(
            f"/{library}/items",
            {
                "itemKey": ",".join(keys),
                "format": "json",
                "include": "data,citation,bib,csljson",
                "includeTrashed": 1,
                "limit": config.BATCH_SIZE,
            },
        )
        return response.json()

    async def deleted_items(self, library: str, since: int) -> list[str]:
        """The keys of the items deleted for good since a version"""
        response = await self.request(
            f"/{library}/deleted", {"since": since}, since=since
        )
        if response.status_code == 304:
            return []
        return list(response.json().get("items", []))

    async def item(self, library: str, key: str) -> dict[str, Any] | None:
        found = await self.items(library, [key])
        return found[0] if found else None
