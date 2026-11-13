"""Citations through the API and the SDK (`Cites[T]`; implementation_docs/entity-identity.md, part 3): how one is
written and read, what a refused write says, who may override, and that the SDK gives and raises what the database
module does"""

from typing import no_type_check

import pytest
from pangloss_api import create_app
from pangloss_models import PanglossCitedError
from pangloss_models.citations import acknowledging
from pangloss_sdk.databases.api import exposed_functions as sdk

from .test_citations import as_update, cite, models, ref, same_as, world
from .test_merge_api import api  # noqa: F401
from .test_sdk_contract import sdk_for, through_the_api  # noqa: F401

# (each async test is marked: the last, of a command, is not async)


def body_of(view) -> dict:
    return view.model_dump(mode="json", by_alias=True, exclude={"meta"})


@pytest.mark.asyncio(loop_scope="session")
@no_type_check
async def test_a_citation_is_written_and_read_over_the_api(db_driver, api):  # noqa: F811
    m = models()
    client, users = await api()
    w = await world(m)

    made = await client.post(
        "/api/SameAs?detail=true",
        json={
            "type": "SameAs",
            "label": "Ann is Bob",
            "people": [ref_json(w.ann), ref_json(w.bob)],
            # (as a reference to an entity is written)
            "evidence": [{"type": "Birth", "id": str(w.birth.id)}],
        },
        headers=users["ann"],
    )
    assert made.status_code in (200, 201), made.text
    citation = made.json()["evidence"][0]
    assert citation["type"] == "PGCitation"
    assert citation["targetId"] == str(w.birth.id) and citation["targetType"] == "Birth"
    assert citation["targetLabel"] == "Ann is born"
    assert citation["targetHeadId"] == str(w.factoid.id)
    assert citation["targetHeadType"] == "Factoid"
    assert citation["targetState"] == "there" and citation["changedSinceCited"] is False

    # what was read is written back as it is
    again = await client.put(
        f"/api/SameAs/{made.json()['id']}?detail=true",
        json={k: v for k, v in made.json().items() if k != "meta"},
        headers={**users["ann"], "If-Match": '"1"'},
    )
    assert again.status_code == 200, again.text
    assert again.json()["evidence"][0]["id"] == citation["id"]

    cited = await client.get(f"/api/Factoid/{w.factoid.id}/cited")
    assert cited.status_code == 200
    assert cited.json() == [
        {
            "citation": citation["id"],
            "target": str(w.birth.id),
            "targetLabel": "Ann is born",
            "changed": False,
            "id": made.json()["id"],
            "type": "SameAs",
            "label": "Ann is Bob",
            "published": True,
            "hidden": False,
        }
    ]
    # (asked of the part itself, on its own page)
    part = await client.get(f"/api/Birth/{w.birth.id}/cited")
    assert [row["id"] for row in part.json()] == [made.json()["id"]]
    assert (await client.get(f"/api/SameAs/{made.json()['id']}/cited")).json() == []

    # a citation of nothing is a 422
    bad = await client.post(
        "/api/SameAs",
        json={
            "type": "SameAs",
            "label": "x",
            "people": [],
            "evidence": [{"type": "Birth", "id": str(w.ann.id)}],
        },
        headers=users["ann"],
    )
    assert bad.status_code == 422 and "is an entity" in bad.json()["detail"]


def ref_json(entity) -> dict:
    return {"type": "Person", "id": str(entity.id)}


@pytest.mark.asyncio(loop_scope="session")
@no_type_check
async def test_a_change_to_what_is_cited_is_a_409_until_acknowledged(db_driver, api):  # noqa: F811
    m = models()
    client, users = await api()
    w = await world(m)
    citing = await same_as(m, w, w.birth)

    changed = body_of(w.factoid)
    changed["statements"][0]["year"] = 1801
    headers = {**users["ann"], "If-Match": '"1"'}

    refused = await client.put(
        f"/api/Factoid/{w.factoid.id}", json=changed, headers=headers
    )
    assert refused.status_code == 409, refused.text
    body = refused.json()
    assert body["error"] == "PanglossCitedError"
    assert body["removed"] == []
    assert body["changed"] == [
        {
            "target": str(w.birth.id),
            "targetLabel": "Ann is born",
            "id": str(citing.id),
            "type": "SameAs",
            "label": "Ann is Bob",
        }
    ]
    assert "acknowledge_citations" in body["fix"]

    done = await client.put(
        f"/api/Factoid/{w.factoid.id}?acknowledge_citations=changes",
        json=changed,
        headers=headers,
    )
    assert done.status_code == 200, done.text
    read = await client.get(f"/api/SameAs/{citing.id}")
    assert read.json()["evidence"][0]["changedSinceCited"] is True
    by = await client.get(f"/api/Factoid/{w.factoid.id}/cited")
    assert [row["changed"] for row in by.json()] == [True]


