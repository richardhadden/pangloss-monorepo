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
async def test_type_narrows_to_a_group_or_to_a_class_and_a_name_that_is_neither_is_refused(
    client,
):
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

    # (a class that is not a group: scanned, step 7a.4)
    births = await client.get(
        f"/api/CreationOfPainting/{made['painting 1']}/similar",
        params={"type": "Birth"},
    )
    assert births.status_code == 200
    assert labels(births.json()) == ["birth"]

    refused = await client.get(
        f"/api/CreationOfPainting/{made['painting 1']}/similar",
        params={"type": "Nothing"},
    )
    assert refused.status_code == 422
    assert (
        "'Nothing' is not a class of documents or entities" in refused.json()["detail"]
    )


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
async def test_a_mention_is_among_no_similar_and_once_it_is_excluded_is_left_out_before_the_rebuild(
    client, db_driver, parts_of_the_test, monkeypatch
):
    """(step 7a.3) a stand-in (`pangloss_review`'s `Unreconciled`) with `VECTORS_INCLUDE` has vectors and is found;
    without it, a rebuild is due, and the route leaves it out at once, its old vectors still there"""
    import pangloss_core.settings as core_settings
    from vectors_live_support import declare_hearings, every_item, saved_hearing

    monkeypatch.setattr(
        core_settings.SETTINGS,
        "INSTALLED_APPS",
        ["pangloss_vectors", "pangloss_review"],
    )
    monkeypatch.setattr(core_settings.SETTINGS, "VECTORS_INCLUDE", ["Unreconciled"])
    other = WaitingPart("other")
    parts_of_the_test(other)
    m = declare_hearings()
    made = await saved_hearing(m)
    other.rows = every_item(db_driver)
    await rebuild()
    await make_vector_indexes()

    def ids(answer) -> set[str]:
        return {item["id"] for item in answer["results"]}

    answer = (await client.get(f"/api/Testimony/{made['testimony']}/similar")).json()
    assert answer["status"] == "ok"
    assert made["mention"] in ids(answer)
    mention = (await client.get(f"/api/Unreconciled/{made['mention']}/similar")).json()
    assert mention["status"] == "ok"

    monkeypatch.setattr(core_settings.SETTINGS, "VECTORS_INCLUDE", None)
    headers = await bearer(client)
    answer = (
        await client.get(f"/api/Testimony/{made['testimony']}/similar", headers=headers)
    ).json()

    assert answer["status"] == "rebuild_due"
    assert made["mention"] not in ids(answer)
    assert {made["witness"], made["hearing"], made["note"]} <= ids(answer)
    mention = (await client.get(f"/api/Unreconciled/{made['mention']}/similar")).json()
    assert (mention["status"], mention["results"]) == ("excluded", [])


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
# GET /api/{NAME}/{URL}/similar (step 7a.2): an entity by one of its URLs
# ---------------------------------------------------------------------------


def declare_with_urls():
    """People who may be made with a URL (`create_with_id`), and letters"""
    from types import SimpleNamespace

    from pangloss_models import Document, Entity, ModelRegistry, initialise

    ModelRegistry._reset()

    class Person(Entity):
        _meta = Entity.Meta(create_with_id=True)

    class Letter(Document):
        pass

    initialise()
    return SimpleNamespace(Person=Person, Letter=Letter)


@no_type_check
async def people(m, merge: dict[str, str] | None = None, **urls: str | None):
    """People saved, by label, with the URL given (or none), the people of `merge` merged into others (absorbed:
    survivor, by label), and the vectors rebuilt: their ids by label"""
    from pydantic import AnyHttpUrl

    made = {}
    for label, url in urls.items():
        if url is None:
            saved = await m.Person.Create(label=label).save()
        else:
            saved = await m.Person.Create(
                id=AnyHttpUrl(url), create_new=True, label=label
            ).save()
        made[label] = str(saved.id)
    for absorbed, survivor in (merge or {}).items():
        await m.Person.merge(made[absorbed], into=made[survivor])
    await rebuild()
    await make_vector_indexes()
    return made


