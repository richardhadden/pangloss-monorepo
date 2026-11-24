"""The worker that suggests (`suggesting.py`; step 10.5d of implementation_docs/similarity-build-plan.md), on the
backend under test.

On models of the test (review's `Unreconciled` for people, the library's identifications): a reviewed factoid of
meetings, each of whose fields takes something else in a stand-in's place (`met` an identification over alternatives,
`witness` one of one person, `by` neither, `roles` an identification inside an `InRole`, `notes` a nested document
of its own, `sure` an identification by way of an edge of its own); the world of the candidates' tests (two Jon
Smyths in different company, one who met Ada and Ben, one Cy and Dee), every part built. What is claimed: what the
worker writes, as whom, once, and where it leaves things alone; what it keeps; when it waits; its lease; its
command."""

import asyncio
import contextlib
import importlib
import json
import logging
from types import SimpleNamespace
from typing import Any, no_type_check
from uuid import UUID

import pangloss_core.settings as core_settings
import pytest
import pytest_asyncio
from pangloss_core import backend
from pangloss_models import hooks
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, load
from pangloss_testing.live import apply_changes, run
from pangloss_testing.parts import drop_vector_indexes, one_turn
from pangloss_users import service

pytestmark = pytest.mark.asyncio(loop_scope="session")

NAME = "Jon Smyth"
STRANGER = "Xavier Quux"
TOOLCHAIN = "pangloss-reconcile"


@pytest.fixture
def database(db_driver, clear_database):
    """(the database emptied, and the vector indexes the tests made dropped, before and after)"""
    drop_vector_indexes(db_driver)
    yield db_driver
    drop_vector_indexes(db_driver)


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def structure(database):
    """The package's migrations applied, as `pangloss migrate` would (the test database is set up without the
    structure of installed apps)"""
    for name in ["0001_initial", "0002_models", "0003_suggested"]:
        migration = load("pangloss_reconcile", name)
        await apply_changes(
            backend.current().database(), EMPTY_SNAPSHOT, list(migration.changes)
        )


@pytest.fixture
def setting(monkeypatch):
    def set_to(name: str, value: Any) -> None:
        monkeypatch.setattr(core_settings.SETTINGS, name, value)

    return set_to


@pytest.fixture(autouse=True)
def a_new_worker(monkeypatch):
    """This process's worker made again for each test (its numbers start at nothing)"""
    from pangloss_reconcile import suggesting

    monkeypatch.setattr(suggesting, "worker", suggesting.Worker())
    return suggesting.worker


# ---------------------------------------------------------------------------
# The models and the world
# ---------------------------------------------------------------------------


@pytest.fixture
def not_by_people():
    """`Kept` is a class an app says it alone writes, while the test runs"""

    def found(model):
        return model.__name__ == "Kept"

    hooks.not_written_by_people.append(found)
    yield
    hooks.not_written_by_people.remove(found)


@no_type_check
def worker_models(more=None):
    """The models of the test, by name; and those `more(library, declared)` declares (by name) before `initialise()`,
    `declared` the test's classes declared so far, by name"""
    import pangloss_criteria.models
    import pangloss_library.models
    import pangloss_review.models
    from pangloss_derived import DerivedDocument, DerivedFrom
    from pangloss_models import (
        Cites,
        Document,
        EdgeModel,
        Entity,
        ModelRegistry,
        ReifiedRelation,
        ViaEdge,
        initialise,
        update_validator,
    )
    from pangloss_review import ReviewMeta

    ModelRegistry._reset()
    # (the registry was reset, and a module is only run once: the packages' models are declared again)
    importlib.reload(pangloss_library.models)
    importlib.reload(pangloss_criteria.models)
    importlib.reload(pangloss_review.models)
    library = pangloss_library.models
    Identification = library.Identification
    Alternatives = library.WeightedAlternative
    reviewed = ReviewMeta(reviewable=True)

    class Person(Entity):
        _review_meta = ReviewMeta(allow_unreconciled=True)

    class Certainty(EdgeModel):
        certain: bool

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Note(Document):
        _meta = Document.Meta(create_directly=False)
        about: Person | Identification[Alternatives[Person]]

    class Meeting(Document):
        _meta = Document.Meta(create_directly=False)
        # (neither: a stand-in, or a person)
        by: Person
        # (an identification over alternatives)
        met: list[Person | Identification[Alternatives[Person]]]
        # (an identification of one person)
        witness: Person | Identification[Person] | None = None
        roles: list[InRole[Person | Identification[Alternatives[Person]]]]
        notes: list[Note]
        sure: list[
            ViaEdge[Person, Certainty]
            | ViaEdge[Identification[Alternatives[Person]], Certainty]
        ]

    class Factoid(Document):
        _review_meta = reviewed
        statements: list[Meeting]

        @update_validator
        def not_unplannable(self):
            if self.label == "Unplannable":
                raise ValueError("label: no longer taken")

        @update_validator
        def takes_no_suggestion_when_it_says_so(self):
            # (a validator of the head that refuses its update with a suggestion in it: `test_reconcile_judge_live`)
            if self.label == "Takes no suggestion" and any(
                getattr(item, "identified_by", None) is not None
                for statement in self.statements
                for item in statement.met
            ):
                raise ValueError("label: this one takes no suggestion")

        @update_validator
        def takes_no_suggestion_of_the_stranger_when_it_says_so(self):
            # (a validator of the head that refuses an identification in one place only, the stranger's:
            # `test_reconcile_judge_live`)
            if self.label == "Not the stranger" and any(
                getattr(item, "identified_by", None) is not None
                and getattr(item, "text", None) == STRANGER
                for statement in self.statements
                for item in statement.met
            ):
                raise ValueError("label: the stranger is not to be identified here")

    class Gift(Document):
        _meta = Document.Meta(label_template="{given_by} gave to {given_to}")
        _review_meta = reviewed
        given_by: Person
        given_to: Person | Identification[Alternatives[Person]]

    class Source(Document):
        _review_meta = reviewed
        evidence: list[Cites[Meeting]]

    class Summary(Document, DerivedDocument):
        sources: list[DerivedFrom[Factoid]]
        statements: list[Meeting]

    class Kept(Document):
        _review_meta = reviewed
        statements: list[Meeting]

    # (an entity that can hold a stand-in: no document a person reviews)
    class Household(Entity):
        members: list[InRole[Person | Identification[Alternatives[Person]]]]

    declared = SimpleNamespace(
        **{k: v for k, v in locals().items() if isinstance(v, type)}
    )
    extra = more(library, declared) if more is not None else {}
    initialise()
    return SimpleNamespace(
        **{k: v for k, v in locals().items() if isinstance(v, type)}, **extra
    )


def ref(id: Any, kind: str = "Person") -> dict[str, str]:
    return {"type": kind, "id": str(id)}


