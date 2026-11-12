"""Merging entities through the API (`pangloss_api.routes.merges`): who may, what is answered, and what a read or a
write of a merged entity says"""

from typing import no_type_check
from uuid import uuid7

import httpx2 as httpx
import pytest
import pytest_asyncio
from pangloss_api import create_app
from pangloss_core import settings as core_settings
from pangloss_users import service

from .merge_support import declare, make, merged_into, person, ref

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"


@pytest_asyncio.fixture(loop_scope="session")
async def api(clear_database):
    """Makes the app for the models declared, and gives a client of it and the headers of three users: `root` (an
    admin), `ann` and `bob`"""
    clients = []

    async def start():
        await service.create_user("root", "root@example.com", PASSWORD, admin=True)
        for name in ("ann", "bob"):
            await service.create_user(name, f"{name}@example.com", PASSWORD)
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
        )
        clients.append(client)
        headers = {}
        for name in ("root", "ann", "bob"):
            token = (
                await client.post(
                    "/api/users/token", data={"username": name, "password": PASSWORD}
                )
            ).json()["access_token"]
            headers[name] = {"Authorization": f"Bearer {token}"}
        return client, headers

    yield start
    for client in clients:
        await client.aclose()


@pytest.fixture
def merge_directly(monkeypatch):
    def set_to(who: str) -> None:
        monkeypatch.setattr(core_settings.SETTINGS, "MERGE_DIRECTLY", who)

    return set_to


