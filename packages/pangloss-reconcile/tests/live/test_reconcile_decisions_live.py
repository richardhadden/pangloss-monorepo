"""What the stored route offered, and what was chosen of it, kept (`decisions.py`; step 11.4 of
implementation_docs/similarity-build-plan.md), on the backend under test.

On review's own models (`reviewed_models`: people who may be unreconciled, a reviewed factoid of meetings), the world
of the candidates' tests (two Jon Smyths in different company, Ada, Ben, Cy and Dee), every part built; a factoid that
names a Jon Smyth not identified, beside Ada and Ben, stored; its mention asked about by the stored route as `root`,
and reconciled through review's `reconcile` (which tells `hooks.resolved`, and so `decisions.heard`). What is
claimed: each path of the challenger's fault 2 by name (who was shown, who decided, how, how soon); twice gives one;
ids and numbers only; what fails to be kept never fails a reader; the sweep; the setting off; what the route costs."""

import asyncio
import contextlib
import datetime
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
from pangloss_review import reconcile
from pangloss_testing.live import apply_changes, run
from pangloss_testing.parts import one_turn
from pangloss_users import current_request_username
import test_reconcile_candidates_live as candidates_live
from test_reconcile_candidates_live import (
    NAME,
    ROUTE,
    bearer,
    ref,
    reviewed_meeting,
    reviewed_models,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

# (the fixtures of the candidates' tests: the database emptied, its vector indexes dropped; a client of the app)
database = candidates_live.database
client = candidates_live.client

# (every label of the world, the mention's first: none of them may be in a record)
LABELS = [NAME, "Ada", "Ben", "Cy", "Dee", "Eve", "Ann met Ben and Jon"]


@pytest_asyncio.fixture(loop_scope="session", autouse=True)
async def structure(database):
    """The package's migration applied, as `pangloss migrate` would (the unique keys the writes rely on; a second
    time it changes nothing): the test database is set up without the structure of installed apps"""
    migration = load("pangloss_reconcile", "0001_initial")
    await apply_changes(
        backend.current().database(), EMPTY_SNAPSHOT, list(migration.changes)
    )


@contextlib.contextmanager
def as_user(db_driver, username: str):
    """What is done in the block is done by `username` (as a request of theirs would be: `hooks.Resolution.user`)"""
    run(db_driver, "MERGE (:PGUser {username: $username})", username=username)
    token = current_request_username.set(username)
    try:
        yield
    finally:
        current_request_username.reset(token)


@no_type_check
async def world(db_driver, built: bool = True) -> tuple[Any, dict[str, str]]:
    """Ada, Ben, Cy and Dee; Jon Smyth who met Ada and Ben (twice), and Jon Smyth who met Cy and Dee (twice): the
    models and the ids by name (`jon`, the first Jon; `namesake`, the second); every part built, unless not"""
    from pangloss_vectors.rebuild import rebuild

    m = reviewed_models()
    ids = {}
    for name in ["Ada", "Ben", "Cy", "Dee"]:
        ids[name] = str((await m.Person.Create(label=name).save()).id)
    ids["jon"] = str((await m.Person.Create(label=NAME).save()).id)
    ids["namesake"] = str((await m.Person.Create(label=NAME).save()).id)
    for jon, (first, second) in [("jon", ("Ada", "Ben")), ("namesake", ("Cy", "Dee"))]:
        for _ in range(2):
            await m.Factoid.Create(
                label=f"{first} and {second}",
                statements=[
                    reviewed_meeting(ref(ids[jon]), [ref(ids[first]), ref(ids[second])])
                ],
            ).save(published=True)
    if built:
        await rebuild()
        await one_turn(db_driver)
    return m, ids


UNKNOWN = {"type": "Unreconciled", "label": NAME, "unreconciled_type": "Person"}


@no_type_check
async def mentioned(db_driver, m, ids: dict[str, str], count: int = 1) -> list[str]:
    """A factoid stored (unpublished, as review writes it) that names `count` Jon Smyths, not identified, beside Ada
    and Ben: the ids of the mentions, by id"""
    made = await m.Factoid.Create(
        label="Ann met Ben and Jon",
        statements=[
            reviewed_meeting(ref(ids["Ada"]), [ref(ids["Ben"]), *([UNKNOWN] * count)])
        ],
    ).save()
    return [
        row["id"]
        for row in run(
            db_driver,
            "MATCH (u:Unreconciled {head_node_id: $head}) RETURN u.id AS id ORDER BY id",
            head=str(made.id),
        )
    ]


async def shown_to(client, headers: dict, mention: str, limit: int = 10) -> dict:
    response = await client.get(f"{ROUTE}/{mention}?limit={limit}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def reconciled(
    db_driver, mention: str, entity: str, user: str = "root", **options
):
    """`mention` reconciled with `entity` through review, by `user`, and what it did in the background ended"""
    with as_user(db_driver, user):
        await reconcile.reconcile(UUID(mention), "Person", UUID(entity), **options)
        await reconcile.background_done()


PROPERTIES = "stand_in, at, rows, profile, signature, parts, weights, features, least"


def shown_records(db_driver) -> list[dict[str, Any]]:
    return run(
        db_driver,
        "MATCH (s:PGReconcileShown) RETURN s.stand_in AS stand_in, s.user AS user, s.at AS at, s.rows AS rows, "
        "s.profile AS profile, s.signature AS signature, s.parts AS parts, s.weights AS weights, "
        "s.features AS features, s.least AS least ORDER BY stand_in, user",
    )


def examples(db_driver) -> list[dict[str, Any]]:
    return run(
        db_driver,
        "MATCH (e:PGReconcileExample) RETURN e.stand_in AS stand_in, e.at AS at, e.rows AS rows, "
        "e.profile AS profile, e.signature AS signature, e.parts AS parts, e.weights AS weights, "
        "e.features AS features, e.least AS least, e.taken AS taken ORDER BY stand_in",
    )


def every_property(db_driver, label: str) -> list[dict[str, Any]]:
    """Each node of the label, all its properties (whatever they are named)"""
    return [
        row["p"]
        for row in run(db_driver, f"MATCH (n:{label}) RETURN properties(n) AS p")
    ]


def rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    return json.loads(record["rows"])


async def below_the_route(mention: str) -> tuple[Any, dict, Any]:
    """What the stored route makes of a mention before it keeps it, as a reader logged in (who sees what is not
    published): its `Found`, the answer, and the states the answer read"""
    from pangloss_reconcile import candidates_of
    from pangloss_reconcile.api import answered
    from pangloss_reconcile.stored import stored_plan
    from pangloss_users import see_unpublished

    token = see_unpublished.set(True)
    try:
        plan = await stored_plan(mention)
        (found,) = await candidates_of(plan, see_unpublished=True, only=[mention])
        given, states = await answered([found], True)
    finally:
        see_unpublished.reset(token)
    return found, given, states


@pytest.fixture
def setting(monkeypatch):
    def set_to(name: str, value: Any) -> None:
        monkeypatch.setattr(core_settings.SETTINGS, name, value)

    return set_to


# ---------------------------------------------------------------------------
# What was offered
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_stored_route_keeps_the_ten_best_with_their_features_which_were_displayed_and_the_signatures(
    database, client
):
    from pangloss_reconcile import decisions, settings
    from pangloss_vectors import store

    m, ids = await world(database)
    headers = await bearer(client)
    (mention,) = await mentioned(database, m, ids)

    before = datetime.datetime.now(datetime.UTC)
    answer = await shown_to(client, headers, mention, limit=2)
    after = datetime.datetime.now(datetime.UTC)

    (record,) = shown_records(database)
    assert record["stand_in"] == mention
    assert record["user"] == "root"
    at = (
        record["at"].to_native() if hasattr(record["at"], "to_native") else record["at"]
    )
    assert before <= at <= after
    kept = rows(record)
    displayed = [c["id"] for c in answer["unknowns"][0]["candidates"]]
    assert displayed[:2] == [ids["jon"], ids["namesake"]]
    # (every person of the world is found by the graph, and kept, whatever the least score and the limit)
    assert {row["id"] for row in kept} == {
        ids[n] for n in ["Ada", "Ben", "Cy", "Dee", "jon", "namesake"]
    }
    assert [row["id"] for row in kept][:2] == displayed
    assert [row["id"] for row in kept if row["displayed"]] == displayed
    scores = [row["score"] for row in kept]
    assert scores == sorted(scores, reverse=True)
    for row in kept:
        assert set(row) == {"id", "type", "scores", "shared", "score", "displayed"}
        assert row["type"] == "Person"
        assert set(row["scores"]) == {"name", "graph", "shared"}
        assert isinstance(row["shared"], int)
    (jon,) = [row for row in kept if row["id"] == ids["jon"]]
    assert jon["shared"] == 2  # (Ada and Ben)
    (candidate,) = [
        c for c in answer["unknowns"][0]["candidates"] if c["id"] == ids["jon"]
    ]
    assert jon["score"] == pytest.approx(candidate["score"])
    assert jon["scores"] == pytest.approx(candidate["scores"])

    states = await store.states()
    assert record["profile"] == "who"
    assert record["signature"] == states.profiles["who"].signature
    assert json.loads(record["parts"]) == {
        part: states.parts[part].signature for part in ["graph", "name"]
    }
    assert json.loads(record["weights"]) == settings.weights()
    assert record["features"] == decisions.FEATURES == 1
    assert record["least"] == settings.least_score()


@no_type_check
async def test_a_second_request_replaces_the_first_s_rows(database, client):
    m, ids = await world(database)
    headers = await bearer(client)
    (mention,) = await mentioned(database, m, ids)

    await shown_to(client, headers, mention, limit=10)
    (first,) = shown_records(database)
    await shown_to(client, headers, mention, limit=1)
    (second,) = shown_records(database)

    assert len([row for row in rows(first) if row["displayed"]]) > 1
    assert [row["id"] for row in rows(second) if row["displayed"]] == [ids["jon"]]
    assert [row["id"] for row in rows(first)] == [row["id"] for row in rows(second)]
    assert second["at"] > first["at"]


@no_type_check
async def test_two_requests_at_once_leave_one_shown_record_and_both_are_answered(
    database, client, caplog
):
    m, ids = await world(database)
    headers = await bearer(client)
    (mention,) = await mentioned(database, m, ids)

    with caplog.at_level(logging.WARNING, logger="pangloss.reconcile"):
        answers = await asyncio.gather(
            *[client.get(f"{ROUTE}/{mention}", headers=headers) for _ in range(4)]
        )

    assert [a.status_code for a in answers] == [200] * 4
    assert len(shown_records(database)) == 1
    assert "could not be kept" not in caplog.text

    # (and below the route, where the writes do meet: each a `MERGE` of the same key at the same moment)
    from pangloss_reconcile import decisions

    found, given, states = await below_the_route(mention)
    run(database, "MATCH (s:PGReconcileShown) DELETE s")
    with caplog.at_level(logging.WARNING, logger="pangloss.reconcile"):
        await asyncio.gather(
            *[decisions.keep_shown(found, given, states, "root") for _ in range(8)]
        )
    assert len(shown_records(database)) == 1
    assert "could not be kept" not in caplog.text


@no_type_check
async def test_an_answer_pending_or_rebuild_due_keeps_nothing(
    database, client, monkeypatch
):
    from pangloss_vectors import status

    m, ids = await world(database, built=False)
    headers = await bearer(client)
    (mention,) = await mentioned(database, m, ids)

    assert (await shown_to(client, headers, mention))["status"] == "pending"
    assert shown_records(database) == []

    from pangloss_vectors.rebuild import rebuild

    await rebuild()
    await one_turn(database)
    told = status.status_of

    def due(states):
        return SimpleNamespace(profile=lambda name: SimpleNamespace(rebuild_due=True))

    monkeypatch.setattr(status, "status_of", due)
    assert (await shown_to(client, headers, mention))["status"] == "rebuild_due"
    assert shown_records(database) == []
    monkeypatch.setattr(status, "status_of", told)
    assert (await shown_to(client, headers, mention))["status"] == "ok"
    assert len(shown_records(database)) == 1


@no_type_check
async def test_a_candidate_the_answer_does_not_give_is_not_displayed(database, client):
    """(below the route: every candidate is an entity, which is never unpublished, and a reader logged in sees what
    is not published, so a reader of the route cannot be made not to see one: the rule is `keep_shown`'s, given an
    answer that leaves one out, as `api.answer` leaves out what the reader may not see)"""
    from pangloss_reconcile import decisions

    m, ids = await world(database)
    (mention,) = await mentioned(database, m, ids)
    found, given, states = await below_the_route(mention)
    unknown = given["unknowns"][0]
    unknown["candidates"] = [c for c in unknown["candidates"] if c["id"] != ids["jon"]]

    await decisions.keep_shown(found, given, states, "root")

    (record,) = shown_records(database)
    displayed = {row["id"]: row["displayed"] for row in rows(record)}
    assert displayed[ids["jon"]] is False
    assert displayed[ids["namesake"]] is True


@no_type_check
async def test_a_failure_to_keep_what_was_offered_still_answers_and_is_logged(
    database, client, monkeypatch, caplog
):
    from pangloss_reconcile import decisions

    m, ids = await world(database)
    headers = await bearer(client)
    (mention,) = await mentioned(database, m, ids)
    monkeypatch.setattr(decisions, "KEEP_QUERY", "THIS IS NO CYPHER")

    with caplog.at_level(logging.ERROR, logger="pangloss.reconcile"):
        answer = await shown_to(client, headers, mention)

    assert answer["unknowns"][0]["candidates"][0]["id"] == ids["jon"]
    assert shown_records(database) == []
    assert (
        f"What was offered for the stand-in {mention} could not be kept" in caplog.text
    )


@no_type_check
async def test_while_the_database_is_being_migrated_nothing_is_kept_and_nothing_is_logged_as_a_failure(
    database, client, caplog
):
    from pangloss_testing.under_test import migration_backend as backend

    m, ids = await world(database)
    headers = await bearer(client)
    (mention,) = await mentioned(database, m, ids)

    await backend.ensure_ready()
    await backend.lock("someone")
    try:
        with caplog.at_level(logging.DEBUG, logger="pangloss.reconcile"):
            answer = await shown_to(client, headers, mention)
    finally:
        await backend.unlock()

    assert answer["status"] == "ok"
    assert shown_records(database) == []
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING], caplog.text