def unknown(label: str = NAME, **more: Any) -> dict[str, Any]:
    return {
        "type": "Unreconciled",
        "label": label,
        "unreconciled_type": "Person",
        **more,
    }


def meeting(by: Any, met: list[Any], **more: Any) -> dict[str, Any]:
    return {
        "type": "Meeting",
        "label": "a meeting",
        "by": by,
        "met": met,
        "roles": [],
        "notes": [],
        "sure": [],
        **more,
    }


@no_type_check
async def world(m, db_driver) -> dict[str, str]:
    """Ada, Ben, Cy and Dee; Jon Smyth who met Ada and Ben (twice), and Jon Smyth who met Cy and Dee (twice), all
    published; every part built and the marks of the writes worked off: the ids by name (`jon`, `namesake`)"""
    from pangloss_vectors.rebuild import rebuild

    ids = {}
    for name in ["Ada", "Ben", "Cy", "Dee"]:
        ids[name] = str((await m.Person.Create(label=name).save()).id)
    ids["jon"] = str((await m.Person.Create(label=NAME).save()).id)
    ids["namesake"] = str((await m.Person.Create(label=NAME).save()).id)
    for jon, (first, second) in [("jon", ("Ada", "Ben")), ("namesake", ("Cy", "Dee"))]:
        for n in range(2):
            await m.Factoid.Create(
                label=f"{jon} {n}",
                statements=[
                    meeting(ref(ids[jon]), [ref(ids[first]), ref(ids[second])])
                ],
            ).save(published=True)
    await rebuild()
    await one_turn(db_driver)
    return ids


async def settle(db_driver) -> None:
    """The other workers' marks worked off (the vectors', the criteria's, the derived): what the worker waits for"""
    await one_turn(db_driver)


def marks(db_driver, kind: str = "reconcile") -> list[str]:
    return sorted(
        row["head"]
        for row in run(
            db_driver,
            "MATCH (p:PGPending {kind: $kind}) RETURN p.head_id AS head",
            kind=kind,
        )
    )


def counts(db_driver) -> tuple[int, int]:
    """The nodes and the edges (not the marks: a worker takes its own away)"""
    return (
        run(db_driver, "MATCH (n) WHERE NOT n:PGPending RETURN count(n) AS n")[0]["n"],
        run(db_driver, "MATCH ()-[r]->() RETURN count(r) AS n")[0]["n"],
    )


def versions(db_driver) -> dict[str, int]:
    return {
        row["id"]: row["version"]
        for row in run(
            db_driver,
            "MATCH (h:HeadNode) RETURN h.id AS id, "
            "size([(h)<-[:is_update_of]-(u:PGUpdate) | u]) + 1 AS version",
        )
    }


async def drained() -> int:
    from pangloss_reconcile.suggesting import drain

    return await drain()


@pytest.fixture
def history(tmp_path, monkeypatch):
    """`start()`: history recording the writes made from now on (its store given)"""
    from pangloss_history import listener
    from pangloss_history.store import SqliteStore

    path = tmp_path / "h.sqlite3"

    def start():
        settings = core_settings.SETTINGS

        class WithHistory:
            """The settings of the test, and those of history"""

            HISTORY_DB_PATH = str(path)
            HISTORY_BATCH_MS = 1

            def __getattr__(self, name):
                return getattr(settings, name)

        monkeypatch.setattr(core_settings, "SETTINGS", WithHistory(), raising=False)
        listener.reset_recorder()
        listener.install()
        return SqliteStore(path)

    yield start
    listener.reset_recorder()
    hooks.after_write[:] = [h for h in hooks.after_write if h is not listener.on_write]


def stand_ins(db_driver, head: Any) -> dict[str, str]:
    """The ids of the stand-ins of a head, by label"""
    return {
        row["label"]: row["id"]
        for row in run(
            db_driver,
            "MATCH (u:Unreconciled {head_node_id: $head}) RETURN u.id AS id, u.label AS label",
            head=str(head),
        )
    }


def suggestions(db_driver, head: Any) -> list[dict[str, Any]]:
    return run(
        db_driver,
        "MATCH (s:IdentificationByToolchainFromText {head_node_id: $head}) RETURN properties(s) AS p",
        head=str(head),
    )


def kept(db_driver, label: str = "PGReconcileSuggested") -> list[dict[str, Any]]:
    return [
        row["p"]
        for row in run(db_driver, f"MATCH (n:{label}) RETURN properties(n) AS p")
    ]


def unwritten(db_driver) -> tuple[int, int]:
    """The nodes and edges of the data (not the marks, the worker's lease, nor the users: the toolchain is made at the
    first batch)"""
    return (
        run(
            db_driver,
            "MATCH (n) WHERE NOT (n:PGPending OR n:PGReconcileWorker OR n:PGUser) RETURN count(n) AS n",
        )[0]["n"],
        run(db_driver, "MATCH ()-[r]->() RETURN count(r) AS n")[0]["n"],
    )


@no_type_check
async def factoid(m, ids, *met: Any, published: bool | None = None, **more: Any):
    """Ada met Ben and these (by default Jon Smyth and a stranger, neither identified): saved, saying `suggest=true`"""
    options = {"instructions": {"suggest": True}}
    if published is not None:
        options["published"] = published
    return await m.Factoid.Create(
        label=more.pop("label", "Ada met Ben and Jon"),
        statements=[
            meeting(
                ref(ids["Ada"]),
                [ref(ids["Ben"]), *(met or [unknown(), unknown(STRANGER)])],
                **more,
            )
        ],
    ).save(**options)


def percents(target: Any) -> list[tuple[str, int]]:
    (alternative,) = target
    return [(str(a.id), a.edge_properties.percent) for a in alternative.alternatives]


# ---------------------------------------------------------------------------
# What it writes
# ---------------------------------------------------------------------------


@no_type_check
async def test_two_mentions_one_decided_give_one_update_by_the_toolchain_and_the_other_left_as_it_was(
    database, history
):
    from pangloss_history import listener
    from pangloss_review import identify

    m = worker_models()
    ids = await world(m, database)
    store = history()
    made = await factoid(
        m, ids, unknown(uris=["http://example.org/jon"]), unknown(STRANGER)
    )
    mentions = stand_ins(database, made.id)
    await settle(database)
    before = versions(database)

    assert await drained() == 1

    after = versions(database)
    assert after[str(made.id)] == before[str(made.id)] + 1
    # (no entity, nor any other head, was written)
    assert {k: v for k, v in after.items() if k != str(made.id)} == {
        k: v for k, v in before.items() if k != str(made.id)
    }
    view = await m.Factoid.get(made.id)
    _, suggested, stranger = view.statements[0].met
    assert suggested.type == "IdentificationByToolchainFromText"
    assert str(suggested.id) != mentions[NAME]
    assert (suggested.text, [str(u) for u in suggested.uris]) == (
        NAME,
        ["http://example.org/jon"],
    )
    assert (suggested.identified_by, suggested.toolchain_version) == (
        TOOLCHAIN,
        "profile who",
    )
    shares = percents(suggested.target)
    assert shares[0][0] == ids["jon"]
    assert sum(percent for _, percent in shares) == 100
    assert (stranger.type, str(stranger.id), stranger.label) == (
        "Unreconciled",
        mentions[STRANGER],
        STRANGER,
    )
    assert marks(database) == []
    assert view.meta.updated_by == TOOLCHAIN
    assert view.meta.published is False
    # (the toolchain was made, a toolchain)
    assert (await service.get_user(TOOLCHAIN)).kind == "toolchain"
    # (history has one version more, by the toolchain)
    listener.get_recorder().drain()
    written = store.versions(made.id)
    assert [(r.version, r.who) for r in written][-1] == (2, TOOLCHAIN)
    # (review lists it, with the text the source wrote)
    listed = await identify.list_suggestions()
    assert [(str(s.id), s.text, s.identified_by) for s in listed.results] == [
        (str(suggested.id), NAME, TOOLCHAIN)
    ]