@no_type_check
async def test_an_admin_merges_and_undoes_through_the_api(db_driver, api):
    m = declare()
    client, users = await api()
    a = await person(m, "John Smith", born=1800)
    b = await person(m, "Jon Smyth", died=1870)
    mention = await make(m.Mention, "Of B", of=ref(b))

    preview = await client.post(
        f"/api/Person/{a.id}/merge/preview",
        json={"absorb": str(b.id)},
        headers=users["root"],
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["possible"] is True and body["refused"] == []
    assert body["heads"] == 1 and body["survivorType"] == "Person"
    assert body["referToAbsorbed"] == {"Mention": 1}
    # the fields the survivor would have, with the keys of the API
    assert body["values"]["died"] == 1870 and body["values"]["aliases"] == ["Jon Smyth"]
    assert merged_into(db_driver, b.id) is None

    merged = await client.post(
        f"/api/Person/{a.id}/merge",
        json={
            "absorb": str(b.id),
            "values": {**body["values"], "label": "John Smith (Jon Smyth)"},
            "versionInto": 1,
            "versionAbsorb": 1,
        },
        headers=users["root"],
    )
    assert merged.status_code == 200, merged.text
    result = merged.json()
    assert result["merge"]["state"] == "done" and result["merge"]["by"] == "root"
    assert result["merge"]["survivor"] == str(a.id)
    assert (result["merge"]["heads"], result["merge"]["moved"]) == (1, 1)
    assert result["collapsed"] == [] and result["kept"] == 0
    merge_id = result["merge"]["id"]
    assert (await m.Person.get(a.id)).label == "John Smith (Jon Smyth)"
    assert (await m.Mention.get(mention.id)).of.id == a.id

    listed = await client.get(f"/api/Person/{b.id}/merges", headers=users["root"])
    assert [x["id"] for x in listed.json()["merges"]] == [merge_id]
    one = await client.get(f"/api/merges/{merge_id}", headers=users["root"])
    assert one.json()["absorbedLabel"] == "Jon Smyth"

    dry = await client.post(
        f"/api/merges/{merge_id}/undo", json={"dryRun": True}, headers=users["root"]
    )
    assert dry.status_code == 200 and dry.json()["restored"] == 1
    assert merged_into(db_driver, b.id) == str(a.id)
    undone = await client.post(f"/api/merges/{merge_id}/undo", headers=users["root"])
    assert undone.status_code == 200, undone.text
    assert undone.json()["merge"]["state"] == "undone"
    assert undone.json()["fieldsRestored"] is True
    assert merged_into(db_driver, b.id) is None
    assert (await m.Person.get(a.id)).label == "John Smith"
    assert (await m.Mention.get(mention.id)).of.id == b.id


@no_type_check
async def test_reading_a_merged_entity_gives_the_survivor_and_says_where_it_is(
    db_driver, api
):
    m = declare()
    client, users = await api()
    a = await person(m, "A")
    b = await make(m.Poet, "B", works=["Odes"])
    await m.Person.merge(absorb=b.id, into=a.id, as_class=m.Person)

    # (decision 27: by the class it was, the survivor as the class it is)
    read = await client.get(f"/api/Poet/{b.id}")
    assert read.status_code == 200, read.text
    body = read.json()
    assert (body["id"], body["type"]) == (str(a.id), "Person")
    assert body["meta"]["mergedFrom"] == [str(b.id)]
    assert read.headers["Content-Location"] == f"/api/Person/{a.id}"
    # the survivor itself says nothing of the kind
    own = await client.get(f"/api/Person/{a.id}")
    assert "Content-Location" not in own.headers
    assert not own.json()["meta"].get("mergedFrom")


@no_type_check
async def test_a_write_to_a_merged_entity_is_a_conflict_that_names_the_survivor(
    db_driver, api
):
    m = declare()
    client, users = await api()
    a, b = await person(m, "A"), await person(m, "B")
    edit = (await client.get(f"/api/Person/{b.id}/edit", headers=users["ann"])).json()
    await m.Person.merge(absorb=b.id, into=a.id)

    update = await client.put(
        f"/api/Person/{b.id}",
        json={**{k: v for k, v in edit.items() if k != "meta"}, "label": "B again"},
        headers={**users["ann"], "If-Match": '"1"'},
    )
    assert update.status_code == 409, update.text
    assert update.json()["error"] == "PanglossMergedError"
    assert update.json()["mergedInto"] == str(a.id)
    delete = await client.delete(f"/api/Person/{b.id}", headers=users["ann"])
    assert delete.status_code == 409 and delete.json()["mergedInto"] == str(a.id)
    undelete = await client.post(f"/api/Person/{b.id}/undelete", headers=users["ann"])
    assert undelete.status_code == 409


@no_type_check
async def test_a_write_that_names_a_merged_entity_says_what_it_was_written_as(
    db_driver, api
):
    m = declare()
    client, users = await api()
    a, b, c = await person(m, "A"), await person(m, "B"), await person(m, "C")
    await m.Person.merge(absorb=b.id, into=a.id)

    created = await client.post(
        "/api/Mention",
        json={
            "label": "Of B",
            "of": {"type": "Person", "id": str(b.id)},
            "others": [{"type": "Person", "id": str(c.id)}],
        },
        headers=users["ann"],
    )
    assert created.status_code == 201, created.text
    assert created.headers["Pangloss-Resolved-References"] == f"{b.id}={a.id}"
    mention = await m.Mention.get(created.json()["id"])
    assert mention.of.id == a.id

    edit = (
        await client.get(f"/api/Mention/{mention.id}/edit", headers=users["ann"])
    ).json()
    edit["others"] = [{"type": "Person", "id": str(b.id)}]
    updated = await client.put(
        f"/api/Mention/{mention.id}",
        json={k: v for k, v in edit.items() if k != "meta"},
        headers={**users["ann"], "If-Match": '"1"'},
    )
    assert updated.status_code == 200, updated.text
    assert updated.headers["Pangloss-Resolved-References"] == f"{b.id}={a.id}"
    # and one that names none says nothing
    plain = await client.post(
        "/api/Mention",
        json={"label": "Of C", "of": {"type": "Person", "id": str(c.id)}, "others": []},
        headers=users["ann"],
    )
    assert "Pangloss-Resolved-References" not in plain.headers


@no_type_check
async def test_who_may_merge_without_anyone_else_is_the_projects_choice(
    db_driver, api, merge_directly
):
    m = declare()
    client, users = await api()
    a, b, c, d = [await person(m, name) for name in "ABCD"]
    body = {"absorb": str(b.id)}

    # the default: admins
    assert (
        await client.get("/api/merges/permissions", headers=users["ann"])
    ).json() == {"direct": False, "large": False, "limit": 1000}
    assert (
        await client.get("/api/merges/permissions", headers=users["root"])
    ).json() == {"direct": True, "large": True, "limit": 1000}
    refused = await client.post(
        f"/api/Person/{a.id}/merge", json=body, headers=users["ann"]
    )
    assert refused.status_code == 403 and "propose" in refused.json()["detail"]
    assert merged_into(db_driver, b.id) is None
    # (and not at all without a login)
    for path in ("merge", "merge/preview", "merge/propose"):
        assert (
            await client.post(f"/api/Person/{a.id}/{path}", json=body)
        ).status_code == 401
    assert (await client.get(f"/api/Person/{a.id}/merges")).status_code == 401
    assert (await client.get("/api/merges")).status_code == 401

    merge_directly("any")
    done = await client.post(
        f"/api/Person/{a.id}/merge", json=body, headers=users["ann"]
    )
    assert done.status_code == 200, done.text
    assert done.json()["merge"]["by"] == "ann"

    merge_directly("none")
    refused = await client.post(
        f"/api/Person/{c.id}/merge", json={"absorb": str(d.id)}, headers=users["root"]
    )
    assert refused.status_code == 403
    assert (await client.get("/api/merges/permissions", headers=users["root"])).json()[
        "direct"
    ] is False
    # an undo follows the same rule: nobody has proposed this one
    undo = await client.post(
        f"/api/merges/{done.json()['merge']['id']}/undo", headers=users["root"]
    )
    assert undo.status_code == 403, undo.text
    assert undo.json()["error"] == "PanglossMergeNotAllowedError"
    assert merged_into(db_driver, b.id) == str(a.id)


@no_type_check
async def test_one_user_proposes_and_another_verifies_through_the_api(db_driver, api):
    m = declare()
    client, users = await api()
    a = await person(m, "John Smith")
    b = await person(m, "Jon Smyth")
    mention = await make(m.Mention, "Of B", of=ref(b))

    proposed = await client.post(
        f"/api/Person/{a.id}/merge/propose",
        json={"absorb": str(b.id), "note": "one man"},
        headers=users["ann"],
    )
    assert proposed.status_code == 201, proposed.text
    proposal = proposed.json()
    assert (proposal["state"], proposal["proposedBy"], proposal["note"]) == (
        "proposed",
        "ann",
        "one man",
    )
    assert proposal["values"]["aliases"] == ["Jon Smyth"]
    assert merged_into(db_driver, b.id) is None

    waiting = (await client.get("/api/merges?open=true", headers=users["bob"])).json()
    assert [x["id"] for x in waiting["results"]] == [proposal["id"]]
    assert (waiting["count"], waiting["page"], waiting["pageSize"]) == (1, 1, 50)

    own = await client.post(
        f"/api/merges/{proposal['id']}/verify", headers=users["ann"]
    )
    assert own.status_code == 403 and "someone other" in own.json()["detail"]
    verified = await client.post(
        f"/api/merges/{proposal['id']}/verify", headers=users["bob"]
    )
    assert verified.status_code == 200, verified.text
    merge = verified.json()["merge"]
    assert (merge["state"], merge["proposedBy"], merge["by"]) == ("done", "ann", "bob")
    assert (await m.Mention.get(mention.id)).of.id == a.id
    again = await client.post(
        f"/api/merges/{proposal['id']}/verify", headers=users["bob"]
    )
    assert again.status_code == 409
    assert (await client.get("/api/merges?open=true", headers=users["bob"])).json()[
        "results"
    ] == []

    # the undoing of it: proposed by one, accepted by the other
    alone = await client.post(f"/api/merges/{merge['id']}/undo", headers=users["bob"])
    assert alone.status_code == 403
    asked = await client.post(
        f"/api/merges/{merge['id']}/undo/propose",
        json={"note": "two men after all"},
        headers=users["bob"],
    )
    assert asked.status_code == 200 and asked.json()["undoProposedBy"] == "bob"
    waiting = (await client.get("/api/merges?open=true", headers=users["ann"])).json()
    assert [x["id"] for x in waiting["results"]] == [merge["id"]]
    own = await client.post(f"/api/merges/{merge['id']}/undo", headers=users["bob"])
    assert own.status_code == 403
    accepted = await client.post(
        f"/api/merges/{merge['id']}/undo", headers=users["ann"]
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["merge"]["undoneBy"] == "ann"
    assert merged_into(db_driver, b.id) is None
    assert (await m.Mention.get(mention.id)).of.id == b.id


@no_type_check
async def test_proposals_are_rejected_through_the_api(db_driver, api):
    m = declare()
    client, users = await api()
    a, b = await person(m, "A"), await person(m, "B")
    proposal = (
        await client.post(
            f"/api/Person/{a.id}/merge/propose",
            json={"absorb": str(b.id)},
            headers=users["ann"],
        )
    ).json()
    rejected = await client.post(
        f"/api/merges/{proposal['id']}/reject",
        json={"reason": "different fathers"},
        headers=users["bob"],
    )
    assert rejected.status_code == 200, rejected.text
    assert (rejected.json()["state"], rejected.json()["reason"]) == (
        "rejected",
        "different fathers",
    )
    listed = (
        await client.get("/api/merges?state=rejected", headers=users["ann"])
    ).json()
    assert [x["id"] for x in listed["results"]] == [proposal["id"]]

    merge = (
        await client.post(
            f"/api/Person/{a.id}/merge",
            json={"absorb": str(b.id)},
            headers=users["root"],
        )
    ).json()["merge"]
    await client.post(f"/api/merges/{merge['id']}/undo/propose", headers=users["ann"])
    kept = await client.post(
        f"/api/merges/{merge['id']}/undo/reject",
        json={"reason": "one man"},
        headers=users["bob"],
    )
    assert kept.status_code == 200 and kept.json()["undoRejectedBy"] == "bob"
    assert merged_into(db_driver, b.id) == str(a.id)


@no_type_check
async def test_what_the_api_answers_when_a_merge_cannot_be_made(
    db_driver, api, monkeypatch
):
    m = declare()
    client, users = await api()
    a, b = await person(m, "A"), await person(m, "B")
    group = await make(m.Group, "A group")
    for index in range(3):
        await make(m.Mention, f"Of B {index}", of=ref(b))
    root = users["root"]

    async def merge(survivor, body, headers=root):
        return await client.post(
            f"/api/Person/{survivor}/merge", json=body, headers=headers
        )

    # not there (nor is a group a person); not to be merged; decided on a version that has passed; a class that is
    # not one
    assert (await merge(a.id, {"absorb": str(uuid7())})).status_code == 404
    assert (await merge(a.id, {"absorb": str(group.id)})).status_code == 404
    itself = await merge(a.id, {"absorb": str(a.id)})
    assert itself.status_code == 409
    assert itself.json()["error"] == "PanglossMergeError"
    stale = await merge(a.id, {"absorb": str(b.id), "versionInto": 7})
    assert stale.status_code == 412 and stale.json()["currentVersion"] == 1
    unknown = await merge(a.id, {"absorb": str(b.id), "asClass": "Nothing"})
    assert unknown.status_code == 422
    assert (await merge(a.id, {"absorb": "b"})).status_code == 422
    # a preview says why, and is not an error
    preview = await client.post(
        f"/api/Person/{a.id}/merge/preview", json={"absorb": str(a.id)}, headers=root
    )
    assert preview.status_code == 200 and preview.json()["possible"] is False
    assert "cannot be merged into itself" in preview.json()["refused"][0]
    # no merge there
    assert (await client.get(f"/api/merges/{uuid7()}", headers=root)).status_code == 404
    assert (
        await client.get("/api/merges?state=finished", headers=root)
    ).status_code == 422

    # over the limit: only an admin, whoever else may merge
    monkeypatch.setattr(core_settings.SETTINGS, "MERGE_LIMIT", 2)
    monkeypatch.setattr(core_settings.SETTINGS, "MERGE_DIRECTLY", "any")
    large = await merge(a.id, {"absorb": str(b.id)}, headers=users["ann"])
    assert large.status_code == 403, large.text
    assert large.json()["error"] == "PanglossMergeTooLargeError"
    assert (large.json()["heads"], large.json()["limit"]) == (3, 2)
    assert merged_into(db_driver, b.id) is None
    done = await merge(a.id, {"absorb": str(b.id)})
    assert done.status_code == 200, done.text
    assert done.json()["merge"]["heads"] == 3
    # what was merged is not merged again
    again = await merge(a.id, {"absorb": str(b.id)})
    assert again.status_code == 409 and "was merged into" in again.json()["detail"]


@no_type_check
async def test_a_merge_does_not_change_what_something_else_keeps_up_to_date(
    db_driver, api
):
    from pangloss_models import Entity, Protection, initialise

    class Source(Entity):
        _protect_meta = Protection(read_only=("synced_title",))
        synced_title: str | None = None
        note: str | None = None

    initialise()
    client, users = await api()
    a = await Source.Create(label="A", synced_title="From outside").save()
    b = await Source.Create(label="B", synced_title="Another", note="mine").save()
    preview = (
        await client.post(
            f"/api/Source/{a.id}/merge/preview",
            json={"absorb": str(b.id)},
            headers=users["root"],
        )
    ).json()
    assert preview["values"]["syncedTitle"] == "From outside"

    for path in ("merge", "merge/propose"):
        refused = await client.post(
            f"/api/Source/{a.id}/{path}",
            json={
                "absorb": str(b.id),
                "values": {**preview["values"], "syncedTitle": "Another"},
            },
            headers=users["root"],
        )
        assert refused.status_code == 403, refused.text
        assert (
            "syncedTitle" in refused.json()["detail"]
            or "synced_title" in (refused.json()["detail"])
        )
    assert merged_into(db_driver, b.id) is None
    done = await client.post(
        f"/api/Source/{a.id}/merge",
        json={"absorb": str(b.id), "values": preview["values"]},
        headers=users["root"],
    )
    assert done.status_code == 200, done.text
    after = await Source.get(a.id)
    assert (after.synced_title, after.note) == ("From outside", "mine")