# ---------------------------------------------------------------------------
# What was chosen
# ---------------------------------------------------------------------------


@no_type_check
async def test_shown_then_reconciled_by_the_same_user_makes_one_example_with_the_row_taken_and_the_shown_record_goes(
    database, client
):
    from pangloss_reconcile import decisions

    m, ids = await world(database)
    headers = await bearer(client)
    (mention,) = await mentioned(database, m, ids)
    await shown_to(client, headers, mention)
    (shown,) = shown_records(database)

    before = datetime.datetime.now(datetime.UTC)
    await reconciled(database, mention, ids["jon"])

    (example,) = examples(database)
    assert example["stand_in"] == mention
    assert example["taken"] == ids["jon"]
    for name in ["rows", *decisions.SIGNATURES]:
        assert example[name] == shown[name], name
    at = (
        example["at"].to_native()
        if hasattr(example["at"], "to_native")
        else example["at"]
    )
    assert at >= before
    assert shown_records(database) == []


@no_type_check
async def test_reconciled_with_an_entity_not_among_the_rows_or_made_just_before_takes_none(
    database, client
):
    m, ids = await world(database)
    # (Eve has no vectors: made after the rebuild, she is found by no part)
    eve = str((await m.Person.Create(label="Eve").save()).id)
    headers = await bearer(client)
    first, second = await mentioned(database, m, ids, count=2)
    await shown_to(client, headers, first)
    await shown_to(client, headers, second)
    made = str((await m.Person.Create(label="Jon Smyth the third").save()).id)

    await reconciled(database, first, eve)
    await reconciled(database, second, made)

    found = {e["stand_in"]: e for e in examples(database)}
    assert set(found) == {first, second}
    for example in found.values():
        assert example["taken"] is None
        assert not {eve, made} & {row["id"] for row in rows(example)}
    assert shown_records(database) == []


