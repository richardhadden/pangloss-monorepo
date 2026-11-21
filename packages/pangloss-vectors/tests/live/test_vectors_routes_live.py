"""The routes (implementation_docs/similarity-build-plan.md, step 2.5): `GET /api/{NAME}/{id}/similar`, the reference
views of the nearest with their similarities, as the reader may see them; `GET /api/vectors/status`. And phase 2's
"done when": a project with only `pangloss_vectors` installed answers "documents of a like class" over the API"""

from typing import no_type_check

import asyncio

import httpx2 as httpx
import pytest
import pytest_asyncio
from pangloss_api import create_app
from pangloss_users import service
from pangloss_vectors import VectorRow
from pangloss_vectors.class_part import PART
from pangloss_vectors.rebuild import rebuild
from vectors_live_support import (
    EVENTS,
    WaitingPart,
    declare_events,
    drop_vector_indexes,
    make_vector_indexes,
    saved_events,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"


@pytest.fixture
def class_part(db_driver, clear_database, parts_of_the_test):
    """The class part alone (the default profile is it, at its weight)"""
    parts_of_the_test(PART)
    drop_vector_indexes(db_driver)
    yield PART
    drop_vector_indexes(db_driver)


@pytest_asyncio.fixture(loop_scope="session")
async def client(class_part):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        yield client


async def bearer(client) -> dict:
    await service.create_user("root", "root@example.com", PASSWORD, admin=True)
    response = await client.post(
        "/api/users/token", data={"username": "root", "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def built(m, **labels) -> dict[str, str]:
    """Items saved, the vectors rebuilt and their indexes made: the ids by label"""
    made = await saved_events(m, **labels)
    await rebuild()
    await make_vector_indexes()
    return made


def labels(answer) -> list[str]:
    return [item["label"] for item in answer["results"]]


# ---------------------------------------------------------------------------
# Phase 2 is done when
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_project_with_only_pangloss_vectors_answers_documents_of_a_like_class(
    class_part,
):
    """A painting's similar are led by the other paintings, then the artworks, and a birth comes after them"""
    m = declare_events()
    made = await built(
        m,
        CreationOfPainting=["painting 1", "painting 2", "painting 3"],
        CreationOfArtwork=["artwork 1", "artwork 2"],
        CreationOfSculpture=["sculpture"],
        Creation=["creation"],
        Birth=["birth"],
        Person=["Anna"],
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get(
            f"/api/CreationOfPainting/{made['painting 1']}/similar"
        )

    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["status"] == "ok"
    found = labels(answer)
    assert set(found[:2]) == {"painting 2", "painting 3"}
    assert set(found[2:4]) == {"artwork 1", "artwork 2"}
    assert found.index("birth") > found.index("sculpture")
    assert found.index("birth") > found.index("creation")
    assert "painting 1" not in found


# ---------------------------------------------------------------------------
# GET /api/{NAME}/{id}/similar
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_route_gives_reference_views_with_their_similarity_nearest_first(
    client,
):
    m = declare_events()
    made = await built(m, **EVENTS)

    response = await client.get(f"/api/CreationOfPainting/{made['painting 1']}/similar")

    assert response.status_code == 200, response.text
    results = response.json()["results"]
    # (the two other paintings, the artwork and the birth, an event as it is; not the two people, who share no class
    # with it: a similarity of 0 is left out)
    assert len(results) == 4
    first = results[0]
    assert first["type"] == "CreationOfPainting"
    assert first["id"] in (made["painting 2"], made["painting 3"])
    assert first["label"] in ("painting 2", "painting 3")
    # (a reference view, as a list gives it: its meta, in camelCase)
    assert first["meta"]["isHeadNode"] is True
    assert first["similarity"] == pytest.approx(1.0)
    similarities = [item["similarity"] for item in results]
    assert similarities == sorted(similarities, reverse=True)
    assert results[2]["label"] == "artwork"
    assert [item["type"] for item in results[3:]] == ["Birth"]


@no_type_check
async def test_a_read_at_a_class_above_the_item_s_is_answered_and_one_at_another_class_is_not(
    client,
):
    m = declare_events()
    made = await built(m, **EVENTS)

    above = await client.get(f"/api/Event/{made['painting 1']}/similar")
    assert above.status_code == 200
    assert labels(above.json())[0] in ("painting 2", "painting 3")

    other = await client.get(f"/api/Person/{made['painting 1']}/similar")
    assert other.status_code == 404
    unknown = await client.get(f"/api/Nothing/{made['painting 1']}/similar")
    assert unknown.status_code == 404


@no_type_check
async def test_a_deleted_item_is_404_and_a_deleted_hit_is_left_out(client):
    m = declare_events()
    made = await built(m, **EVENTS)

    await m.CreationOfPainting.delete(made["painting 2"])
    response = await client.get(f"/api/CreationOfPainting/{made['painting 1']}/similar")
    assert response.status_code == 200
    assert "painting 2" not in labels(response.json())

    await m.CreationOfPainting.delete(made["painting 1"])
    gone = await client.get(f"/api/CreationOfPainting/{made['painting 1']}/similar")
    assert gone.status_code == 404
    assert "There is no CreationOfPainting with id" in gone.json()["detail"]


@no_type_check
async def test_an_unpublished_item_is_404_to_a_reader_not_logged_in_and_seen_by_one_who_is(
    client,
):
    m = declare_events(reviewed=True)
    made = await built(m, CreationOfPainting=["waiting"], CreationOfArtwork=["artwork"])

    anyone = await client.get(f"/api/CreationOfPainting/{made['waiting']}/similar")
    assert anyone.status_code == 404
    # (nor is it among what another item's similar give)
    from_artwork = await client.get(f"/api/CreationOfArtwork/{made['artwork']}/similar")
    assert from_artwork.status_code == 200
    assert labels(from_artwork.json()) == []

    headers = await bearer(client)
    logged_in = await client.get(
        f"/api/CreationOfPainting/{made['waiting']}/similar", headers=headers
    )
    assert logged_in.status_code == 200
    assert labels(logged_in.json()) == ["artwork"]
    from_artwork = await client.get(
        f"/api/CreationOfArtwork/{made['artwork']}/similar", headers=headers
    )
    assert labels(from_artwork.json()) == ["waiting"]


@no_type_check
async def test_an_item_with_no_vector_is_pending(client):
    m = declare_events()
    await built(m, **EVENTS)
    later = await m.Birth.Create(label="since").save()

    response = await client.get(f"/api/Birth/{later.id}/similar")

    assert response.status_code == 200
    assert (response.json()["status"], response.json()["results"]) == ("pending", [])


@no_type_check
async def test_a_profile_never_built_is_pending(client):
    m = declare_events()
    made = await saved_events(m, **EVENTS)

    response = await client.get(f"/api/Birth/{made['birth']}/similar")

    assert (response.json()["status"], response.json()["results"]) == ("pending", [])


@no_type_check
async def test_type_narrows_to_a_group_and_one_that_is_not_a_group_is_refused(client):
    m = declare_events()
    made = await built(m, **EVENTS, Saint=["Catherine"])

    everything = await client.get(f"/api/Person/{made['Anna']}/similar")
    assert {item["type"] for item in everything.json()["results"]} == {
        "Person",
        "Saint",
    }
    narrowed = await client.get(
        f"/api/Person/{made['Anna']}/similar",
        params={"type": "Person"},
    )
    assert narrowed.status_code == 200
    assert {item["type"] for item in narrowed.json()["results"]} == {"Person", "Saint"}
    # (and from a painting, narrowed to people: none of them has anything in common with it)
    none = await client.get(
        f"/api/CreationOfPainting/{made['painting 1']}/similar",
        params={"type": "Person"},
    )
    assert (none.status_code, none.json()["results"]) == (200, [])

    refused = await client.get(
        f"/api/CreationOfPainting/{made['painting 1']}/similar",
        params={"type": "Birth"},
    )
    assert refused.status_code == 422
    assert "'Birth' is not a group" in refused.json()["detail"]


@no_type_check
async def test_limit_bounds_the_results_and_is_from_1_to_100(client):
    m = declare_events()
    made = await built(m, **EVENTS)
    url = f"/api/CreationOfPainting/{made['painting 1']}/similar"

    two = await client.get(url, params={"limit": 2})
    assert two.status_code == 200
    assert len(two.json()["results"]) == 2
    for wrong in (0, 101):
        assert (await client.get(url, params={"limit": wrong})).status_code == 422
    assert (await client.get(url, params={"limit": 100})).status_code == 200


@no_type_check
async def test_an_unknown_profile_or_parameter_is_refused(client):
    m = declare_events()
    made = await built(m, **EVENTS)
    url = f"/api/CreationOfPainting/{made['painting 1']}/similar"

    unknown = await client.get(url, params={"profile": "nope"})
    assert unknown.status_code == 422
    assert "There is no profile named 'nope'" in unknown.json()["detail"]
    assert (await client.get(url, params={"profile": "default"})).status_code == 200
    assert (await client.get(url, params={"nope": 1})).status_code == 422


@no_type_check
async def test_a_rebuild_due_is_said_with_the_results_of_the_vectors_in_use(
    client, monkeypatch
):
    import pangloss_core.settings as core_settings

    m = declare_events()
    made = await built(m, **EVENTS)
    monkeypatch.setattr(core_settings.SETTINGS, "VECTORS_CLASS_DECAY", 0.3)

    response = await client.get(f"/api/CreationOfPainting/{made['painting 1']}/similar")

    answer = response.json()
    assert answer["status"] == "rebuild_due"
    assert len(answer["results"]) == 4


@no_type_check
async def test_the_answer_names_the_profiles_default_first_and_the_groups(
    client, monkeypatch
):
    import pangloss_core.settings as core_settings

    monkeypatch.setattr(
        core_settings.SETTINGS,
        "VECTORS_PROFILES",
        {"broad": {"class": 1}, "another": {"class": 0.5}},
    )
    m = declare_events()
    made = await saved_events(m, **EVENTS)

    answer = (await client.get(f"/api/Birth/{made['birth']}/similar")).json()

    # (`default` is every part at its own weight, when the settings do not name it)
    assert answer["profiles"] == ["default", "another", "broad"]
    assert answer["groups"] == ["Person"]


def declare_with_notes():
    """A person (a group), a letter, and a note whose class has no vectors"""
    from types import SimpleNamespace

    from pangloss_models import Document, Entity, ModelRegistry, initialise
    from pangloss_vectors import VectorsMeta

    ModelRegistry._reset()

    class Person(Entity):
        _vectors_meta = VectorsMeta(searchable=True)

    class Letter(Document):
        pass

    class Note(Document):
        _vectors_meta = VectorsMeta(include=False)

    initialise()
    return SimpleNamespace(Person=Person, Letter=Letter, Note=Note)


@no_type_check
async def test_an_item_of_a_class_without_vectors_is_excluded_and_nothing_is_searched(
    client, monkeypatch
):
    import pangloss_vectors.search

    m = declare_with_notes()
    made = await built(m, Letter=["letter 1", "letter 2"], Note=["note"])
    # (a letter's similar never include it)
    letter = (await client.get(f"/api/Letter/{made['letter 1']}/similar")).json()
    assert letter["status"] == "ok"
    assert labels(letter) == ["letter 2"]

    async def no_search(*args, **kwargs):
        raise AssertionError("an excluded item is not searched from")

    monkeypatch.setattr(pangloss_vectors.search, "nearest", no_search)
    response = await client.get(f"/api/Note/{made['note']}/similar")

    assert response.status_code == 200, response.text
    answer = response.json()
    assert (answer["status"], answer["results"]) == ("excluded", [])
    assert answer["profiles"] == ["default"] and answer["groups"] == ["Person"]


@no_type_check
async def test_an_item_with_nothing_in_common_is_not_among_the_similar(client):
    m = declare_with_notes()
    # (a person and a letter share no class: by the class part alone, the cosine of the two is 0)
    made = await built(m, Letter=["letter 1", "letter 2"], Person=["ann"])

    letter = (await client.get(f"/api/Letter/{made['letter 1']}/similar")).json()
    person = (await client.get(f"/api/Person/{made['ann']}/similar")).json()

    assert (letter["status"], labels(letter)) == ("ok", ["letter 2"])
    assert (person["status"], person["results"]) == ("ok", [])


# ---------------------------------------------------------------------------
# GET /api/vectors/status
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_status_route_is_for_a_logged_in_reader_and_says_what_is_in_use(
    client,
):
    m = declare_events()
    await built(m, **EVENTS)

    assert (await client.get("/api/vectors/status")).status_code == 401
    response = await client.get("/api/vectors/status", headers=await bearer(client))

    assert response.status_code == 200
    answer = response.json()
    assert answer["rebuildDue"] is False
    [part] = answer["parts"]
    assert part["part"] == "class"
    assert part["count"] == 7 and part["stale"] == 0
    assert part["dimension"] == PART.dimension()
    assert part["signature"] == PART.signature()
    assert part["builtAt"] is not None and part["reasons"] == []
    [profile] = answer["profiles"]
    assert profile["profile"] == "default"
    assert profile["weights"] == {"class": 0.1}
    assert profile["count"] == 7 and profile["rebuildDue"] is False
    assert answer["rebuilding"] is None


@no_type_check
async def test_the_status_says_who_is_rebuilding_while_a_rebuild_runs_and_nothing_after(
    db_driver, clear_database, parts_of_the_test
):
    declare_events()
    waiting = WaitingPart("w")
    parts_of_the_test(waiting)
    waiting.rows = [VectorRow(f"i{n}", "Birth", [1, n, 0]) for n in range(4)]
    waiting.go = asyncio.Event()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        headers = await bearer(client)
        task = asyncio.create_task(rebuild())
        try:
            await asyncio.wait_for(waiting.waiting.wait(), 10)
            during = (await client.get("/api/vectors/status", headers=headers)).json()
        finally:
            waiting.go.set()
            await task
        after = (await client.get("/api/vectors/status", headers=headers)).json()

    assert during["rebuilding"] is not None
    assert during["rebuilding"]["by"].startswith("process ")
    assert during["rebuilding"]["since"]
    assert after["rebuilding"] is None