def by_id(answer) -> dict:
    """The answer, its results by id (people alike by the class part are all as near: their order is not fixed)"""
    return {
        **answer,
        "results": {item["id"]: item for item in answer["results"]},
    }


@no_type_check
async def test_an_entity_is_asked_for_by_its_url_as_by_its_id(client):
    m = declare_with_urls()
    made = await people(m, ann="http://x.org/people/ann", bob=None, cat=None)

    at_url = await client.get("/api/Person/http://x.org/people/ann/similar")
    at_id = await client.get(f"/api/Person/{made['ann']}/similar")

    assert at_url.status_code == 200, at_url.text
    assert at_url.json()["status"] == "ok"
    assert set(labels(at_url.json())) == {"bob", "cat"}
    assert by_id(at_url.json()) == by_id(at_id.json())


@no_type_check
async def test_a_url_s_own_query_is_the_url_s_and_the_route_s_parameters_still_apply(
    client,
):
    m = declare_with_urls()
    made = await people(
        m, ann="http://x.org/p?id=7", bob=None, cat=None, dee=None, eve=None
    )

    response = await client.get(
        "/api/Person/http://x.org/p/similar?id=7&limit=3&profile=default"
    )

    assert response.status_code == 200, response.text
    assert len(response.json()["results"]) == 3
    assert made["ann"] not in by_id(response.json())["results"]
    # (and without the URL's query it is another URL, which no one has)
    other = await client.get("/api/Person/http://x.org/p/similar?limit=3")
    assert other.status_code == 404
    assert "URL http://x.org/p " in other.json()["detail"]
    # (the route's own parameters are still checked)
    wrong = await client.get("/api/Person/http://x.org/p/similar?id=7&limit=0")
    assert wrong.status_code == 422


@no_type_check
async def test_a_url_whose_slashes_a_proxy_merged_is_found(client):
    m = declare_with_urls()
    made = await people(m, ann="http://x.org/people/ann", bob=None)

    response = await client.get("/api/Person/http:/x.org/people/ann/similar")

    assert response.status_code == 200, response.text
    assert by_id(response.json()) == by_id(
        (await client.get(f"/api/Person/{made['ann']}/similar")).json()
    )


@no_type_check
async def test_a_url_no_entity_has_is_404_and_says_how_a_url_ending_in_similar_is_read(
    client,
):
    m = declare_with_urls()
    await people(m, ann="http://x.org/people/ann")

    response = await client.get("/api/Person/http://x.org/nobody/similar")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "There is no Person with URL http://x.org/nobody" in detail
    assert "whose URL itself ends in /similar is read by its id" in detail


@no_type_check
async def test_a_url_at_a_document_class_is_refused(client):
    m = declare_with_urls()
    made = await people(m, ann="http://x.org/people/ann")
    letter = await m.Letter.Create(label="letter").save()

    response = await client.get("/api/Letter/http://x.org/people/ann/similar")

    assert response.status_code == 422
    assert "a document is found by its id" in response.json()["detail"]
    # (by its id, as before)
    assert (await client.get(f"/api/Letter/{letter.id}/similar")).status_code == 200
    assert made


@no_type_check
async def test_the_url_of_an_entity_merged_into_another_answers_for_its_survivor(
    client,
):
    m = declare_with_urls()
    made = await people(
        m,
        merge={"absorbed": "kept"},
        kept="http://x.org/people/kept",
        absorbed="http://x.org/people/absorbed",
        bob=None,
        cat=None,
    )

    at_url = await client.get("/api/Person/http://x.org/people/absorbed/similar")
    of_survivor = await client.get(f"/api/Person/{made['kept']}/similar")

    assert at_url.status_code == 200, at_url.text
    assert at_url.json()["status"] == "ok"
    assert set(labels(at_url.json())) == {"bob", "cat"}
    assert by_id(at_url.json()) == by_id(of_survivor.json())
    # (as the id of the entity merged does)
    of_absorbed = await client.get(f"/api/Person/{made['absorbed']}/similar")
    assert by_id(of_absorbed.json()) == by_id(of_survivor.json())