@no_type_check
async def test_reconciled_with_a_row_kept_but_not_displayed_takes_it_and_says_it_was_not_displayed(
    database, client
):
    m, ids = await world(database)
    headers = await bearer(client)
    (mention,) = await mentioned(database, m, ids)
    answer = await shown_to(client, headers, mention, limit=1)
    assert [c["id"] for c in answer["unknowns"][0]["candidates"]] == [ids["jon"]]

    await reconciled(database, mention, ids["namesake"])

    (example,) = examples(database)
    assert example["taken"] == ids["namesake"]
    (row,) = [row for row in rows(example) if row["id"] == ids["namesake"]]
    assert row["displayed"] is False


@no_type_check
async def test_never_shown_makes_no_example(database, client):
    """(as a mention reconciled by a URI it names, for which no list is asked)"""
    m, ids = await world(database)
    (mention,) = await mentioned(database, m, ids)

    await reconciled(database, mention, ids["jon"])

    assert examples(database) == []
    assert shown_records(database) == []


@no_type_check
async def test_shown_to_one_user_and_reconciled_by_another_makes_no_example_and_removes_the_first_s_record(
    database, client
):
    m, ids = await world(database)
    headers = await bearer(client)
    (mention,) = await mentioned(database, m, ids)
    await shown_to(client, headers, mention)

    await reconciled(database, mention, ids["jon"], user="bea")

    assert examples(database) == []
    assert shown_records(database) == []