@no_type_check
async def test_a_field_over_alternatives_takes_them_all_one_of_one_entity_the_best_and_one_of_neither_is_left(
    database, setting
):
    m = worker_models()
    ids = await world(m, database)
    # (both Jon Smyths among the alternatives)
    setting("RECONCILE_SUGGEST_WITHIN", 0.0)
    made = await m.Factoid.Create(
        label="Ada met Ben and Jon, and Jon met them",
        statements=[
            meeting(ref(ids["Ada"]), [ref(ids["Ben"]), unknown()], witness=unknown()),
            meeting(unknown(), [ref(ids["Ada"]), ref(ids["Ben"])]),
        ],
    ).save(instructions={"suggest": True})
    mentions = run(
        database,
        "MATCH (m:Meeting {head_node_id: $head})-[e]->(u:Unreconciled) WHERE NOT coalesce(e.reverse, false) "
        "RETURN type(e) AS field, u.id AS id",
        head=str(made.id),
    )
    by = next(row["id"] for row in mentions if row["field"] == "by")
    await settle(database)

    assert await drained() == 1

    meeting_, other = (await m.Factoid.get(made.id)).statements
    alternatives = percents(meeting_.met[1].target)
    assert {id for id, _ in alternatives} == {ids["jon"], ids["namesake"]}
    assert alternatives[0][0] == ids["jon"]
    assert sum(percent for _, percent in alternatives) == 100
    assert meeting_.witness.type == "IdentificationByToolchainFromText"
    assert [str(t.id) for t in meeting_.witness.target] == [ids["jon"]]
    # (`by` takes no identification: the stand-in stays, and is noted as tried; the two replaced are noted too, with
    # their suggestions' ids)
    assert (other.by.type, str(other.by.id)) == ("Unreconciled", by)
    tried = {
        row["stand_in"]: row.get("suggested")
        for row in kept(database, "PGReconcileTried")
    }
    assert tried[by] is None
    assert sorted(v for k, v in tried.items() if k != by) == sorted(
        str(s.id) for s in (meeting_.met[1], meeting_.witness)
    )


@no_type_check
async def test_a_mention_inside_a_wrapper_in_a_nested_document_and_by_an_edge_of_its_own_is_suggested_with_the_edge_kept(
    database,
):
    m = worker_models()
    ids = await world(m, database)
    made = await factoid(
        m,
        ids,
        ref(ids["Dee"]),
        roles=[{"type": "InRole", "role": "guest", "target": [unknown()]}],
        notes=[{"type": "Note", "label": "a note", "about": unknown()}],
        sure=[unknown(edge_properties={"certain": True})],
    )
    await settle(database)

    assert await drained() == 1

    meeting_ = (await m.Factoid.get(made.id)).statements[0]
    (role,) = meeting_.roles
    (in_role,) = role.target
    assert (role.type, role.role, in_role.type, in_role.text) == (
        "InRole",
        "guest",
        "IdentificationByToolchainFromText",
        NAME,
    )
    assert meeting_.notes[0].about.type == "IdentificationByToolchainFromText"
    (sure,) = meeting_.sure
    assert sure.type == "IdentificationByToolchainFromText"
    assert sure.edge_properties.certain is True
    assert len(suggestions(database, made.id)) == 3


@no_type_check
async def test_the_label_of_a_head_made_from_the_field_keeps_the_name_the_source_wrote(
    database, setting
):
    """(point 11: the library's suggestion reads, in the label of what holds it, as its `text`)"""
    m = worker_models()
    ids = await world(m, database)
    setting("RECONCILE_SUGGEST_ABOVE", 0.2)
    made = await m.Gift.Create(
        given_by=ref(ids["Ada"]), given_to=unknown("Jon Smith")
    ).save(instructions={"suggest": True})
    assert (await m.Gift.get(made.id)).label == "Ada gave to Jon Smith"
    await settle(database)

    assert await drained() == 1

    view = await m.Gift.get(made.id)
    assert view.given_to.type == "IdentificationByToolchainFromText"
    assert [a.label for a in view.given_to.target[0].alternatives][0] == NAME
    assert view.label == "Ada gave to Jon Smith"


@no_type_check
async def test_more_mentions_than_are_asked_about_at_once_are_asked_in_groups_and_written_in_one_update(
    database, setting, monkeypatch
):
    from pangloss_reconcile import candidates

    m = worker_models()
    ids = await world(m, database)
    setting("RECONCILE_MOST_UNKNOWNS", 2)
    asked = []
    real = candidates.candidates_of

    async def counted(plan, **options):
        asked.append(sorted(options["only"]))
        return await real(plan, **options)

    monkeypatch.setattr(candidates, "candidates_of", counted)
    made = await factoid(m, ids, *[unknown() for _ in range(5)])
    await settle(database)
    before = versions(database)[str(made.id)]

    assert await drained() == 1

    assert [len(group) for group in asked] == [2, 2, 1]
    assert versions(database)[str(made.id)] == before + 1
    assert len(suggestions(database, made.id)) == 5


# ---------------------------------------------------------------------------
# What it leaves alone
# ---------------------------------------------------------------------------


async def left_alone(db_driver, caplog, why: str) -> None:
    """A drain that writes nothing of the data, takes the mark away, and says why at info"""
    before, heads = unwritten(db_driver), versions(db_driver)
    with caplog.at_level(logging.INFO, logger="pangloss.reconcile.worker"):
        assert await drained() == 1
    assert unwritten(db_driver) == before
    assert versions(db_driver) == heads
    assert marks(db_driver) == []
    assert any(
        "is left alone" in record.getMessage() and why in record.getMessage()
        for record in caplog.records
    ), [record.getMessage() for record in caplog.records]


