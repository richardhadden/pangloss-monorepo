"""The clients: send a `Call`, logging in and renewing the token as needed.

There are two, the same in what they do: `AsyncClient` (for the async database module)
and `Client` (blocking). One of them is made for the process by `connect()` and found by
the database module.
"""

import asyncio
import threading
import time
import warnings
from typing import Any

import httpx2 as httpx
from pangloss_core import settings as core_settings

from pangloss_sdk import protocol
from pangloss_sdk.auth import LOGIN_PATH, REFRESH_PATH, Prompt, Session
from pangloss_sdk.exceptions import (
    PanglossAuthenticationError,
    PanglossConnectionError,
    PanglossNotConnected,
    PanglossSdkOutOfDateWarning,
)
from pangloss_sdk.schemas import schema_hash
from pangloss_sdk.protocol import Call
from pangloss_sdk.settings import SdkSettings

BACKOFF_SECONDS = 0.2


def client_arguments(settings: SdkSettings) -> dict[str, Any]:
    return dict(
        base_url=str(settings.URL),
        timeout=settings.TIMEOUT,
        verify=settings.VERIFY_TLS,
        limits=httpx.Limits(max_connections=settings.MAX_CONNECTIONS),
    )


def sdk_headers(sdk: dict[str, Any] | None) -> dict[str, str]:
    """What tells the server which SDK this is (from the manifest of the generated SDK)"""
    if not sdk:
        return {}
    return {
        "X-Pangloss-SDK": sdk["fingerprint"],
        "X-Pangloss-Schema": schema_hash(sdk.get("schema_position", {})),
    }