@no_type_check
async def test_shown_longer_ago_than_the_setting_makes_no_example_and_the_record_goes(
    database, client
):
    m, ids = await world(database)
    headers = await bearer(client)
    (mention,) = await mentioned(database, m, ids)
    await shown_to(client, headers, mention)
    run(
        database,
        "MATCH (s:PGReconcileShown) SET s.at = $at",
        at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=31),
    )

    await reconciled(database, mention, ids["jon"])

    assert examples(database) == []
    assert shown_records(database) == []


@no_type_check
async def test_an_also_mention_with_a_shown_record_of_its_own_makes_no_example_and_its_record_goes(
    database, client
):
    m, ids = await world(database)
    headers = await bearer(client)
    asked, also = await mentioned(database, m, ids, count=2)
    await shown_to(client, headers, asked)
    await shown_to(client, headers, also)

    await reconciled(database, asked, ids["jon"], also=[UUID(also)])

    assert [e["stand_in"] for e in examples(database)] == [asked]
    assert shown_records(database) == []


@no_type_check
async def test_in_a_form_nothing_is_told_and_the_shown_record_stays_until_the_sweep(
    database, client
):
    m, ids = await world(database)
    headers = await bearer(client)
    (mention,) = await mentioned(database, m, ids)
    await shown_to(client, headers, mention)

    await reconciled(database, mention, ids["jon"], in_form=True)

    assert examples(database) == []
    assert [r["stand_in"] for r in shown_records(database)] == [mention]