@pytest.mark.asyncio(loop_scope="session")
@no_type_check
async def test_only_an_admin_removes_what_is_cited(db_driver, api):  # noqa: F811
    m = models()
    client, users = await api()
    w = await world(m)
    await same_as(m, w, w.birth)

    without = body_of(w.factoid)
    without["statements"] = without["statements"][1:]
    url = f"/api/Factoid/{w.factoid.id}"
    match = {"If-Match": '"1"'}

    for query in ("", "?acknowledge_citations=changes", "?acknowledge_citations=true"):
        refused = await client.put(
            url + query, json=without, headers={**users["ann"], **match}
        )
        assert refused.status_code == 409, refused.text
        assert len(refused.json()["removed"]) == 1 and refused.json()["changed"] == []
    forbidden = await client.put(
        url + "?acknowledge_citations=removals",
        json=without,
        headers={**users["ann"], **match},
    )
    assert forbidden.status_code == 403

    # deleting it: asked first, refused, forbidden to override, and an admin's to do
    deletable = await client.get(url + "/deletable", headers=users["ann"])
    assert deletable.json()["deletable"] is False
    assert "cites this" in deletable.json()["reason"]
    assert (await client.delete(url, headers=users["ann"])).status_code == 409
    assert (
        await client.delete(
            url + "?acknowledge_citations=removals", headers=users["ann"]
        )
    ).status_code == 403

    done = await client.put(
        url + "?acknowledge_citations=removals",
        json=without,
        headers={**users["root"], **match},
    )
    assert done.status_code == 200, done.text
    assert (
        await client.delete(
            url + "?acknowledge_citations=removals", headers=users["root"]
        )
    ).status_code == 204


@pytest.mark.asyncio(loop_scope="session")
@no_type_check
async def test_a_citation_in_an_unpublished_document_is_hidden_from_who_cannot_see_it(
    db_driver,
    api,  # noqa: F811
):
    from .helpers import run

    m = models()
    client, users = await api()
    w = await world(m)
    citing = await same_as(m, w, w.birth)
    run(db_driver, "MATCH (n:SameAs) SET n.published = false")

    anonymous = (await client.get(f"/api/Factoid/{w.factoid.id}/cited")).json()
    assert anonymous == [
        {
            "citation": None,
            "target": str(w.birth.id),
            "targetLabel": "Ann is born",
            "changed": False,
            "id": None,
            "type": None,
            "label": None,
            "published": False,
            "hidden": True,
        }
    ]
    logged_in = (
        await client.get(f"/api/Factoid/{w.factoid.id}/cited", headers=users["ann"])
    ).json()
    assert [(row["id"], row["hidden"]) for row in logged_in] == [
        (str(citing.id), False)
    ]

    # The other way round: a published document that cites an unpublished one says only that
    run(db_driver, "MATCH (n:SameAs) REMOVE n.published")
    run(db_driver, "MATCH (n:Factoid) SET n.published = false")
    seen = (await client.get(f"/api/SameAs/{citing.id}")).json()["evidence"][0]
    assert seen["targetState"] == "hidden"
    assert seen["targetLabel"] is None and seen["targetHeadLabel"] is None
    seen = (await client.get(f"/api/SameAs/{citing.id}", headers=users["ann"])).json()
    assert seen["evidence"][0]["targetState"] == "there"
    assert seen["evidence"][0]["targetLabel"] == "Ann is born"


@pytest.mark.asyncio(loop_scope="session")
@no_type_check
async def test_the_sdk_gives_and_raises_what_the_database_module_does(
    db_driver,
    through_the_api,  # noqa: F811
):
    m = models()
    await through_the_api(create_app())
    w = await world(m)
    citing = await same_as(m, w, w.birth)

    assert await sdk.document_cited_by(
        m.Factoid, w.factoid.id
    ) == await m.Factoid.cited_by(w.factoid.id)

    statements = as_update(m, w.factoid)["statements"]
    statements[0]["year"] = 1801
    update = m.Factoid.Update(**as_update(m, w.factoid, statements=statements))
    with pytest.raises(PanglossCitedError) as refused:
        await sdk.update_head_node(update)
    assert [(r["id"], r["target"]) for r in refused.value.changed] == [
        (str(citing.id), str(w.birth.id))
    ]
    assert refused.value.removed == [] and "acknowledge_citations" in refused.value.fix

    with pytest.raises(PanglossCitedError):
        await sdk.delete_document(m.Factoid, w.factoid.id)

    # acknowledged by the argument, or by the block the call is in
    await sdk.update_head_node(update, acknowledge_citations=True)
    assert (await m.SameAs.get(citing.id)).evidence[0].changed_since_cited
    statements[0]["year"] = 1802
    with acknowledging("changes"):
        await sdk.update_head_node(
            m.Factoid.Update(**as_update(m, w.factoid, statements=statements))
        )
    assert (await m.Factoid.get(w.factoid.id)).statements[0].year == 1802

    made = await sdk.create_head_node(
        m.SameAs.Create(
            label="Another", people=[ref(w.ann)], evidence=[cite(w.naming)]
        ),
        detail=True,
    )
    assert made.evidence[0].target_label == "Not called Anna"
    assert made.evidence[0].target_spaces == ["Negative"]


@no_type_check
def test_check_data_says_which_citations_are_of_what_has_been_removed(
    clear_database, db_driver, command_backend, capsys
):
    """`pangloss check-data` (the command runs its own event loop, so this test is not async itself)"""
    from types import SimpleNamespace

    from pangloss_cli import migrations

    from pangloss_testing.live import run_connected

    m = models()

    async def seed():
        w = await world(m)
        citing = await same_as(m, w, w.birth, w.naming)
        return w, citing

    w, citing = run_connected(command_backend, seed)
    project = SimpleNamespace(require_database=lambda: command_backend)

    capsys.readouterr()
    migrations.report_citations_check(project)
    assert "citations are of something" not in capsys.readouterr().err

    async def remove():
        statements = as_update(m, w.factoid)["statements"][1:]
        await m.Factoid.Update(**as_update(m, w.factoid, statements=statements)).save(
            acknowledge_citations="removals"
        )

    run_connected(command_backend, remove)
    capsys.readouterr()
    migrations.report_citations_check(project)
    said = capsys.readouterr().err
    assert "1 citations are of something that has been removed" in said
    assert f"SameAs {citing.id} (Ann is Bob) cites Birth {w.birth.id}" in said