def request_arguments(call: Call, session: Session, sdk: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(
        method=call.method,
        url=call.path,
        params=call.params,
        json=call.json,
        headers={**sdk_headers(sdk), **session.headers(), **(call.headers or {})},
    )


class Observer:
    """Says once that the SDK is out of date, when the server says so"""

    def __init__(self) -> None:
        self.status: str | None = None
        self._warned = False

    def observe(self, response: Any) -> None:
        status = response.headers.get("x-pangloss-sdk-status")
        if status is None:
            return
        self.status = status
        if status != "current" and not self._warned:
            self._warned = True
            warnings.warn(
                "The server's models are not those of this SDK "
                f"({status}): update it (`pip install -U` the SDK, or `git pull`)",
                PanglossSdkOutOfDateWarning,
                stacklevel=4,
            )


def connection_error(error: Exception, session: Session) -> PanglossConnectionError:
    return PanglossConnectionError(f"Could not reach {session.url}: {error}")


class AsyncClient:
    def __init__(
        self,
        settings: SdkSettings,
        transport: httpx.AsyncBaseTransport | None = None,
        prompt: Prompt | None = None,
        sdk: dict[str, Any] | None = None,
    ) -> None:
        self.sdk = sdk
        self.observer = Observer()
        self.settings = settings
        self.session = Session(settings, prompt)
        self.transport = transport
        self._http: httpx.AsyncClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = asyncio.Lock()

    def http(self) -> httpx.AsyncClient:
        # (a connection pool belongs to the event loop that made it: a script that runs
        # `asyncio.run` more than once gets a new one)
        loop = asyncio.get_running_loop()
        if self._http is None or self._loop is not loop:
            self._http = httpx.AsyncClient(
                transport=self.transport, **client_arguments(self.settings)
            )
            self._loop = loop
        return self._http

    async def close(self) -> None:
        if self._http is not None and self._loop is asyncio.get_running_loop():
            await self._http.aclose()
        self._http = None

    async def _once(self, call: Call) -> httpx.Response:
        attempts = 1 + (self.settings.READ_RETRIES if call.is_read else 0)
        for attempt in range(attempts):
            try:
                response = await self.http().request(
                    **request_arguments(call, self.session, self.sdk)
                )
                self.observer.observe(response)
                return response
            except httpx.TransportError as error:
                if attempt + 1 == attempts:
                    raise connection_error(error, self.session) from error
                await asyncio.sleep(BACKOFF_SECONDS * 2**attempt)
        raise AssertionError("unreachable")

    async def _login(self) -> None:
        while True:
            form = self.session.login_form()
            try:
                response = await self.http().post(LOGIN_PATH, data=form)
            except httpx.TransportError as error:
                raise connection_error(error, self.session) from error
            if response.status_code == 200:
                self.session.accept(response.json())
                return
            if response.status_code != 401:
                raise protocol.error_for(response)
            # (wrong: credentials() asks again, or says it cannot)

    async def _refresh(self) -> bool:
        if not self.session.refresh_token:
            return False
        try:
            response = await self.http().post(
                REFRESH_PATH, json={"refresh_token": self.session.refresh_token}
            )
        except httpx.TransportError as error:
            raise connection_error(error, self.session) from error
        if response.status_code != 200:
            return False
        self.session.accept(response.json())
        return True

    async def _renew(self, used: str | None, call: Call) -> bool:
        """The token that was refused is renewed (once, if several requests are refused
        together). False: read again without one"""
        async with self._lock:
            if self.session.access_token != used:
                return True
            if await self._refresh():
                return True
            self.session.forget()
            if call.needs_login:
                await self._login()
                return True
            return False

    async def send(self, call: Call) -> httpx.Response:
        if call.needs_login and not self.session.access_token:
            async with self._lock:
                if not self.session.access_token and not await self._refresh():
                    await self._login()

        used = self.session.access_token
        response = await self._once(call)
        if response.status_code == 401 and used is not None:
            await self._renew(used, call)
            response = await self._once(call)
        elif response.status_code == 401 and call.needs_login:
            raise PanglossAuthenticationError(protocol.message_of(
                response, protocol.body_of(response)))
        return response


class Client:
    """The same, blocking"""

    def __init__(
        self,
        settings: SdkSettings,
        transport: httpx.BaseTransport | None = None,
        prompt: Prompt | None = None,
        sdk: dict[str, Any] | None = None,
    ) -> None:
        self.sdk = sdk
        self.observer = Observer()
        self.settings = settings
        self.session = Session(settings, prompt)
        self.transport = transport
        self._http: httpx.Client | None = None
        self._lock = threading.Lock()

    def http(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(
                transport=self.transport, **client_arguments(self.settings)
            )
        return self._http

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
        self._http = None

    def _once(self, call: Call) -> httpx.Response:
        attempts = 1 + (self.settings.READ_RETRIES if call.is_read else 0)
        for attempt in range(attempts):
            try:
                response = self.http().request(
                    **request_arguments(call, self.session, self.sdk)
                )
                self.observer.observe(response)
                return response
            except httpx.TransportError as error:
                if attempt + 1 == attempts:
                    raise connection_error(error, self.session) from error
                time.sleep(BACKOFF_SECONDS * 2**attempt)
        raise AssertionError("unreachable")

    def _login(self) -> None:
        while True:
            form = self.session.login_form()
            try:
                response = self.http().post(LOGIN_PATH, data=form)
            except httpx.TransportError as error:
                raise connection_error(error, self.session) from error
            if response.status_code == 200:
                self.session.accept(response.json())
                return
            if response.status_code != 401:
                raise protocol.error_for(response)

    def _refresh(self) -> bool:
        if not self.session.refresh_token:
            return False
        try:
            response = self.http().post(
                REFRESH_PATH, json={"refresh_token": self.session.refresh_token}
            )
        except httpx.TransportError as error:
            raise connection_error(error, self.session) from error
        if response.status_code != 200:
            return False
        self.session.accept(response.json())
        return True

    def _renew(self, used: str | None, call: Call) -> bool:
        with self._lock:
            if self.session.access_token != used:
                return True
            if self._refresh():
                return True
            self.session.forget()
            if call.needs_login:
                self._login()
                return True
            return False

    def send(self, call: Call) -> httpx.Response:
        if call.needs_login and not self.session.access_token:
            with self._lock:
                if not self.session.access_token and not self._refresh():
                    self._login()

        used = self.session.access_token
        response = self._once(call)
        if response.status_code == 401 and used is not None:
            self._renew(used, call)
            response = self._once(call)
        elif response.status_code == 401 and call.needs_login:
            raise PanglossAuthenticationError(
                protocol.message_of(response, protocol.body_of(response))
            )
        return response


# The client of the process, set by `connect()`
_async_client: AsyncClient | None = None
_client: Client | None = None


def install(client: AsyncClient | Client | None) -> None:
    global _async_client, _client
    _async_client = client if isinstance(client, AsyncClient) else None
    _client = client if isinstance(client, Client) else None


def current_async_client() -> AsyncClient:
    if _async_client is None:
        raise PanglossNotConnected("Not connected: call pangloss_sdk.connect(url) first")
    return _async_client


def current_client() -> Client:
    if _client is None:
        raise PanglossNotConnected("Not connected: call pangloss_sdk.connect(url) first")
    return _client


def settings() -> SdkSettings:
    current = core_settings.SETTINGS
    if not isinstance(current, SdkSettings):
        raise PanglossNotConnected("Not connected: call pangloss_sdk.connect(url) first")
    return current