@no_type_check
async def test_an_entity_whose_url_ends_in_similar_has_its_similar_at_similar_similar(
    client,
):
    m = declare_with_urls()
    made = await people(m, odd="http://x.org/people/similar", bob=None)

    response = await client.get("/api/Person/http://x.org/people/similar/similar")

    assert response.status_code == 200, response.text
    assert labels(response.json()) == ["bob"]
    assert by_id(response.json()) == by_id(
        (await client.get(f"/api/Person/{made['odd']}/similar")).json()
    )
    # (and at its own URL it is not read: the similar route takes it, for the URL without the /similar, and says so)
    at_url = await client.get("/api/Person/http://x.org/people/similar")
    assert at_url.status_code == 404
    assert "There is no Person with URL http://x.org/people " in at_url.json()["detail"]
    assert "ends in /similar is read by its id" in at_url.json()["detail"]
    # (by its id it is: the model's routes of an app made now, after the models of the test)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as now:
        own = await now.get(f"/api/Person/{made['odd']}")
        at_url = await now.get("/api/Person/http://x.org/people/similar")
    assert own.status_code == 200, own.text
    assert at_url.status_code == 404
    assert "ends in /similar is read by its id" in at_url.json()["detail"]


@no_type_check
async def test_a_reference_that_is_neither_an_id_nor_a_url_is_refused(client):
    m = declare_with_urls()
    await people(m, ann="http://x.org/people/ann")

    for bad in ("ann", "ftp://x.org/people/ann", "http://"):
        response = await client.get(f"/api/Person/{bad}/similar")
        assert response.status_code == 422, bad
        assert "is neither an id nor an http(s) URL" in response.json()["detail"]


@no_type_check
async def test_an_app_s_route_ending_in_similar_after_this_one_is_not_taken_by_it(
    class_part,
):
    """The similar route matches only where its first part is a model's: a route of another app, ending in
    `/similar` as review's `/api/review/unreconciled/{id}/similar` does, included after it, is still reached"""
    declare_with_urls()
    app = create_app()

    @app.get("/api/elsewhere/things/{id}/similar")
    async def elsewhere(id: str):
        return {"elsewhere": id}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/elsewhere/things/x/similar")
        unknown = await client.get("/api/Nothing/things/x/similar")

    assert response.status_code == 200, response.text
    assert response.json() == {"elsewhere": "x"}
    assert unknown.status_code == 404


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


# ---------------------------------------------------------------------------
# Several types, and a field's (step 7a.4)
# ---------------------------------------------------------------------------


@no_type_check
def declare_agents(reviewed: bool = False):
    """`Person` (a group) above `Saint`, `Group` (a group), `Place` (in no group); an `Activity`, nested in a
    `Factoid`, carried out by people or groups and at a place; a `Letter` sent by people; a `Report` in no group (with
    `reviewed`, saved unpublished)"""
    import importlib
    from types import SimpleNamespace

    from pangloss_models import Document, Entity, ModelRegistry, initialise
    from pangloss_vectors import VectorsMeta

    ModelRegistry._reset()
    review_meta = {}
    if reviewed:
        review = pytest.importorskip("pangloss_review")
        import pangloss_review.models

        importlib.reload(pangloss_review.models)
        review_meta = {"_review_meta": review.ReviewMeta(reviewable=True)}

    class Person(Entity):
        _vectors_meta = VectorsMeta(searchable=True)

    class Saint(Person):
        pass

    class Group(Entity):
        _vectors_meta = VectorsMeta(searchable=True)

    class Place(Entity):
        pass

    class Activity(Document):
        _meta = Document.Meta(create_directly=False)
        carried_out_by: list[Person | Group]
        took_place_at: list[Place]

    class Factoid(Document):
        activities: list[Activity]

    class Letter(Document):
        sent_by: list[Person]
        text: str = ""

    Report = type("Report", (Document,), {"__module__": __name__, **review_meta})

    initialise()
    return SimpleNamespace(
        Person=Person,
        Saint=Saint,
        Group=Group,
        Place=Place,
        Factoid=Factoid,
        Letter=Letter,
        Report=Report,
    )