async def mark(head: Any) -> None:
    """A mark of the kind, as a trigger would leave it (for a head no write of which is marked)"""
    from pangloss_cypher import pending

    @backend.current().database().write_transaction
    async def write(tx):
        await pending.mark(tx, "reconcile", [str(head)])

    await write()


@no_type_check
async def test_a_published_document_is_left_alone(database, caplog):
    m = worker_models()
    ids = await world(m, database)
    await factoid(m, ids, published=True)
    await settle(database)
    await left_alone(database, caplog, "published")


@no_type_check
async def test_a_document_cited_where_a_mention_would_change_is_left_alone(
    database, caplog
):
    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown())
    statement = (await m.Factoid.get(made.id)).statements[0]
    await m.Source.Create(
        label="the evidence", evidence=[{"type": "Meeting", "id": statement.id}]
    ).save()
    await settle(database)
    await left_alone(database, caplog, "cited")


@no_type_check
async def test_a_document_that_cannot_be_planned_is_left_alone(database, caplog):
    m = worker_models()
    ids = await world(m, database)
    await factoid(m, ids, label="Unplannable")
    await settle(database)
    await left_alone(database, caplog, "unplannable")


@no_type_check
async def test_a_derived_document_is_left_alone(database, caplog):
    from pangloss_derived.documents import writing_derived

    m = worker_models()
    ids = await world(m, database)
    source = await factoid(m, ids, published=True, label="the source")
    with writing_derived("a rule"):
        made = await m.Summary.Create(
            label="derived",
            sources=[ref(source.id, "Factoid")],
            statements=[meeting(ref(ids["Ada"]), [unknown()])],
        ).save()
    await settle(database)
    await database_marks_cleared(database)
    await mark(made.id)
    await left_alone(database, caplog, "not written by people")


async def database_marks_cleared(db_driver) -> None:
    """The marks the test's own writes left, taken away (the published source's)"""
    run(db_driver, "MATCH (p:PGPending {kind: 'reconcile'}) DELETE p")


@no_type_check
async def test_a_class_people_do_not_write_is_left_alone(
    database, caplog, not_by_people
):
    m = worker_models()
    ids = await world(m, database)
    made = await m.Kept.Create(
        label="kept", statements=[meeting(ref(ids["Ada"]), [unknown()])]
    ).save(instructions={"suggest": True})
    # (not marked by its write: it is no class the worker would touch)
    assert marks(database) == []
    await settle(database)
    await mark(made.id)
    await left_alone(database, caplog, "not written by people")


# ---------------------------------------------------------------------------
# Versions that move on, and nothing twice
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def as_person(db_driver, username: str = "ann"):
    from pangloss_users import current_request_username

    run(db_driver, "MERGE (:PGUser {username: $username})", username=username)
    token = current_request_username.set(username)
    try:
        yield
    finally:
        current_request_username.reset(token)


@pytest.fixture
def saved_meanwhile(monkeypatch, database):
    """`between(m, head, **save)`: the head saved by a person (its label changed) between the worker's read and its
    write, once (in `judged`, the step between the decision and the update)"""
    from pangloss_models import rewriting

    from pangloss_reconcile import suggesting

    def between(m, head, **save):
        done = []
        real = suggesting.judged

        async def judged(view, unknown, found, decision, **options):
            if not done:
                done.append(True)
                with as_person(database):
                    await rewriting.rewrite(
                        m.Factoid,
                        UUID(str(head)),
                        lambda data: ({**data, "label": "changed meanwhile"}, True),
                        **save,
                    )
            return await real(view, unknown, found, decision, **options)

        monkeypatch.setattr(suggesting, "judged", judged)
        return done

    return between


@no_type_check
async def test_a_version_that_moved_on_writes_nothing_keeps_the_mark_and_it_is_done_again(
    database, saved_meanwhile, a_new_worker
):
    """(the claim given back is claimed again at the next turn, in the same drain: so one drain does the head twice,
    the first time writing nothing)"""
    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown())
    await settle(database)
    done = saved_meanwhile(m, made.id)

    assert await drained() == 2

    assert done == [True]
    assert a_new_worker.stats.conflicts == 1
    assert a_new_worker.stats.updates == 1
    # (made, saved by the person, written by the worker once: on the person's version)
    assert versions(database)[str(made.id)] == 3
    view = await m.Factoid.get(made.id)
    assert view.label == "changed meanwhile"
    assert len(suggestions(database, made.id)) == 1
    assert len(kept(database)) == 1
    assert marks(database) == []


@pytest.fixture
def conflicted(monkeypatch):
    """The worker's update refused once as if the version had moved on (nothing written)"""
    from pangloss_models import PanglossVersionConflictError, rewriting

    real = rewriting.rewrite
    done = []

    async def rewrite(*args, **options):
        if not done:
            done.append(True)
            raise PanglossVersionConflictError("moved on", current_version=0)
        return await real(*args, **options)

    monkeypatch.setattr(rewriting, "rewrite", rewrite)
    return done


@no_type_check
async def test_a_conflict_gives_the_claim_back_with_the_mark_kept(
    database, conflicted, a_new_worker
):
    from pangloss_reconcile.suggesting import Worker

    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown())
    await settle(database)
    one = Worker()
    claimed = await one.claim()

    outcome = await one.process(claimed[0])

    assert outcome.what == "conflict"
    assert suggestions(database, made.id) == []
    assert kept(database) == []
    (claim,) = run(
        database,
        "MATCH (p:PGPending {kind: 'reconcile'}) RETURN p.head_id AS head, p.claimed_until AS until",
    )
    assert (claim["head"], claim["until"]) == (str(made.id), None)
    assert await drained() == 1
    assert len(suggestions(database, made.id)) == 1


@no_type_check
async def test_a_save_that_says_suggest_false_meanwhile_takes_the_mark_and_the_next_drain_does_nothing(
    database, saved_meanwhile
):
    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown())
    await settle(database)
    saved_meanwhile(m, made.id, instructions={"suggest": False})

    assert await drained() == 1

    assert marks(database) == []
    await settle(database)
    assert await drained() == 0
    assert suggestions(database, made.id) == []
    assert NAME in stand_ins(database, made.id)


@no_type_check
async def test_nothing_is_suggested_twice_by_two_drains_nor_by_two_workers_at_once(
    database,
):
    from pangloss_reconcile.suggesting import Worker

    m = worker_models()
    ids = await world(m, database)
    first = await factoid(m, ids, unknown())
    await settle(database)
    assert await drained() == 1
    assert await drained() == 0
    assert len(suggestions(database, first.id)) == 1
    assert len(kept(database)) == 1

    second = await factoid(m, ids, unknown())
    await settle(database)
    one, other = Worker(), Worker()
    claimed = await one.claim()
    assert [head for head, _ in claimed] == [str(second.id)]
    outcomes = await asyncio.gather(one.process(claimed[0]), other.process(claimed[0]))

    # (the second finds the version moved on, the mark gone in its own transaction, or the stand-in gone)
    assert sorted(outcome.what for outcome in outcomes) in (
        ["conflict", "written"],
        ["moved", "written"],
        ["nothing", "written"],
    )
    assert len(suggestions(database, second.id)) == 1
    assert len(kept(database)) == 2
    assert marks(database) == []