@no_type_check
async def test_a_stand_in_decided_twice_has_one_example_the_later(database, client):
    """(the stand-in coming back with its id, as a restore from history would bring it, cannot be had here:
    `pangloss-history` is no dependency of this package's tests. So the listener is told twice, of two
    resolutions, each after a list shown: the mention is not written, and stays)"""
    from pangloss_reconcile import decisions

    m, ids = await world(database)
    headers = await bearer(client)
    (mention,) = await mentioned(database, m, ids)

    def resolution(entity: str) -> hooks.Resolution:
        return hooks.Resolution(
            stand_in_id=UUID(mention),
            stand_in_type="Unreconciled",
            head_id=UUID(mention),
            head_type="Factoid",
            entity_id=UUID(entity),
            entity_type="Person",
            user="root",
            at=datetime.datetime.now(datetime.UTC),
            direct=True,
        )

    await shown_to(client, headers, mention, limit=10)
    await decisions.heard(resolution(ids["jon"]))
    await shown_to(client, headers, mention, limit=1)
    await decisions.heard(resolution(ids["namesake"]))

    (example,) = examples(database)
    assert example["taken"] == ids["namesake"]
    assert [row["id"] for row in rows(example) if row["displayed"]] == [ids["jon"]]
    assert shown_records(database) == []


@no_type_check
async def test_resolved_again_with_no_list_shown_the_earlier_example_goes_and_a_list_dated_after_the_decision_is_none(
    database, client
):
    """(told directly, as in the test above) An example, then the stand-in resolved again by a path that makes none
    (no list shown since): the earlier decision was undone, and its example is not kept. And a list written after
    the decision (a request still on its way when the person decided) is no example"""
    from pangloss_reconcile import decisions

    m, ids = await world(database)
    headers = await bearer(client)
    (mention,) = await mentioned(database, m, ids)

    def resolution(entity: str, at: datetime.datetime) -> hooks.Resolution:
        return hooks.Resolution(
            stand_in_id=UUID(mention),
            stand_in_type="Unreconciled",
            head_id=UUID(mention),
            head_type="Factoid",
            entity_id=UUID(entity),
            entity_type="Person",
            user="root",
            at=at,
            direct=True,
        )

    await shown_to(client, headers, mention)
    await decisions.heard(resolution(ids["jon"], datetime.datetime.now(datetime.UTC)))
    assert [example["taken"] for example in examples(database)] == [ids["jon"]]

    await decisions.heard(
        resolution(ids["namesake"], datetime.datetime.now(datetime.UTC))
    )
    assert examples(database) == []

    before = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=5)
    await shown_to(client, headers, mention)
    await decisions.heard(resolution(ids["jon"], before))
    assert examples(database) == []
    assert shown_records(database) == []