# (each item's vector of the one part, about the person `q`)
AGENTS = {
    "q": ("Person", [1, 0, 0]),
    "person 1": ("Person", [1, 0.3, 0]),
    "person 2": ("Person", [0.4, 1, 0]),
    "saint 1": ("Saint", [1, 0.1, 0.2]),
    "group 1": ("Group", [1, 0.05, 0]),
    "group 2": ("Group", [0.6, 0.5, 0.5]),
    "place 1": ("Place", [1, 0.2, 0.1]),
    "report 1": ("Report", [1, 0.15, 0]),
    "report 2": ("Report", [0.3, 1, 0.2]),
}


@pytest.fixture
def planted_part(db_driver, clear_database, parts_of_the_test):
    """One part whose rebuild writes the rows a test gives it (the default profile is it)"""
    made = WaitingPart("planted")
    parts_of_the_test(made)
    drop_vector_indexes(db_driver)
    yield made
    drop_vector_indexes(db_driver)


@pytest_asyncio.fixture(loop_scope="session")
async def agents_client(planted_part):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        yield client


@no_type_check
async def planted_agents(m, part, rows=AGENTS) -> dict[str, str]:
    """The items of `rows` saved (and a factoid with an activity), their vectors rebuilt, the indexes made: ids by
    label"""
    made = {}
    for label, (class_name, _vector) in rows.items():
        made[label] = str((await getattr(m, class_name).Create(label=label).save()).id)
    part.rows = [
        VectorRow(made[label], class_name, vector)
        for label, (class_name, vector) in rows.items()
    ]
    await rebuild()
    await make_vector_indexes()
    return made


def results(answer) -> list[tuple[str, str, float]]:
    return [(r["id"], r["type"], r["similarity"]) for r in answer["results"]]


def same_results(found, expected) -> None:
    assert [r[:2] for r in found] == [r[:2] for r in expected]
    for (_, _, score), (_, _, wanted) in zip(found, expected, strict=True):
        assert score == pytest.approx(wanted, abs=1e-6)


async def cut_by_hand(client, url: str, classes: set[str], limit: int, **asked):
    """The whole answer with the largest limit, cut to the classes: what one narrowed to them must give"""
    whole = await client.get(url, params={"limit": 100}, **asked)
    assert whole.json()["status"] == "ok"
    return [r for r in results(whole.json()) if r[1] in classes][:limit]


@no_type_check
async def test_two_types_give_both_in_the_order_of_their_scores_as_the_whole_answer_cut_to_them(
    agents_client, planted_part
):
    m = declare_agents()
    made = await planted_agents(m, planted_part)
    url = f"/api/Person/{made['q']}/similar"
    expected = await cut_by_hand(agents_client, url, {"Person", "Saint", "Group"}, 4)

    response = await agents_client.get(
        url, params=[("type", "Person"), ("type", "Group"), ("limit", "4")]
    )

    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["status"] == "ok"
    same_results(results(answer), expected)
    assert {r[1] for r in results(answer)} == {"Person", "Saint", "Group"}
    # (what the interface offers is as it was)
    assert answer["groups"] == ["Group", "Person"]