@no_type_check
async def test_its_own_update_leaves_no_mark_of_its_kind_and_a_mark_of_the_vectors(
    database,
):
    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown())
    await settle(database)

    assert await drained() == 1

    assert marks(database) == []
    assert str(made.id) in marks(database, "vectors")


# ---------------------------------------------------------------------------
# A stand-in tried
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_stand_in_tried_is_not_asked_again_at_a_later_save_and_is_once_the_decision_changes(
    database, setting, monkeypatch
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

    async def saved_again() -> None:
        view = await m.Factoid.get(made.id)
        await rewriting_save(m, view)
        await settle(database)

    await saved_again()
    assert marks(database) == [str(made.id)]
    assert await drained() == 1
    assert asked == [[stranger]]
    assert marks(database) == []

    # (a setting of the decision changed: asked again)
    setting("RECONCILE_SUGGEST_ABOVE", 0.95)
    await saved_again()
    assert await drained() == 1
    assert asked == [[stranger], [stranger]]


async def rewriting_save(m: Any, view: Any) -> None:
    """The document saved again as it is, saying `suggest=true`"""
    from pangloss_models.utils import editable

    await m.Factoid.Update(**editable(view.model_dump())).save(
        expected_version=view.meta.version, instructions={"suggest": True}
    )


# ---------------------------------------------------------------------------
# What sets a mark
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_setting_and_the_instruction_mark_on_create_and_update_and_false_takes_a_standing_mark_off(
    database, setting
):
    from pangloss_models import PanglossInstructionError
    from pangloss_models.utils import editable

    m = worker_models()
    ada = await m.Person.Create(label="Ada").save()

    async def created(**save) -> str:
        made = await m.Factoid.Create(
            label="a factoid", statements=[meeting(ref(ada.id), [unknown()])]
        ).save(**save)
        return str(made.id)

    async def updated(head: str, **save) -> None:
        view = await m.Factoid.get(UUID(head))
        await m.Factoid.Update(**editable(view.model_dump())).save(
            expected_version=view.meta.version, **save
        )

    def marked(head: str) -> bool:
        return head in marks(database)

    # (the setting off)
    assert not marked(await created())
    assert marked(await created(instructions={"suggest": True}))
    assert not marked(await created(instructions={"suggest": False}))
    head = await created(instructions={"suggest": "true"})
    await updated(head)
    assert marked(head), "a save that says nothing leaves a standing mark"
    await updated(head, instructions={"suggest": False})
    assert not marked(head)
    await updated(head, instructions={"suggest": True})
    assert marked(head)

    # (the setting on)
    setting("RECONCILE_SUGGEST_ON_SAVE", True)
    assert marked(await created())
    assert not marked(await created(instructions={"suggest": False}))
    head = await created(instructions={"suggest": False})
    await updated(head)
    assert marked(head)
    await updated(head, instructions={"suggest": False})
    assert not marked(head)

    # (a class that can hold no stand-in, and a value that is not one)
    person = await m.Person.Create(label="Bea").save(instructions={"suggest": True})
    assert not marked(str(person.id))
    with pytest.raises(PanglossInstructionError):
        await created(instructions={"suggest": "maybe"})


# ---------------------------------------------------------------------------
# Who it writes as
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_toolchain_that_is_a_person_or_disabled_is_refused_and_nothing_is_written(
    database,
):
    from pangloss_reconcile.suggesting import ToolchainRefused

    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown())
    await settle(database)
    before = unwritten(database)

    await service.create_user(TOOLCHAIN, "reconcile@example.com", "a long password")
    with pytest.raises(ToolchainRefused, match="a person"):
        await drained()
    assert unwritten(database) == before
    assert marks(database) == [str(made.id)]

    run(database, "MATCH (u:PGUser {username: $name}) DELETE u", name=TOOLCHAIN)
    await service.create_toolchain(TOOLCHAIN)
    await service.set_disabled(TOOLCHAIN, True)
    with pytest.raises(ToolchainRefused, match="disabled"):
        await drained()
    assert unwritten(database) == before
    assert marks(database) == [str(made.id)]

    # (enabled again, it writes; and the claim given back was claimed again at once)
    await service.set_disabled(TOOLCHAIN, False)
    assert await drained() == 1
    assert len(suggestions(database, made.id)) == 1


# ---------------------------------------------------------------------------
# What it keeps
# ---------------------------------------------------------------------------


@no_type_check
async def test_what_it_saw_is_kept_by_each_suggestion_s_id_none_for_a_stand_in_left_and_the_sweep_leaves_it_until_it_is_gone(
    database,
):
    from pangloss_models.utils import editable
    from pangloss_vectors import store

    from pangloss_reconcile import decisions

    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown(), unknown(STRANGER))
    mentions = stand_ins(database, made.id)
    await settle(database)
    assert await drained() == 1

    (suggested,) = suggestions(database, made.id)
    (row,) = kept(database)
    assert row["id"] == suggested["p"]["id"]
    assert (row["head"], row["stand_in"], row["shape"]) == (
        str(made.id),
        mentions[NAME],
        "alternatives",
    )
    assert "user" not in row
    rows = json.loads(row["rows"])
    assert rows and rows[0]["id"] == ids["jon"]
    assert all(
        set(r) == {"id", "type", "scores", "shared", "score", "displayed"} for r in rows
    )
    assert [r["id"] for r in rows if r["displayed"]][0] == ids["jon"]
    alternatives = json.loads(row["alternatives"])
    assert alternatives[0]["id"] == ids["jon"]
    assert sum(a["percent"] for a in alternatives) == 100
    today = decisions.today(await store.states())
    assert {name: row[name] for name in decisions.SIGNATURES} == today
    # (the stranger left: tried, not kept; Jon Smyth replaced: tried, with the suggestion's id)
    assert {
        r["stand_in"]: r.get("suggested") for r in kept(database, "PGReconcileTried")
    } == {mentions[STRANGER]: None, mentions[NAME]: row["id"]}

    # (the sweep leaves it, whatever its age, and Jon Smyth's tried row while the record of its suggestion names it,
    # though the stand-in is gone)
    run(
        database,
        "MATCH (s:PGReconcileSuggested) SET s.at = datetime('2001-01-01T00:00:00Z')",
    )
    await decisions.sweep()
    assert len(kept(database)) == 1
    assert len(kept(database, "PGReconcileTried")) == 2

    # (the suggestion edited away by a person, and the stranger with it: both go at the next sweep)
    view = await m.Factoid.get(made.id)
    data = editable(view.model_dump())
    data["statements"][0]["met"] = [ref(ids["Ben"]), ref(ids["jon"])]
    with as_person(database):
        await m.Factoid.Update(**data).save(expected_version=view.meta.version)
    await decisions.sweep()
    assert kept(database) == []
    assert kept(database, "PGReconcileTried") == []