@no_type_check
async def test_an_example_and_a_shown_record_hold_no_label(database, client):
    m, ids = await world(database)
    headers = await bearer(client)
    first, second = await mentioned(database, m, ids, count=2)
    await shown_to(client, headers, first)
    await shown_to(client, headers, second)
    await reconciled(database, first, ids["jon"])

    held = [
        *every_property(database, "PGReconcileExample"),
        *every_property(database, "PGReconcileShown"),
    ]
    assert len(held) == 2
    for properties in held:
        text = json.dumps(properties, default=str)
        for label in LABELS:
            assert label not in text, (label, properties)
    (example,) = every_property(database, "PGReconcileExample")
    assert "user" not in example
    assert set(example) == {*PROPERTIES.split(", "), "taken"}


# ---------------------------------------------------------------------------
# The setting off, and the sweep
# ---------------------------------------------------------------------------


@no_type_check
async def test_with_the_setting_off_the_route_keeps_nothing_and_the_listener_does_nothing(
    database, client, setting
):
    m, ids = await world(database)
    headers = await bearer(client)
    first, second = await mentioned(database, m, ids, count=2)
    await shown_to(client, headers, first)

    setting("RECONCILE_KEEP_DECISIONS", False)
    await shown_to(client, headers, second)
    await reconciled(database, first, ids["jon"])

    assert examples(database) == []
    # (the one shown with it on stays, as no listener was there)
    assert [r["stand_in"] for r in shown_records(database)] == [first]


@no_type_check
async def test_the_sweep_removes_what_is_old_and_what_lost_its_stand_in_and_leaves_what_is_fresh(
    database, client
):
    """(and `pangloss reconcile sweep`: `test_reconcile_sweep_command_live.py`)"""
    from pangloss_reconcile import decisions

    m, ids = await world(database)
    headers = await bearer(client)
    old, gone, fresh = [(await mentioned(database, m, ids))[0] for _ in range(3)]
    for mention in (old, gone, fresh):
        await shown_to(client, headers, mention)
    run(
        database,
        "MATCH (s:PGReconcileShown {stand_in: $id}) SET s.at = $at",
        id=old,
        at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=45),
    )
    # (the document written again without the mention, by no route of review's: nothing is told)
    (row,) = run(
        database,
        "MATCH (n:PGIndexableNode {id: $id}) RETURN n.head_node_id AS head",
        id=gone,
    )
    await reconcile.rewrite_part(
        "Factoid", row["head"], gone, lambda part: {"type": "Person", "id": ids["Cy"]}
    )
    assert (
        run(database, "MATCH (n:PGIndexableNode {id: $id}) RETURN n.id AS id", id=gone)
        == []
    )

    assert await decisions.sweep(page=1) == 2
    assert [r["stand_in"] for r in shown_records(database)] == [fresh]
    assert await decisions.sweep() == 0
    assert [r["stand_in"] for r in shown_records(database)] == [fresh]


# ---------------------------------------------------------------------------
# What the stored route costs
# ---------------------------------------------------------------------------

# What one GET of a stored stand-in runs (measured 2026-11-23, on Memgraph): with nothing kept
# (`RECONCILE_KEEP_DECISIONS = False`), as before step 11.4, 15 transactions and 49 statements (the login, the plan
# of the stored document, the parts, the reasons, the states, the views); with what was offered kept, one write
# transaction more, of two statements (the migration lock every write looks for, and the `MERGE`). Step 11.6
# (2026-11-23) reads the fit in use (`fits.in_use()`, for "none of these"): one read transaction of one statement
# more, 16 and 50 with nothing kept (`test_reconcile_new_live.py` holds it with a fit in use)
STORED_TRANSACTIONS = 16
STORED_STATEMENTS = 50


@pytest.mark.parametrize("kept", [True, False], ids=["kept", "not kept"])
@no_type_check
async def test_a_get_of_a_stored_stand_in_runs_its_budget_of_transactions_and_statements(
    database, client, setting, kept
):
    from pangloss_testing.conformance.test_query_costs import recorded

    setting("RECONCILE_KEEP_DECISIONS", kept)
    m, ids = await world(database)
    headers = await bearer(client)
    (mention,) = await mentioned(database, m, ids)
    # (once before, so that what is read once for a process is read)
    await shown_to(client, headers, mention)

    with recorded() as found:
        await shown_to(client, headers, mention)

    more = 1 if kept else 0
    assert (found.transactions, len(found.statements)) == (
        STORED_TRANSACTIONS + more,
        STORED_STATEMENTS + 2 * more,
    )
