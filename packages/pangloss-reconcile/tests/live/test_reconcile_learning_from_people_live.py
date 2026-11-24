"""Learning from people only (step 10.5f of implementation_docs/similarity-build-plan.md): an example is made of a
person's confirmation of one of the worker's suggestions (`decisions.confirmed`, a listener of `hooks.confirmed`),
never of what the worker wrote, on the backend under test.

On the worker's models and world (`test_reconcile_worker_live.py`: two Jon Smyths in different company, one who met
Ada and Ben, one Cy and Dee), with review and the library installed, through review's real confirmations: each test
starts from a mention the worker replaced (`drain()`), then a person acts. What is claimed: the example made (by the
suggestion's id, `via` "suggestion", the rows the worker kept, `taken`), when none is, what the sweep does with them,
and what `learn` reads."""

import json
import logging
from typing import Any, no_type_check
from uuid import UUID

import pytest
import test_reconcile_worker_live as worker_tests
from pangloss_models import ToolchainRun
from pangloss_models.utils import editable
from pangloss_review import identify, reconcile
from pangloss_testing.live import run
from pangloss_users import service
from test_reconcile_worker_live import (
    NAME,
    as_person,
    drained,
    factoid,
    kept,
    meeting,
    ref,
    settle,
    suggestions,
    unknown,
    worker_models,
    world,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

# (the worker's tests' fixtures: the database emptied, the package's migrations applied, a new worker for each test,
# a setting changed for one test, history recording)
database = worker_tests.database
structure = worker_tests.structure
a_new_worker = worker_tests.a_new_worker
setting = worker_tests.setting
history = worker_tests.history

FROM_TEXT = "IdentificationFromText"


def examples(db_driver) -> list[dict[str, Any]]:
    return kept(db_driver, "PGReconcileExample")


def alternatives(*ids: Any) -> list[dict[str, Any]]:
    """A target over these alternatives (one `WeightedAlternative`), the per cents shared out, the first taking what
    is left over"""
    share = 100 // len(ids)
    percents = [share] * len(ids)
    percents[0] += 100 - share * len(ids)
    return [
        {
            "type": "WeightedAlternative",
            "alternatives": [
                {"type": "Person", "id": str(id), "edge_properties": {"percent": p}}
                for id, p in zip(ids, percents, strict=True)
            ],
        }
    ]


@no_type_check
async def suggested(m, db_driver, ids, **more) -> Any:
    """Ada met Ben and Jon Smyth, not identified (`factoid`, with `more`), saved with `suggest=true` and drained: the
    head, the suggestion's id, and the record the worker kept of it (None if it kept none)"""
    made = await factoid(m, ids, unknown(), **more)
    await settle(db_driver)
    assert await drained() == 1
    (suggestion,) = suggestions(db_driver, made.id)
    rows = [row for row in kept(db_driver) if row["id"] == suggestion["p"]["id"]]
    return made, suggestion["p"]["id"], (rows[0] if rows else None)


async def confirm(db_driver, id: str, user: str = "ann", **more) -> Any:
    with as_person(db_driver, user):
        return await identify.confirm(UUID(id), user, **more)


@no_type_check
async def saved_with(m, db_driver, made, change, user: str = "bob", **save) -> None:
    """The factoid saved by a person (`user`) with its first statement's `met` changed (`change(met)`), and review's
    work after the save done"""
    view = await m.Factoid.get(made.id)
    data = editable(view.model_dump())
    data["statements"][0]["met"] = change(data["statements"][0]["met"])
    with as_person(db_driver, user):
        await m.Factoid.Update(**data).save(expected_version=view.meta.version, **save)
        await reconcile.background_done()


def signatures(record: dict[str, Any]) -> dict[str, Any]:
    from pangloss_reconcile import decisions

    return {name: record[name] for name in decisions.SIGNATURES}


# ---------------------------------------------------------------------------
# A person confirms: an example
# ---------------------------------------------------------------------------


@no_type_check
async def test_confirmed_as_one_of_its_alternatives_makes_one_example_of_what_the_worker_saw_and_its_record_goes(
    database, setting
):
    m = worker_models()
    ids = await world(m, database)
    # (both Jon Smyths among the alternatives)
    setting("RECONCILE_SUGGEST_WITHIN", 0.0)
    made, id, record = await suggested(m, database, ids)
    target = (await m.Factoid.get(made.id)).statements[0].met[1].target[0]
    assert ids["namesake"] in [str(a.id) for a in target.alternatives]

    await confirm(database, id, entity={"type": "Person", "id": ids["namesake"]})

    (example,) = examples(database)
    assert (example["stand_in"], example["via"], example.get("taken")) == (
        id,
        "suggestion",
        ids["namesake"],
    )
    assert (example["direct"], example["user"]) == (True, "ann")
    # (the rows and signatures as the worker kept them, `displayed` the list it decided on)
    assert example["rows"] == record["rows"]
    assert ids["namesake"] in [r["id"] for r in json.loads(example["rows"])]
    assert signatures(example) == signatures(record)
    assert kept(database) == []


@no_type_check
async def test_a_suggestion_of_one_candidate_confirmed_as_it_is_makes_an_example_that_takes_it(
    database,
):
    m = worker_models()
    ids = await world(m, database)
    # (the witness's place takes one person: the best alone)
    made = await m.Factoid.Create(
        label="Ada met Ben, Jon looking on",
        statements=[meeting(ref(ids["Ada"]), [ref(ids["Ben"])], witness=unknown())],
    ).save(instructions={"suggest": True})
    await settle(database)
    assert await drained() == 1
    witness = (await m.Factoid.get(made.id)).statements[0].witness
    assert [str(t.id) for t in witness.target] == [ids["jon"]]

    await confirm(database, str(witness.id))

    (example,) = examples(database)
    assert (example["stand_in"], example.get("taken"), example["direct"]) == (
        str(witness.id),
        ids["jon"],
        True,
    )
    assert kept(database) == []


@no_type_check
async def test_confirmed_as_someone_else_by_a_form_s_save_makes_an_example_that_takes_none_not_direct(
    database,
):
    m = worker_models()
    ids = await world(m, database)
    made, id, record = await suggested(m, database, ids)
    # (made after the worker asked: in none of its rows)
    other = str((await m.Person.Create(label="Zed Quux").save()).id)

    def someone_else(met):
        part = met[1]
        assert str(part["id"]) == id
        return [
            met[0],
            {
                "type": FROM_TEXT,
                "id": part["id"],
                "text": part["text"],
                "target": alternatives(other),
            },
        ]

    await saved_with(m, database, made, someone_else, user="bob")

    (example,) = examples(database)
    assert (example["stand_in"], example["via"], example.get("taken")) == (
        id,
        "suggestion",
        None,
    )
    assert (example["direct"], example["user"]) == (False, "bob")
    assert example["rows"] == record["rows"]
    assert kept(database) == []


@no_type_check
async def test_an_entity_merged_since_the_worker_asked_is_taken_as_the_row_it_was(
    database,
):
    m = worker_models()
    ids = await world(m, database)
    made, id, _ = await suggested(m, database, ids)
    elder = (await m.Person.Create(label=NAME).save()).id
    await m.Person.merge(absorb=UUID(ids["jon"]), into=elder)

    # (the person names the survivor, which no row is)
    await confirm(database, id, entity={"type": "Person", "id": str(elder)})

    (example,) = examples(database)
    assert example.get("taken") == ids["jon"]
    assert str(elder) not in [r["id"] for r in json.loads(example["rows"])]


# ---------------------------------------------------------------------------
# No example
# ---------------------------------------------------------------------------


@no_type_check
async def test_confirmed_as_it_is_with_alternatives_still_open_makes_no_example_and_its_record_stays(
    database, setting
):
    m = worker_models()
    ids = await world(m, database)
    setting("RECONCILE_SUGGEST_WITHIN", 0.0)
    made, id, record = await suggested(m, database, ids)
    target = (await m.Factoid.get(made.id)).statements[0].met[1].target[0]
    assert len(target.alternatives) > 1

    await confirm(database, id)

    assert (await m.Factoid.get(made.id)).statements[0].met[1].type == FROM_TEXT
    assert examples(database) == []
    assert [r["id"] for r in kept(database)] == [record["id"]]


@no_type_check
async def test_confirmed_with_alternatives_open_then_collapsed_to_one_by_a_save_is_not_learnt_from(
    database, setting
):
    """Decided 2026-11-24: confirmed as it is with several, the node is an identification and no suggestion; a later
    save that leaves one entity is an edit like any other (no event of the core tells of it), and the worker's
    record goes at the sweep. A person who means one confirms as that one"""
    from pangloss_reconcile import decisions

    m = worker_models()
    ids = await world(m, database)
    setting("RECONCILE_SUGGEST_WITHIN", 0.0)
    made, id, _ = await suggested(m, database, ids)
    await confirm(database, id)

    def collapsed(met):
        return [met[0], {**met[1], "target": alternatives(ids["jon"])}]

    await saved_with(m, database, made, collapsed)

    assert examples(database) == []
    await decisions.sweep()
    assert kept(database) == []
    assert examples(database) == []


@no_type_check
async def test_a_suggestion_edited_away_makes_no_example_and_the_sweep_removes_its_record(
    database,
):
    from pangloss_reconcile import decisions

    m = worker_models()
    ids = await world(m, database)
    made, _, _ = await suggested(m, database, ids)
    other, _, _ = await suggested(m, database, ids, label="Ada again")
    assert len(kept(database)) == 2

    # (one to a stand-in again, the other removed)
    await saved_with(m, database, made, lambda met: [met[0], unknown()])
    await saved_with(m, database, other, lambda met: [met[0]])

    assert examples(database) == []
    await decisions.sweep()
    assert kept(database) == []
    assert examples(database) == []


@no_type_check
async def test_an_outside_toolchain_s_suggestion_confirmed_makes_nothing(database):
    m = worker_models()
    ids = await world(m, database)
    await service.create_toolchain("extractor")
    made = await m.Factoid.Create(
        label="Ada met Ben and Jon, by an extractor",
        statements=[
            meeting(
                ref(ids["Ada"]),
                [
                    ref(ids["Ben"]),
                    {
                        "type": "IdentificationByToolchainFromText",
                        "text": NAME,
                        "target": alternatives(ids["jon"]),
                    },
                ],
            )
        ],
    ).save(toolchain=ToolchainRun("extractor", version="1"))
    part = (await m.Factoid.get(made.id)).statements[0].met[1]

    await confirm(database, str(part.id))

    assert (await m.Factoid.get(made.id)).statements[0].met[1].type == FROM_TEXT
    assert examples(database) == []
    assert kept(database) == []


@no_type_check
async def test_the_worker_s_own_later_write_of_the_document_makes_no_example(
    database,
):
    """The worker cannot write a suggestion again as an identification (it only puts suggestions in the place of
    stand-ins, and writes what a person confirmed as it is: `was` is then not a suggestion), and review tells nothing
    of a write by a toolchain anyway: so its write here raises no `hooks.confirmed`, and this is all that can be shown
    of it. The first suggestion is in the document it writes again, and still makes no example"""
    m = worker_models()
    ids = await world(m, database)
    made, id, _ = await suggested(m, database, ids)
    # (a person adds a witness, saying suggest=true: the worker writes the document again, the first suggestion in it)
    view = await m.Factoid.get(made.id)
    data = editable(view.model_dump())
    data["statements"][0]["witness"] = unknown()
    with as_person(database):
        await m.Factoid.Update(**data).save(
            expected_version=view.meta.version, instructions={"suggest": True}
        )
        await reconcile.background_done()
    await settle(database)
    assert await drained() == 1
    await reconcile.background_done()

    assert (await m.Factoid.get(made.id)).meta.updated_by == worker_tests.TOOLCHAIN
    assert examples(database) == []
    assert id in [r["id"] for r in kept(database)]


# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------


@no_type_check
async def test_confirmed_then_swept_the_example_stays_and_restored_to_before_the_confirmation_it_goes(
    database, history
):
    from pangloss_history import listener
    from pangloss_history.restore import restore

    from pangloss_reconcile import decisions

    m = worker_models()
    ids = await world(m, database)
    store = history()
    made, id, _ = await suggested(m, database, ids)
    stand_in = next(
        r["stand_in"] for r in kept(database, "PGReconcileTried") if r.get("suggested")
    )
    await confirm(database, id, entity={"type": "Person", "id": ids["jon"]})

    await decisions.sweep()
    (example,) = examples(database)
    assert example["stand_in"] == id
    # (and the stand-in replaced stays tried while the example of its suggestion is there)
    assert [
        (r["stand_in"], r["suggested"]) for r in kept(database, "PGReconcileTried")
    ] == [(stand_in, id)]

    # (version 2 is the worker's, 3 the confirmation: back to 2, the node is a suggestion again)
    listener.get_recorder().drain()
    with as_person(database):
        await restore(store, m.Factoid, made.id, 2)
    assert (await m.Factoid.get(made.id)).statements[0].met[
        1
    ].type == "IdentificationByToolchainFromText"
    await decisions.sweep()
    assert examples(database) == []
    assert kept(database, "PGReconcileTried") == []


# ---------------------------------------------------------------------------
# learn, and the settings
# ---------------------------------------------------------------------------


@no_type_check
async def test_learn_reads_no_suggestion_until_a_person_confirms_it_then_counts_it_apart_or_leaves_it_out(
    database, setting
):
    from pangloss_reconcile import fits

    m = worker_models()
    ids = await world(m, database)
    made, id, _ = await suggested(m, database, ids)
    other, _, _ = await suggested(m, database, ids, label="Ada again")
    assert len(kept(database)) == 2

    # (suggestions written, none confirmed: no decision)
    learnt = await fits.learn(dry_run=True)
    assert (learnt.read, learnt.decisions, learnt.suggested) == (0, 0, 0)

    await confirm(database, id, entity={"type": "Person", "id": ids["jon"]})

    learnt = await fits.learn(dry_run=True)
    assert (learnt.read, learnt.decisions, learnt.suggested) == (1, 1, 1)
    assert learnt.suggestions_left_out == 0
    assert "1 decision to learn from, 1 of them of confirmed suggestions" in (
        learnt.lines()
    )

    setting("RECONCILE_LEARN_FROM_SUGGESTIONS", False)
    learnt = await fits.learn(dry_run=True)
    assert (learnt.read, learnt.decisions, learnt.suggestions_left_out) == (1, 0, 1)
    assert (
        "1 example left out: of confirmed suggestions (RECONCILE_LEARN_FROM_SUGGESTIONS is False)"
        in learnt.lines()
    )

    setting("RECONCILE_LEARN_FROM_SUGGESTIONS", True)
    learnt = await fits.learn()
    assert learnt.id is not None
    (fit,) = await fits.fits()
    assert (fit["decisions"], fit["suggested"]) == (1, 1)
    # (the sweep `learn` makes left the example, and the unconfirmed one's record)
    assert len(examples(database)) == 1
    assert len(kept(database)) == 1


@no_type_check
async def test_with_keep_decisions_off_the_worker_keeps_no_record_and_a_confirmation_makes_nothing(
    database, setting
):
    m = worker_models()
    ids = await world(m, database)
    setting("RECONCILE_KEEP_DECISIONS", False)
    made, id, record = await suggested(m, database, ids)
    assert record is None and kept(database) == []
    # (what it tried is its own, and still noted)
    assert [r["suggested"] for r in kept(database, "PGReconcileTried")] == [id]

    await confirm(database, id, entity={"type": "Person", "id": ids["jon"]})

    assert examples(database) == []


@no_type_check
async def test_reconcile_s_listener_failing_is_logged_and_the_confirmation_is_made(
    database, monkeypatch, caplog
):
    from pangloss_reconcile import decisions

    m = worker_models()
    ids = await world(m, database)
    made, id, record = await suggested(m, database, ids)

    async def failing(*args, **kwargs):
        raise RuntimeError("the listener fails")

    monkeypatch.setattr(decisions, "taken_of", failing)
    with caplog.at_level(logging.ERROR):
        await confirm(database, id, entity={"type": "Person", "id": ids["jon"]})

    assert "A listener to confirmed suggestions failed" in caplog.text
    assert (await m.Factoid.get(made.id)).statements[0].met[1].type == FROM_TEXT
    # (nothing of its transaction written)
    assert examples(database) == []
    assert [r["id"] for r in kept(database)] == [record["id"]]


# ---------------------------------------------------------------------------
# The mends of the second reading (briefs/10.5f-mends.md)
# ---------------------------------------------------------------------------


@no_type_check
async def restored_to_the_suggestion(m, db_driver, ids, store) -> tuple[Any, str, Any]:
    """Ann confirms the suggestion as Jon (an example), then it is restored to the worker's version (2), no sweep in
    between: the head, the suggestion's id, and Ann's example"""
    from pangloss_history import listener
    from pangloss_history.restore import restore

    made, id, _ = await suggested(m, db_driver, ids)
    await confirm(db_driver, id, entity={"type": "Person", "id": ids["jon"]})
    (example,) = examples(db_driver)
    assert (example.get("taken"), example["user"]) == (ids["jon"], "ann")
    listener.get_recorder().drain()
    with as_person(db_driver):
        await restore(store, m.Factoid, made.id, 2)
    assert (await m.Factoid.get(made.id)).statements[0].met[
        1
    ].type == "IdentificationByToolchainFromText"
    return made, id, example


@no_type_check
async def test_restored_to_the_suggestion_and_confirmed_again_by_another_the_example_is_replaced_from_its_own_rows(
    database, history, setting
):
    m = worker_models()
    ids = await world(m, database)
    setting("RECONCILE_SUGGEST_WITHIN", 0.0)
    store = history()
    _, id, before = await restored_to_the_suggestion(m, database, ids, store)
    assert ids["namesake"] in [r["id"] for r in json.loads(before["rows"])]

    await confirm(database, id, user="bob", entity=ref(ids["namesake"]))

    (example,) = examples(database)
    assert (example["stand_in"], example.get("taken"), example["user"]) == (
        id,
        ids["namesake"],
        "bob",
    )
    assert example["direct"] is True
    assert example["at"] != before["at"]
    # (the rows and signatures are those the worker kept, as the first example had them)
    assert example["rows"] == before["rows"]
    assert signatures(example) == signatures(before)


@no_type_check
async def test_restored_to_the_suggestion_and_confirmed_again_with_alternatives_open_the_example_goes(
    database, history, setting
):
    m = worker_models()
    ids = await world(m, database)
    setting("RECONCILE_SUGGEST_WITHIN", 0.0)
    store = history()
    made, id, _ = await restored_to_the_suggestion(m, database, ids, store)
    target = (await m.Factoid.get(made.id)).statements[0].met[1].target[0]
    assert len(target.alternatives) > 1

    await confirm(database, id, user="bob")

    assert examples(database) == []


@no_type_check
async def test_a_restore_over_the_suggestion_to_the_confirmed_version_makes_no_example_of_the_restorer(
    database, history
):
    """A restore is no judgement: putting back Ann's confirmed version over the suggestion raises no
    `hooks.confirmed` (review), so Ann's example stands as she made it, and none is made by whoever restored"""
    from pangloss_history import listener
    from pangloss_history.restore import restore

    m = worker_models()
    ids = await world(m, database)
    store = history()
    made, id, before = await restored_to_the_suggestion(m, database, ids, store)

    listener.get_recorder().drain()
    with as_person(database, "bob"):
        await restore(store, m.Factoid, made.id, 3)
        await reconcile.background_done()
    assert (await m.Factoid.get(made.id)).statements[0].met[1].type == FROM_TEXT

    (example,) = examples(database)
    assert (example.get("taken"), example["user"], example["at"]) == (
        ids["jon"],
        "ann",
        before["at"],
    )


@no_type_check
@pytest.mark.parametrize(
    "who", ["a toolchain", "an unknown name", "the default user", "a disabled user"]
)
async def test_a_confirmation_by_no_person_makes_no_example_and_says_so(
    database, caplog, who
):
    m = worker_models()
    ids = await world(m, database)
    made, id, record = await suggested(m, database, ids)
    if who == "a toolchain":
        await service.create_toolchain("extractor")
        user = "extractor"
    elif who == "an unknown name":
        user = "nobody-at-all"
    elif who == "the default user":
        user = "pangloss_default_user"
    else:
        user = "dan"
        run(database, "MERGE (:PGUser {username: 'dan', disabled: true})")

    # (the write is Ann's: what is checked is the user the confirmation names, as `confirm` is called in-process)
    with caplog.at_level(logging.INFO, logger="pangloss.reconcile"):
        with as_person(database, "ann"):
            await identify.confirm(UUID(id), user, entity=ref(ids["jon"]))

    assert (await m.Factoid.get(made.id)).statements[0].met[1].type == FROM_TEXT
    assert examples(database) == []
    assert [r["id"] for r in kept(database)] == [record["id"]]
    assert f"The confirmation of {id}" in caplog.text
    assert "is not learnt from" in caplog.text


@no_type_check
async def test_two_rows_merged_since_into_the_entity_confirmed_make_no_example(
    database, caplog
):
    m = worker_models()
    ids = await world(m, database)
    # (the namesake among the rows, not among the alternatives: a document that names both cannot have them merged)
    made, id, record = await suggested(m, database, ids)
    target = (await m.Factoid.get(made.id)).statements[0].met[1].target[0]
    assert [str(a.id) for a in target.alternatives] == [ids["jon"]]
    rows = [r["id"] for r in json.loads(record["rows"])]
    assert ids["jon"] in rows and ids["namesake"] in rows
    await m.Person.merge(absorb=UUID(ids["namesake"]), into=UUID(ids["jon"]))

    with caplog.at_level(logging.INFO, logger="pangloss.reconcile"):
        await confirm(database, id, entity=ref(ids["jon"]))

    assert examples(database) == []
    assert kept(database) == []
    assert "2 of the rows offered have been merged since" in caplog.text


@no_type_check
async def test_the_others_confirmed_along_with_it_are_examples_too_not_direct(
    database,
):
    m = worker_models()
    ids = await world(m, database)
    _, first, _ = await suggested(m, database, ids)
    _, second, _ = await suggested(m, database, ids, label="Ada again")

    with as_person(database):
        await identify.confirm(
            UUID(first), "ann", also=[UUID(second)], entity=ref(ids["jon"])
        )
        await reconcile.background_done()

    found = {e["stand_in"]: e for e in examples(database)}
    assert {
        id: (e.get("taken"), e["direct"], e["user"]) for id, e in found.items()
    } == {first: (ids["jon"], True, "ann"), second: (ids["jon"], False, "ann")}
    assert kept(database) == []


@no_type_check
async def test_given_to_others_they_are_examples_not_direct(database):
    m = worker_models()
    ids = await world(m, database)
    _, mine, _ = await suggested(m, database, ids)
    _, other, _ = await suggested(m, database, ids, label="Ada again")

    with as_person(database):
        assert (
            await identify.give_to_others(
                UUID(mine), "ann", [UUID(other)], alternatives(ids["jon"])
            )
            == 1
        )
        await reconcile.background_done()

    # (the form's own suggestion is not confirmed here: its record stays)
    (example,) = examples(database)
    assert (example["stand_in"], example.get("taken"), example["direct"]) == (
        other,
        ids["jon"],
        False,
    )
    assert [r["id"] for r in kept(database)] == [mine]


@no_type_check
async def test_confirmed_as_an_entity_a_reconciled_mention_names_it_is_an_example_not_direct(
    database,
):
    m = worker_models()
    ids = await world(m, database)
    _, id, _ = await suggested(m, database, ids)

    with as_person(database, "bob"):
        assert await identify.confirm_as_entity([UUID(id)], ref(ids["jon"])) == 1
        await reconcile.background_done()

    (example,) = examples(database)
    assert (
        example["stand_in"],
        example.get("taken"),
        example["direct"],
        example["user"],
    ) == (id, ids["jon"], False, "bob")


@no_type_check
async def test_kept_with_keep_decisions_on_and_confirmed_with_it_off_makes_none(
    database, setting
):
    """The setting is read at the confirmation: off then, nothing is written (the worker's record stays, for the
    sweep)"""
    m = worker_models()
    ids = await world(m, database)
    _, id, record = await suggested(m, database, ids)
    assert record is not None
    setting("RECONCILE_KEEP_DECISIONS", False)

    await confirm(database, id, entity=ref(ids["jon"]))

    assert examples(database) == []
    assert [r["id"] for r in kept(database)] == [id]