@no_type_check
async def test_a_group_and_a_class_that_is_not_one_and_a_class_alone(
    agents_client, planted_part
):
    m = declare_agents()
    made = await planted_agents(m, planted_part)
    url = f"/api/Person/{made['q']}/similar"

    both = await agents_client.get(url, params=[("type", "Group"), ("type", "Place")])
    same_results(
        results(both.json()),
        await cut_by_hand(agents_client, url, {"Group", "Place"}, 10),
    )
    assert [r[0] for r in results(both.json())] == [
        made["group 1"],
        made["place 1"],
        made["group 2"],
    ]

    place = await agents_client.get(url, params={"type": "Place"})
    assert [r[0] for r in results(place.json())] == [made["place 1"]]


@no_type_check
async def test_a_field_gives_what_its_types_named_give_and_with_a_type_the_union(
    agents_client, planted_part
):
    m = declare_agents()
    made = await planted_agents(m, planted_part)
    url = f"/api/Person/{made['q']}/similar"

    # (a nested document's field: an activity is in a factoid)
    by_field = await agents_client.get(
        url, params={"field": "Activity.carried_out_by", "limit": 4}
    )
    named = await agents_client.get(
        url,
        params=[("type", "Group"), ("type", "Person"), ("type", "Saint"), ("limit", 4)],
    )
    assert by_field.status_code == 200, by_field.text
    assert results(by_field.json()) == results(named.json())

    # (a head's field, in JSON's spelling: people and saints only)
    letters = await agents_client.get(url, params={"field": "Letter.sentBy"})
    assert {r[1] for r in results(letters.json())} == {"Person", "Saint"}

    # (with a type, of either)
    union = await agents_client.get(
        url, params={"field": "Letter.sent_by", "type": "Place"}
    )
    same_results(
        results(union.json()),
        await cut_by_hand(agents_client, url, {"Person", "Saint", "Place"}, 10),
    )


@no_type_check
async def test_a_field_that_is_no_model_s_no_field_or_not_a_relation_is_refused_by_name(
    agents_client, planted_part
):
    m = declare_agents()
    made = await planted_agents(m, planted_part)
    url = f"/api/Person/{made['q']}/similar"

    for field, said in (
        ("Nothing.sent_by", "there is no model 'Nothing'"),
        ("Letter.nothing", "Letter has no field 'nothing'"),
        ("Letter.text", "'Letter.text' is not a relation"),
        ("Factoid.activities", "'Factoid.activities' reaches no class of entities"),
        ("sent_by", "'sent_by' is not a field"),
    ):
        response = await agents_client.get(url, params={"field": field})
        assert response.status_code == 422, field
        assert said in response.json()["detail"], response.json()


@no_type_check
async def test_an_unpublished_item_of_a_scanned_class_is_shown_only_to_a_reader_logged_in(
    agents_client, planted_part
):
    m = declare_agents(reviewed=True)
    made = await planted_agents(m, planted_part)
    url = f"/api/Person/{made['q']}/similar"

    anyone = await agents_client.get(url, params={"type": "Report"})
    assert (anyone.status_code, anyone.json()["results"]) == (200, [])

    headers = await bearer(agents_client)
    logged_in = await agents_client.get(url, params={"type": "Report"}, headers=headers)
    assert [r[0] for r in results(logged_in.json())] == [
        made["report 1"],
        made["report 2"],
    ]


@no_type_check
async def test_an_entity_merged_into_another_is_not_among_the_similar_of_a_scanned_class(
    agents_client, planted_part
):
    m = declare_agents()
    rows = {**AGENTS, "place 2": ("Place", [0.9, 0.3, 0])}
    made = await planted_agents(m, planted_part, rows)
    url = f"/api/Person/{made['q']}/similar"
    before = await agents_client.get(url, params={"type": "Place"})
    assert [r[0] for r in results(before.json())] == [made["place 1"], made["place 2"]]

    await m.Place.merge(made["place 1"], into=made["place 2"])
    after = await agents_client.get(url, params={"type": "Place"})

    assert [r[0] for r in results(after.json())] == [made["place 2"]]
