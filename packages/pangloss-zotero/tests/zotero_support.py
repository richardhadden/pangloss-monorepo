"""A Zotero that is a dict, and a store that is a dict: what the sync needs to be tried with no network or database"""

import json
from typing import Any
from uuid import uuid7

import httpx2 as httpx
from pangloss_zotero.client import ZoteroClient
from pangloss_zotero.convert import item_url
from pangloss_zotero.sync import Existing, LibraryState

LIBRARY = "groups/1"


def make_item(
    key: str,
    item_type: str = "book",
    title: str | None = None,
    creators: list[dict] | None = None,
    **data: Any,
) -> dict[str, Any]:
    return {
        "key": key,
        "version": 0,
        "data": {
            "key": key,
            "itemType": item_type,
            "title": title or f"Title of {key}",
            "creators": creators
            if creators is not None
            else [{"creatorType": "author", "firstName": "Anne", "lastName": "Smith"}],
            "date": "1742",
            **data,
        },
        "citation": f"<span>(Smith, {key})</span>",
        "bib": f'<div class="csl-bib-body"><div class="csl-entry">Smith, Anne. <i>{key}</i>. 1742.</div></div>',
        "csljson": {"id": key, "type": item_type, "title": title or key},
    }


class FakeZotero:
    """The part of Zotero's API that the client uses, over `httpx` mock transport"""

    def __init__(self) -> None:
        self.version = 0
        self.items: dict[str, dict[str, Any]] = {}
        self.deleted: list[tuple[int, str]] = []  # (version, key)
        self.requests: list[httpx.Request] = []
        self.script: list[httpx.Response] = []  # answers given first, in order
        self.fail_items: set[str] = set()

    def put(self, item: dict[str, Any]) -> dict[str, Any]:
        self.version += 1
        item = {
            **item,
            "version": self.version,
            "data": {**item["data"], "version": self.version},
        }
        self.items[item["key"]] = item
        return item

    def trash(self, key: str) -> None:
        item = self.items[key]
        self.put({**item, "data": {**item["data"], "deleted": 1}})

    def remove(self, key: str) -> None:
        self.version += 1
        del self.items[key]
        self.deleted.append((self.version, key))

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.script:
            return self.script.pop(0)
        if request.headers.get("Zotero-API-Key") != "key":
            return httpx.Response(403)
        headers = {"Last-Modified-Version": str(self.version)}
        params = request.url.params
        path = request.url.path
        since = int(params.get("since", 0))
        held = int(request.headers.get("If-Modified-Since-Version", 0))
        if held and held == self.version:
            return httpx.Response(304, headers=headers)
        if path.endswith("/items/top"):
            changed = {
                k: v["version"] for k, v in self.items.items() if v["version"] > since
            }
            return httpx.Response(200, json=changed, headers=headers)
        if path.endswith("/items"):
            keys = params["itemKey"].split(",")
            return httpx.Response(
                200,
                json=[self.items[k] for k in keys if k in self.items],
                headers=headers,
            )
        if path.endswith("/deleted"):
            keys = [k for v, k in self.deleted if v > since]
            return httpx.Response(
                200, json={"items": keys, "collections": []}, headers=headers
            )
        return httpx.Response(404)

    def client(self, sleep=None, key: str = "key") -> ZoteroClient:
        http = httpx.AsyncClient(
            transport=httpx.MockTransport(self.handler), headers={"Zotero-API-Key": key}
        )
        slept: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            slept.append(seconds)

        client = ZoteroClient(
            key, "https://zotero.test", http=http, sleep=sleep or fake_sleep
        )
        client.slept = slept  # type: ignore[attr-defined]
        return client


class MemoryStore:
    """A `Store` that is a dict, for the sync's tests"""

    def __init__(self) -> None:
        self.states: dict[str, LibraryState] = {}
        self.nodes: dict[
            str, dict[str, Any]
        ] = {}  # url -> fields (+ "_id", "_model", "_version", "_deleted")
        self.referenced: set[str] = set()
        self.writes: list[tuple[str, str]] = []
        self.fail_for: set[str] = set()

    async def library_state(self, library: str) -> LibraryState:
        state = self.states.get(library, LibraryState())
        return LibraryState(state.synced_version, state.last_sync, state.last_error)

    async def save_library_state(self, library: str, state: LibraryState) -> None:
        self.states[library] = state

    async def find(self, url: str) -> Existing | None:
        node = self.nodes.get(url)
        if node is None:
            return None
        restored = node["_deleted"]
        node["_deleted"] = False
        return Existing(
            id=node["_id"],
            model=node["_model"],
            version=node["_version"],
            zotero_version=node.get("zotero_version"),
            synced_entity_version=node.get("zotero_synced_entity_version"),
            removed_from_zotero=bool(node.get("removed_from_zotero")),
            referenced=url in self.referenced,
            restored=restored,
        )

    def _write(self, url: str) -> None:
        if url in self.fail_for:
            raise RuntimeError("the database said no")

    async def create(self, model: str, fields: dict[str, Any]) -> None:
        url = fields["zotero_url"]
        self._write(url)
        self.nodes[url] = {
            **fields,
            "_id": uuid7(),
            "_model": model,
            "_version": 1,
            "_deleted": False,
            "zotero_synced_entity_version": 1,
        }
        self.writes.append(("create", url))

    async def update(self, existing: Existing, fields: dict[str, Any]) -> None:
        url = next(u for u, n in self.nodes.items() if n["_id"] == existing.id)
        self._write(url)
        node = self.nodes[url]
        node.update(fields)
        node["_version"] += 1
        node["zotero_synced_entity_version"] = node["_version"]
        self.writes.append(("update", url))

    async def delete(self, existing: Existing) -> None:
        url = next(u for u, n in self.nodes.items() if n["_id"] == existing.id)
        self.nodes[url]["_deleted"] = True
        self.writes.append(("delete", url))

    # (what a person does)
    def person_edits(self, key: str) -> None:
        self.nodes[item_url(LIBRARY, key)]["_version"] += 1

    def person_deletes(self, key: str) -> None:
        self.nodes[item_url(LIBRARY, key)]["_deleted"] = True


def body_of(response: httpx.Response) -> Any:
    return json.loads(response.content)
