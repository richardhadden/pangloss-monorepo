"""What sets the worker that suggests off over what is already stored (`suggesting.mark_stored`, the route
`/api/reconcile/suggest`, the admin job `reconcile_suggest`, `suggesting.status`; step 10.5e of
implementation_docs/similarity-build-plan.md), on the backend under test.

On models of the test (review's `Unreconciled` for people): letters that may name someone not identified, and
postcards, which are letters; diaries, which may too; notes about places, which cannot hold a stand-in; a derived
summary. And, for what the worker then does, the models and the world of the worker's tests. What is claimed: which
heads are marked (and which not), that a head already marked keeps its mark as it was, `classes`, `again`, the pages,
what follows a bulk load, the route's permission and answers, the job."""

import importlib
from types import SimpleNamespace
from typing import Any, no_type_check

import httpx2 as httpx
import pytest
import pytest_asyncio
from pangloss_core import backend
from pangloss_models import hooks
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, load
from pangloss_testing.live import apply_changes, run
from pangloss_testing.parts import drop_vector_indexes
from pangloss_users import service
from test_reconcile_worker_live import (
    STRANGER,
    drained,
    factoid,
    kept,
    marks,
    settle,
    stand_ins,
    suggestions,
    unknown,
    world,
    worker_models,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"
ROUTE = "/api/reconcile/suggest"


@pytest.fixture
def database(db_driver, clear_database):
    """(the database emptied, and the vector indexes the tests made dropped, before and after)"""
    drop_vector_indexes(db_driver)
    yield db_driver
    drop_vector_indexes(db_driver)


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def structure(database):
    """The package's migrations applied, as `pangloss migrate` would"""
    for name in ["0001_initial", "0002_models", "0003_suggested"]:
        migration = load("pangloss_reconcile", name)
        await apply_changes(
            backend.current().database(), EMPTY_SNAPSHOT, list(migration.changes)
        )


@pytest.fixture(autouse=True)
def a_new_worker(monkeypatch):
    """This process's worker made again for each test"""
    from pangloss_reconcile import suggesting

    monkeypatch.setattr(suggesting, "worker", suggesting.Worker())
    return suggesting.worker


@no_type_check
def trigger_models(mention: bool = False):
    """The models of the test, by name. `mention`: `Mention` is declared too (a stand-in while
    `pangloss_testing.similar_models.mention_stand_in()` is among `hooks.stand_ins`)"""
    import pangloss_criteria.models
    import pangloss_library.models
    import pangloss_review.models
    from pangloss_derived import DerivedDocument, DerivedFrom
    from pangloss_models import Document, Entity, ModelRegistry, initialise
    from pangloss_review import ReviewMeta

    ModelRegistry._reset()
    importlib.reload(pangloss_library.models)
    importlib.reload(pangloss_criteria.models)
    importlib.reload(pangloss_review.models)
    Identification = pangloss_library.models.Identification
    Alternatives = pangloss_library.models.WeightedAlternative
    reviewed = ReviewMeta(reviewable=True)

    class Person(Entity):
        _review_meta = ReviewMeta(allow_unreconciled=True)

    if mention:

        class Mention(Document):
            _meta = Document.Meta(create_directly=False)
            mentioned_type: str

    class Place(Entity):
        pass

    class Letter(Document):
        _review_meta = reviewed
        to: list[Person | Identification[Alternatives[Person]]]

    class Postcard(Letter):
        pass

    class Diary(Document):
        _review_meta = reviewed
        about: list[Person | Identification[Alternatives[Person]]]

    class PlaceNote(Document):
        _review_meta = reviewed
        at: list[Place]

    class Summary(Document, DerivedDocument):
        sources: list[DerivedFrom[Letter]]
        to: list[Person | Identification[Alternatives[Person]]]

    initialise()
    return SimpleNamespace(**{k: v for k, v in locals().items() if isinstance(v, type)})


def mention(label: str = "Jon Smyth") -> dict[str, Any]:
    return unknown(label)


def person(id: Any) -> dict[str, str]:
    return {"type": "Person", "id": str(id)}


@no_type_check
async def letter(m, *to: Any, kind: str = "Letter", **save: Any):
    model = getattr(m, kind)
    return await model.Create(label=f"a {kind.lower()}", to=list(to)).save(**save)


async def marked_by(**options: Any):
    from pangloss_reconcile.suggesting import mark_stored

    return await mark_stored(**options)


def tokens(db_driver) -> dict[str, tuple[Any, Any, Any]]:
    """Each mark of the kind: its token, claim and the time it holds until, by head"""
    return {
        row["head"]: (row["token"], row["claim"], row["until"])
        for row in run(
            db_driver,
            "MATCH (p:PGPending {kind: 'reconcile'}) "
            "RETURN p.head_id AS head, p.token AS token, p.claim AS claim, p.claimed_until AS until",
        )
    }


@pytest.fixture
def woken():
    """The classes `hooks.work_marked` is told of while the test runs"""
    heard: list[str] = []

    def listen(model: type) -> None:
        heard.append(model.__name__)

    hooks.work_marked.append(listen)
    yield heard
    hooks.work_marked.remove(listen)


# ---------------------------------------------------------------------------
# What is marked
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_heads_holding_a_stand_in_are_marked_and_no_others(database, woken):
    from pangloss_derived.documents import writing_derived
    from pangloss_reconcile.suggesting import Marked

    m = trigger_models()
    ada = await m.Person.Create(label="Ada").save()
    paris = await m.Place.Create(label="Paris").save()
    holding = await letter(m, mention(), mention("Xavier Quux"), person(ada.id))
    diary = await m.Diary.Create(label="a diary", about=[mention()]).save()
    # (none: a letter of people identified, a published one, a deleted one, a note of places, a derived summary)
    await letter(m, person(ada.id))
    await letter(m, mention(), published=True)
    deleted = await letter(m, mention())
    await m.Letter.delete(deleted.id)
    await m.PlaceNote.Create(
        label="a note", at=[{"type": "Place", "id": str(paris.id)}]
    ).save()
    with writing_derived("a rule"):
        await m.Summary.Create(
            label="derived",
            sources=[{"type": "Letter", "id": str(holding.id)}],
            to=[mention()],
        ).save()
    # (the setting is off and no write said `suggest`: nothing is marked yet)
    assert marks(database) == []

    done = await marked_by()

    assert done == Marked(marked=2, already=0, stand_ins=3, forgotten=0)
    assert marks(database) == sorted([str(holding.id), str(diary.id)])
    assert sorted(woken) == ["Diary", "Letter"]


@no_type_check
async def test_a_head_already_marked_keeps_its_token_and_its_claim_and_twice_marks_once(
    database, woken
):
    from pangloss_cypher import pending
    from pangloss_reconcile.suggesting import Marked

    m = trigger_models()
    waiting = await letter(m, mention(), instructions={"suggest": True})
    other = await letter(m, mention())

    @backend.current().database().write_transaction
    async def claim(tx):
        return await pending.claim(tx, "reconcile", 5, 60.0)

    (claimed,) = await claim()
    assert claimed[0] == str(waiting.id)
    before = tokens(database)[str(waiting.id)]

    assert await marked_by() == Marked(marked=1, already=1, stand_ins=2)
    assert tokens(database)[str(waiting.id)] == before
    assert marks(database) == sorted([str(waiting.id), str(other.id)])
    assert woken == ["Letter"]

    marked_first = tokens(database)
    assert await marked_by() == Marked(marked=0, already=2, stand_ins=2)
    assert tokens(database) == marked_first
    # (nothing marked: nothing to wake)
    assert woken == ["Letter"]


@no_type_check
async def test_classes_narrow_it_to_those_and_the_classes_below_them(database):
    m = trigger_models()
    plain = await letter(m, mention())
    card = await letter(m, mention(), kind="Postcard")
    diary = await m.Diary.Create(label="a diary", about=[mention()]).save()

    done = await marked_by(classes=["Postcard"])
    assert (done.marked, marks(database)) == (1, [str(card.id)])

    done = await marked_by(classes=["Letter"])
    assert (done.marked, done.already) == (1, 1)
    assert marks(database) == sorted([str(plain.id), str(card.id)])

    done = await marked_by(classes=["Diary", "Letter"])
    assert (done.marked, done.already) == (1, 2)
    assert str(diary.id) in marks(database)


@no_type_check
async def test_a_class_that_can_hold_no_stand_in_or_no_class_is_refused_with_those_that_can(
    database,
):
    from pangloss_reconcile.suggesting import NotSuggestible

    m = trigger_models()
    await letter(m, mention())
    for asked in (["PlaceNote"], ["Nothing"], ["Letter", "Person"], ["Summary"]):
        with pytest.raises(NotSuggestible) as refused:
            await marked_by(classes=asked)
        assert "The classes that can: Diary, Letter, Postcard" in str(refused.value)
    assert marks(database) == []


@no_type_check
async def test_it_goes_in_pages_and_misses_no_head(database):
    from pangloss_reconcile import suggesting

    m = trigger_models()
    made = [str((await letter(m, mention(), mention())).id) for _ in range(5)]
    made.append(str((await m.Diary.Create(label="d", about=[mention()]).save()).id))
    pages = []
    real = suggesting.pending.mark_unmarked

    async def counted(tx, kind, heads, **options):
        pages.append(len(list(heads)))
        return await real(tx, kind, heads, **options)

    suggesting.pending.mark_unmarked = counted
    try:
        done = await suggesting.mark_stored(page=2)
    finally:
        suggesting.pending.mark_unmarked = real
    assert (done.marked, done.stand_ins) == (6, 11)
    assert marks(database) == sorted(made)
    assert pages == [2, 2, 2]


@no_type_check
async def test_with_two_classes_of_stand_in_the_pages_miss_no_head(database):
    """(a second class of stand-in, as an app may add one: its label read beside the first's, the page ending where
    the fuller of the two ends)"""
    from pangloss_reconcile import suggesting
    from pangloss_testing.similar_models import mention_stand_in

    stand_in = mention_stand_in()
    hooks.stand_ins.append(stand_in)
    try:
        m = trigger_models(mention=True)
        assert suggesting.stand_in_labels() == ["Mention", "Unreconciled"]
        other = {"type": "Mention", "label": "Jon", "mentioned_type": "Person"}
        made = [
            str((await letter(m, *to)).id)
            for to in (
                [mention()],
                [other],
                [other, mention()],
                [other, other],
                [mention()],
                [other],
            )
        ]
        done = await suggesting.mark_stored(page=1)
    finally:
        hooks.stand_ins.remove(stand_in)
    assert (done.marked, done.stand_ins) == (6, 8)
    assert marks(database) == sorted(made)


# ---------------------------------------------------------------------------
# Again, and what the worker then does
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_stand_in_tried_is_skipped_unless_again_forgets_it(
    database, monkeypatch
):
    from pangloss_reconcile import candidates

    m = worker_models()
    ids = await world(m, database)
    asked = []
    real = candidates.candidates_of

    async def counted(plan, **options):
        asked.append(sorted(options["only"]))
        return await real(plan, **options)

    monkeypatch.setattr(candidates, "candidates_of", counted)
    made = await factoid(m, ids, unknown(STRANGER))
    (stranger,) = stand_ins(database, made.id).values()
    await settle(database)
    assert await drained() == 1
    assert asked == [[stranger]]
    assert [row["stand_in"] for row in kept(database, "PGReconcileTried")] == [stranger]
    assert marks(database) == []

    # (without `again`: marked, and its stand-in skipped)
    done = await marked_by()
    assert (done.marked, done.forgotten) == (1, 0)
    assert await drained() == 1
    assert asked == [[stranger]]
    assert marks(database) == []

    # (with it: what was tried forgotten, and asked again)
    done = await marked_by(again=True)
    assert (done.marked, done.forgotten) == (1, 1)
    assert kept(database, "PGReconcileTried") == []
    assert await drained() == 1
    assert asked == [[stranger], [stranger]]


@no_type_check
async def test_after_a_bulk_load_nothing_is_marked_until_it_is_asked_and_a_drain_then_suggests(
    database,
):
    from pangloss_models.bulk_upload import upload

    m = worker_models()
    ids = await world(m, database)
    records = [
        (
            n,
            {
                "type": "Factoid",
                "label": f"loaded {n}",
                "statements": [
                    {
                        "type": "Meeting",
                        "label": "a meeting",
                        "by": {"type": "Person", "id": ids["Ada"]},
                        "met": [{"type": "Person", "id": ids["Ben"]}, unknown()],
                        "roles": [],
                        "notes": [],
                        "sure": [],
                    }
                ],
            },
        )
        for n in (1, 2)
    ]
    assert await upload(records, concurrency=1) == {"Factoid": 2}
    loaded = [
        row["id"]
        for row in run(
            database,
            "MATCH (h:Factoid) WHERE h.label STARTS WITH 'loaded' RETURN h.id AS id",
        )
    ]
    await settle(database)
    assert marks(database) == []

    done = await marked_by()
    assert (done.marked, done.already) == (2, 0)
    assert marks(database) == sorted(loaded)
    assert await drained() == 2
    assert marks(database) == []
    for head in loaded:
        (suggested,) = suggestions(database, head)
        assert suggested["p"]["text"] == "Jon Smyth"


# ---------------------------------------------------------------------------
# The status
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_status_counts_what_waits_what_was_tried_and_what_is_suggested(
    database,
):
    from pangloss_reconcile.suggesting import status

    m = worker_models()
    ids = await world(m, database)
    await factoid(m, ids)
    await settle(database)
    found = await status()
    assert (found["pending"], found["claimed"], found["tried"], found["suggested"]) == (
        1,
        0,
        0,
        0,
    )
    assert found["lease"] is None

    assert await drained() == 1
    found = await status()
    # (Jon Smyth suggested, the stranger tried and left)
    assert (found["pending"], found["tried"], found["suggested"]) == (0, 1, 1)
    assert found["waiting_for_vectors"] == 0 and found["rebuilding"] is False


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


class MadeWhenFirstAsked:
    """The app, made at its first request: after the test has declared its models"""

    def __init__(self) -> None:
        self.app: Any = None

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        from pangloss_api import create_app

        if self.app is None:
            self.app = create_app()
        await self.app(scope, receive, send)


async def bearer(client, username: str, admin: bool) -> dict:
    await service.create_user(
        username, f"{username}@example.com", PASSWORD, admin=admin
    )
    response = await client.post(
        "/api/users/token", data={"username": username, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@no_type_check
async def test_the_route_is_for_admins_and_answers_what_it_marked_and_the_status(
    database,
):
    m = trigger_models()
    plain = await letter(m, mention(), mention())
    card = await letter(m, mention(), kind="Postcard")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=MadeWhenFirstAsked()),
        base_url="http://test",
    ) as client:
        # (not logged in, and not an admin)
        assert (await client.post(ROUTE, json={})).status_code == 401
        assert (await client.get(ROUTE)).status_code == 401
        someone = await bearer(client, "ann", admin=False)
        assert (await client.post(ROUTE, json={}, headers=someone)).status_code == 403
        assert (await client.get(ROUTE, headers=someone)).status_code == 403
        assert marks(database) == []

        root = await bearer(client, "root", admin=True)
        narrowed = await client.post(
            ROUTE, json={"classes": ["Postcard"]}, headers=root
        )
        assert narrowed.status_code == 200, narrowed.text
        assert narrowed.json() == {
            "marked": 1,
            "already": 0,
            "standIns": 1,
            "forgotten": 0,
        }
        assert marks(database) == [str(card.id)]

        # (no body: every class)
        every = await client.post(ROUTE, headers=root)
        assert every.json() == {
            "marked": 1,
            "already": 1,
            "standIns": 3,
            "forgotten": 0,
        }
        again = await client.post(ROUTE, json={"again": True}, headers=root)
        assert again.json() == {
            "marked": 0,
            "already": 2,
            "standIns": 3,
            "forgotten": 0,
        }
        assert marks(database) == sorted([str(plain.id), str(card.id)])

        refused = await client.post(
            ROUTE, json={"classes": ["PlaceNote"]}, headers=root
        )
        assert refused.status_code == 422
        assert (
            "The classes that can: Diary, Letter, Postcard" in refused.json()["detail"]
        )

        answer = await client.get(ROUTE, headers=root)
        assert answer.status_code == 200
        given = answer.json()
        assert {k: given[k] for k in ("pending", "claimed", "tried", "suggested")} == {
            "pending": 2,
            "claimed": 0,
            "tried": 0,
            "suggested": 0,
        }
        assert set(given) == {
            "pending",
            "claimed",
            "oldest",
            "waitingForVectors",
            "rebuilding",
            "profile",
            "lease",
            "tried",
            "suggested",
        }


# ---------------------------------------------------------------------------
# The admin job
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_admin_job_marks_every_class_with_its_counts(database, tmp_path):
    from pangloss_admin.kinds import job_kinds
    from pangloss_admin.runner import run_job
    from pangloss_admin.store import JobStore

    m = trigger_models()
    made = [
        str((await letter(m, mention())).id),
        str((await letter(m, mention(), kind="Postcard")).id),
    ]
    kinds = job_kinds(["pangloss_reconcile"])
    assert kinds["reconcile_suggest"].describe() == {
        "name": "reconcile_suggest",
        "options": [{"name": "again", "type": "flag", "default": False}],
    }
    jobs = JobStore(tmp_path / "jobs")

    job = jobs.create("reconcile_suggest", {"again": False}, "me")
    await run_job(jobs, job["id"], kinds)
    done = jobs.read(job["id"])
    assert done["state"] == "finished", done
    assert done["counts"] == {"marked": 2, "already": 0, "stand_ins": 2, "forgotten": 0}
    assert marks(database) == sorted(made)

    job = jobs.create("reconcile_suggest", {"again": True}, "me")
    await run_job(jobs, job["id"], kinds)
    assert jobs.read(job["id"])["counts"] == {
        "marked": 0,
        "already": 2,
        "stand_ins": 2,
        "forgotten": 0,
    }