# ---------------------------------------------------------------------------
# Waiting for the vectors, and the lease
# ---------------------------------------------------------------------------


@no_type_check
async def test_it_waits_for_older_marks_of_the_vectors_not_for_newer_ones_and_for_a_rebuild_in_hand(
    database,
):
    from pangloss_vectors.rebuild import LEASE

    from pangloss_reconcile.suggesting import pending_status

    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown())

    # (its write's vectors mark is older than its own: it waits, and says so)
    assert await drained() == 0
    status = await pending_status()
    assert (status["pending"], status["waiting_for_vectors"]) == (1, 1)
    assert marks(database) == [str(made.id)]

    # (only newer marks of the vectors: it does not wait)
    await settle(database)
    await m.Person.Create(label="Eve").save()
    assert str(made.id) not in marks(database, "vectors")
    assert (await pending_status())["waiting_for_vectors"] == 0

    # (a rebuild in hand: nothing is claimed)
    run(
        database,
        f"MERGE (l:{LEASE} {{key: 'rebuild'}}) SET l.holder = 'someone', l.until = $until",
        until=1e12,
    )
    assert (await pending_status())["rebuilding"] is True
    assert await drained() == 0
    assert marks(database) == [str(made.id)]
    run(database, f"MATCH (l:{LEASE} {{key: 'rebuild'}}) REMOVE l.holder, l.until")
    assert await drained() == 1
    assert len(suggestions(database, made.id)) == 1


@no_type_check
async def test_a_second_worker_does_not_run_beside_the_first_and_takes_a_lease_outlived(
    database,
):
    from pangloss_reconcile.suggesting import Settings, Worker, pending_status

    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown())
    await settle(database)
    one, other = Worker(), Worker(Settings(idle=0.05, paused=0.05))
    assert await one.take_lease()
    assert not await other.take_lease()
    assert (await pending_status())["lease"]["holder"] == one.id

    running = asyncio.create_task(other.run())
    try:
        await asyncio.sleep(0.5)
        assert marks(database) == [str(made.id)]
        # (the first's lease outlived: the second takes it, and works)
        run(database, "MATCH (w:PGReconcileWorker) SET w.until = 0")
        for _ in range(100):
            if not marks(database):
                break
            await asyncio.sleep(0.1)
        assert marks(database) == []
        assert len(suggestions(database, made.id)) == 1
        assert not await one.take_lease()
    finally:
        running.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await running


# ---------------------------------------------------------------------------
# What a write costs
# ---------------------------------------------------------------------------


@no_type_check
async def test_with_the_setting_off_a_write_costs_what_it_did_without_the_app_and_a_mark_one_statement_more(
    database,
):
    from pangloss_review import reconcile as review_reconcile
    from pangloss_testing.conformance.test_query_costs import recorded

    from pangloss_reconcile import marking

    m = worker_models()
    ada = await m.Person.Create(label="Ada").save()

    async def statements(**save) -> tuple[int, int]:
        # (what review does after a write, in the background, done first: it is not this write's)
        await review_reconcile.background_done()
        with recorded() as r:
            await m.Factoid.Create(
                label="a factoid", statements=[meeting(ref(ada.id), [unknown()])]
            ).save(**save)
        return r.transactions, len(r.statements)

    async def least(**save) -> tuple[int, int]:
        # (the least of three: a write in the background that a sleep does not wait for is not this write's)
        return min([await statements(**save) for _ in range(3)])

    with_app = await least()
    hooks.instructed_work.remove(marking.instructed)
    hooks.in_write.remove(marking.in_write)
    try:
        without = await least()
    finally:
        hooks.instructed_work.append(marking.instructed)
        hooks.in_write.append(marking.in_write)
    marked = await least(instructions={"suggest": True})

    assert with_app == without
    assert marked == (without[0], without[1] + 1)


@no_type_check
async def test_claims_are_taken_the_oldest_first_before_a_time_and_renewed_only_while_they_are_held(
    database,
):
    """(`pangloss_cypher.pending.claim(before=)` and `renew`, which the worker claims and keeps its claims by)"""
    import time

    from pangloss_cypher import pending

    db = backend.current().database()

    @db.write_transaction
    async def marked(tx, heads):
        await pending.mark(tx, "test-kind", heads)

    @db.write_transaction
    async def claimed(tx, before):
        return await pending.claim(tx, "test-kind", 10, 30.0, before=before)

    @db.write_transaction
    async def renewed(tx, held):
        return await pending.renew(tx, "test-kind", held, 300.0)

    await marked(["old"])
    await asyncio.sleep(0.05)
    between = time.time()
    await asyncio.sleep(0.05)
    await marked(["new"])

    held = await claimed(between)
    assert [head for head, _ in held] == ["old"]
    assert await renewed(held) == 1
    (until,) = run(
        database,
        "MATCH (p:PGPending {key: 'test-kind:old'}) RETURN p.claimed_until AS until",
    )
    assert until["until"] > time.time() + 200
    # (marked again: its claim is no longer the one held, and is not renewed)
    await marked(["old"])
    assert await renewed(held) == 0
    # (without a time: every one not claimed, "old" again since its claim went with its new mark)
    assert sorted(head for head, _ in await claimed(None)) == ["new", "old"]


@no_type_check
async def test_a_slow_head_keeps_its_claim_and_the_lease_while_it_is_worked(
    database, monkeypatch
):
    from pangloss_reconcile import suggesting
    from pangloss_reconcile.suggesting import Settings, Worker

    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown())
    await settle(database)
    one, other = Worker(Settings(lease=0.4)), Worker(Settings(lease=0.4))
    real = suggesting.judged

    async def slowly(*args, **options):
        # (longer than the lease: renewed meanwhile, the claim is not taken by another)
        await asyncio.sleep(1.2)
        assert await other.claim() == []
        assert not await other.take_lease()
        return await real(*args, **options)

    monkeypatch.setattr(suggesting, "judged", slowly)
    assert await one.take_lease()

    assert await one.process_batch() == 1

    assert len(suggestions(database, made.id)) == 1


# ---------------------------------------------------------------------------
# The mends of the second reading (implementation_docs/similarity-build-plan.md, "10.5d and 10.5c read a second time")
# ---------------------------------------------------------------------------


@pytest.fixture
def meanwhile(monkeypatch):
    """`meanwhile(work)`: `work()` done once between the worker's decision and its update (in `judged`)"""
    from pangloss_reconcile import suggesting

    def between(work):
        done = []
        real = suggesting.judged

        async def judged(view, unknown, found, decision, **options):
            if not done:
                done.append(True)
                await work()
            return await real(view, unknown, found, decision, **options)

        monkeypatch.setattr(suggesting, "judged", judged)
        return done

    return between


@no_type_check
async def test_a_document_published_between_the_read_and_the_write_is_left_as_a_published_one(
    database, caplog, meanwhile
):
    """(mend 1: the check is in the update's own transaction; publishing changes no version)"""
    from pangloss_cypher.write_functions import set_review_status_in_db

    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown())
    await settle(database)

    async def published():
        await set_review_status_in_db(made.id, "published", True, "ann")

    done = meanwhile(published)

    await left_alone(database, caplog, "published")

    assert done == [True]
    assert suggestions(database, made.id) == []
    assert kept(database) == [] and kept(database, "PGReconcileTried") == []
    assert (await m.Factoid.get(made.id)).meta.published is True


@no_type_check
async def test_a_save_that_says_suggest_false_after_the_claim_and_before_the_read_writes_nothing(
    database, caplog
):
    """(mend 2: the worker reads the person's version, and its mark is gone: dropped, nothing completed)"""
    from pangloss_models import rewriting

    from pangloss_reconcile.suggesting import Worker

    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown())
    await settle(database)
    one = Worker()
    (claimed,) = await one.claim()
    with as_person(database):
        await rewriting.rewrite(
            m.Factoid,
            made.id,
            lambda data: ({**data, "label": "changed"}, True),
            instructions={"suggest": False},
        )
    before = versions(database)

    with caplog.at_level(logging.INFO, logger="pangloss.reconcile.worker"):
        outcome = await one.process(claimed)

    assert (outcome.what, outcome.why) == ("moved", "its mark was taken off meanwhile")
    assert versions(database) == before
    assert suggestions(database, made.id) == []
    assert kept(database) == [] and kept(database, "PGReconcileTried") == []
    assert marks(database) == []
    assert NAME in stand_ins(database, made.id)
    assert any("is dropped" in r.getMessage() for r in caplog.records)


@no_type_check
async def test_a_head_marked_again_by_the_trigger_with_again_while_it_is_claimed_is_done_again_not_taken_off(
    database,
):
    """(mends 1/2 with finding 7: `mark_stored(again=True)` gives a head that has a mark a new token; the claim of the
    old one writes nothing, and the new mark is not taken off by it)"""
    from pangloss_reconcile.suggesting import Worker, mark_stored

    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown())
    await settle(database)
    one = Worker()
    (claimed,) = await one.claim()
    (old,) = run(
        database,
        "MATCH (p:PGPending {kind: 'reconcile'}) RETURN p.token AS token, p.claimed_until AS until",
    )
    assert old["until"] is not None

    done = await mark_stored(again=True)

    (new,) = run(
        database,
        "MATCH (p:PGPending {kind: 'reconcile'}) RETURN p.token AS token, p.claimed_until AS until",
    )
    assert (done.marked, done.already) == (0, 1)
    assert new["token"] != old["token"] and new["until"] is None
    outcome = await one.process(claimed)
    assert (outcome.what, outcome.why) == ("moved", "it was marked again meanwhile")
    assert suggestions(database, made.id) == []
    assert marks(database) == [str(made.id)]
    # (the new mark is done as any)
    assert await drained() == 1
    assert len(suggestions(database, made.id)) == 1
    assert marks(database) == []


async def set_dimension(db_driver, more: int) -> None:
    run(
        db_driver,
        "MATCH (s:PGVectorProfile {profile: 'who'}) SET s.dimension = s.dimension + $more",
        more=more,
    )


@no_type_check
async def test_nothing_is_claimed_while_the_profile_is_not_built_or_a_rebuild_is_due_and_the_status_says_so(
    database,
):
    """(mend 3: before, the mark was completed with nothing done, and nothing was marked after the rebuild)"""
    from pangloss_reconcile.suggesting import pending_status, status, status_json

    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown())
    await settle(database)
    await set_dimension(database, 1)

    assert await drained() == 0

    assert marks(database) == [str(made.id)]
    found = await pending_status()
    assert found["profile"] == "rebuild_due"
    assert status_json(await status())["profile"] == "rebuild_due"
    assert kept(database, "PGReconcileTried") == []
    # (not built at all)
    run(
        database, "MATCH (s:PGVectorProfile {profile: 'who'}) SET s.profile = 'unbuilt'"
    )
    assert (await pending_status())["profile"] == "pending"
    assert await drained() == 0
    run(
        database, "MATCH (s:PGVectorProfile {profile: 'unbuilt'}) SET s.profile = 'who'"
    )
    await set_dimension(database, -1)
    assert (await pending_status())["profile"] == "ok"
    assert await drained() == 1
    assert len(suggestions(database, made.id)) == 1


@no_type_check
async def test_candidates_not_ok_inside_a_batch_keep_the_mark_and_write_and_note_nothing(
    database, monkeypatch, a_new_worker
):
    """(mend 3: the state changed under the batch)"""
    import dataclasses

    from pangloss_reconcile import suggesting

    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown(), unknown(STRANGER))
    await settle(database)
    real = suggesting._candidates
    done = []

    async def changed(plan, ids):
        found = await real(plan, ids)
        if not done:
            done.append(True)
            # (one of the two not ok: the whole head waits)
            found[-1] = dataclasses.replace(found[-1], status="pending", candidates=[])
        return found

    monkeypatch.setattr(suggesting, "_candidates", changed)

    # (the drain stops at it, and does not claim it again in the same drain)
    assert await drained() == 1

    assert suggestions(database, made.id) == []
    assert kept(database) == [] and kept(database, "PGReconcileTried") == []
    (claim,) = run(
        database,
        "MATCH (p:PGPending {kind: 'reconcile'}) RETURN p.claimed_until AS until",
    )
    assert claim["until"] is None
    assert a_new_worker.stats.waiting == 1
    assert await drained() == 1
    assert len(suggestions(database, made.id)) == 1


@no_type_check
async def test_a_head_that_fails_three_times_is_taken_as_refused_and_the_younger_ones_are_done(
    database, monkeypatch, caplog
):
    """(mend 4)"""
    from pangloss_reconcile import suggesting

    m = worker_models()
    ids = await world(m, database)
    failing = await factoid(m, ids, unknown(), label="the one that fails")
    younger = await factoid(m, ids, unknown(), label="the younger one")
    await settle(database)
    failing_ids = set(stand_ins(database, failing.id).values())
    real = suggesting._candidates

    async def candidates(plan, ids):
        if failing_ids & set(ids):
            raise RuntimeError("a bug")
        return await real(plan, ids)

    monkeypatch.setattr(suggesting, "_candidates", candidates)

    # (the younger one may be done before the failing one in a batch, whose order is the claim's: the failing one keeps
    # its mark until its third failure, and then the drain goes on)
    for _ in range(suggesting.FAILURES - 1):
        with pytest.raises(RuntimeError, match="a bug"):
            await drained()
        assert str(failing.id) in marks(database)
    with caplog.at_level(logging.ERROR, logger="pangloss.reconcile.worker"):
        await drained()

    assert marks(database) == []
    assert suggestions(database, failing.id) == []
    assert len(suggestions(database, younger.id)) == 1
    # (its stand-ins not noted as tried: asked again when it is next marked)
    assert not failing_ids & {r["stand_in"] for r in kept(database, "PGReconcileTried")}
    (record,) = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert "failed 3 times" in record.getMessage() and record.exc_info


@no_type_check
async def test_a_write_error_that_is_not_a_refusal_in_planning_makes_the_head_unplannable(
    database, caplog, monkeypatch
):
    """(mend 4, `stored.plan_of_view`: a `PanglossReferenceError`, as a citation an app cannot resolve now)"""
    from pangloss_cypher import citations
    from pangloss_models import PanglossReferenceError

    m = worker_models()
    ids = await world(m, database)
    await factoid(m, ids, unknown())
    await settle(database)

    async def unresolvable(instance):
        raise PanglossReferenceError("what it cites cannot be resolved now")

    monkeypatch.setattr(citations, "resolve", unresolvable)
    await left_alone(database, caplog, "unplannable")


@pytest.fixture
def refused(monkeypatch):
    """The worker's update refused (by a `@before_update`, say)"""
    from pangloss_models import PanglossWriteRefused, rewriting

    async def rewrite(*args, **options):
        raise PanglossWriteRefused("not today")

    monkeypatch.setattr(rewriting, "rewrite", rewrite)


@no_type_check
async def test_a_refused_update_notes_as_tried_only_the_stand_ins_left_for_a_reason_of_their_own(
    database, refused
):
    """(mend 5)"""
    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown(), unknown(STRANGER))
    mentions = stand_ins(database, made.id)
    await settle(database)

    assert await drained() == 1

    assert marks(database) == []
    assert [r["stand_in"] for r in kept(database, "PGReconcileTried")] == [
        mentions[STRANGER]
    ]


@no_type_check
async def test_a_suggestion_undone_by_a_restore_is_not_written_again_and_the_sweep_keeps_what_says_so(
    database, history, setting
):
    """(mend 6: a person who restores the version before the worker's rejects its suggestion)"""
    from pangloss_history import listener
    from pangloss_history.restore import restore

    from pangloss_reconcile import decisions

    m = worker_models()
    ids = await world(m, database)
    store = history()
    setting("RECONCILE_SUGGEST_ON_SAVE", True)
    made = await factoid(m, ids, unknown())
    mentions = stand_ins(database, made.id)
    await settle(database)
    assert await drained() == 1
    assert len(suggestions(database, made.id)) == 1
    # (the stand-in is gone; its tried row stays while the record of its suggestion names it)
    await decisions.sweep()
    assert [r["stand_in"] for r in kept(database, "PGReconcileTried")] == [
        mentions[NAME]
    ]

    listener.get_recorder().drain()
    with as_person(database):
        await restore(store, m.Factoid, made.id, 1)
    # (back with its old id, and marked by the save, the setting on)
    assert stand_ins(database, made.id) == mentions
    assert marks(database) == [str(made.id)]
    await settle(database)
    before = versions(database)[str(made.id)]

    assert await drained() == 1

    assert versions(database)[str(made.id)] == before
    assert suggestions(database, made.id) == []
    assert marks(database) == []
    # (the stand-in is a node again: the record of the suggestion goes, the tried row stays)
    await decisions.sweep()
    assert kept(database) == []
    assert [r["stand_in"] for r in kept(database, "PGReconcileTried")] == [
        mentions[NAME]
    ]


@no_type_check
async def test_a_stand_in_tried_where_its_place_takes_no_suggestion_is_asked_again_once_moved_to_one_that_does(
    database, monkeypatch
):
    """(mend 7: the digest holds where the stand-in sits and the shape found)"""
    from pangloss_models.utils import editable

    from pangloss_reconcile import candidates

    m = worker_models()
    ids = await world(m, database)
    asked = []
    real = candidates.candidates_of

    async def counted(plan, **options):
        asked.append(sorted(options["only"]))
        return await real(plan, **options)

    monkeypatch.setattr(candidates, "candidates_of", counted)
    made = await m.Factoid.Create(
        label="Jon met Ada and Ben",
        statements=[meeting(unknown(), [ref(ids["Ada"]), ref(ids["Ben"])])],
    ).save(instructions={"suggest": True})
    (jon,) = stand_ins(database, made.id).values()
    await settle(database)
    assert await drained() == 1
    # (its place, `by`, takes no suggestion: not asked, noted as tried)
    assert asked == []
    assert [r["stand_in"] for r in kept(database, "PGReconcileTried")] == [jon]

    # (moved, its id kept, from `by` to `met`, which takes one)
    view = await m.Factoid.get(made.id)
    data = editable(view.model_dump())
    statement = data["statements"][0]
    statement["met"], statement["by"] = (
        [*statement["met"], statement["by"]],
        ref(ids["Dee"]),
    )
    await m.Factoid.Update(**data).save(
        expected_version=view.meta.version, instructions={"suggest": True}
    )
    assert stand_ins(database, made.id) == {NAME: jon}
    await settle(database)

    assert await drained() == 1

    assert asked == [[jon]]


@no_type_check
async def test_an_entity_that_can_hold_a_stand_in_is_not_marked_and_a_mark_left_on_one_is_completed(
    database, caplog
):
    """(mend 8: an entity is no document a person reviews)"""
    from pangloss_reconcile import marking

    m = worker_models()
    await world(m, database)
    assert marking.holds_stand_ins(m.Household)
    assert "Household" not in marking.suggestible_classes()
    made = await m.Household.Create(
        label="the Smyths",
        members=[{"type": "InRole", "role": "head", "target": [unknown()]}],
    ).save(instructions={"suggest": True})
    assert marks(database) == []
    await settle(database)
    await mark(made.id)

    await left_alone(database, caplog, "an entity")


@no_type_check
async def test_a_task_started_by_a_listener_of_the_worker_s_update_does_not_carry_what_it_keeps(
    database,
):
    """(mend 9: `marking.keeping` cleared before the write's other listeners run)"""
    from pangloss_reconcile import marking

    m = worker_models()
    ids = await world(m, database)
    made = await factoid(m, ids, unknown())
    await settle(database)
    seen = []

    def listener(event):
        if event.op == "update" and str(event.id) == str(made.id):
            seen.append(marking.keeping.get())

            async def later():
                seen.append(marking.keeping.get())

            asyncio.get_running_loop().create_task(later())

    hooks.after_write.append(listener)
    try:
        assert await drained() == 1
        await asyncio.sleep(0.05)
    finally:
        hooks.after_write.remove(listener)

    assert seen == [None, None]
    assert len(suggestions(database, made.id)) == 1
