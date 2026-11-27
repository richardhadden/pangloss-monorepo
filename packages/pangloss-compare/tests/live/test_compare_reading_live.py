"""Stored statements read as the verdict's plain data (`pangloss_compare.reading.read`;
implementation_docs/spaces-and-comparison-plan.md, step 6.3), on the backend under test, with
`similar_models.declare(compared=True)`: a handful of the planted world's shapes (`planted._compare`) written through
the models, each read as `tests/test_compare_maths.py`'s `statements_of` makes it of the same payload (the ids
those of the database, the dates as `pangloss_dates` stores them), and the verdict on them the planted world's truth."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, no_type_check
from uuid import uuid4

import pytest
from pangloss_compare import maths
from pangloss_compare.reading import read
from pangloss_compare.rules import rules
from pangloss_testing.live import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


def maths_tests() -> Any:
    """`tests/test_compare_maths.py` (in the folder above, which pytest puts on the path only when it collects it)"""
    name = "test_compare_maths"
    if name not in sys.modules:
        path = Path(__file__).parents[1] / f"{name}.py"
        spec = importlib.util.spec_from_file_location(name, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def ref(id: str, kind: str = "Person") -> dict[str, str]:
    return {"type": kind, "id": id}


def day(year: int, month: int | None = None, number: int | None = None) -> dict:
    said: dict[str, Any] = {"type": "ExactDate", "year": year}
    if month is not None:
        said["month"] = month
    if number is not None:
        said["day"] = number
    return said


def span(date: dict) -> maths.Span:
    """A date of a payload as `pangloss_dates` works it out (and stores it)"""
    from pangloss_models import ModelRegistry

    model: Any = ModelRegistry._model_dict[date["type"]]
    value = model.Create(**date)
    bounds, _ = model.work_out(value)
    return maths.Span.of(bounds)


ENTITIES = {
    "Person": ["guido", "maker", "host", "ada", "ben", "orderer", "doer", "receiver"],
    "Place": ["spoleto", "rome", "mill"],
    "Source": ["chronicle", "annals"],
    "Picture": ["picture"],
    "Group": ["guild"],
}


@no_type_check
async def entities(m) -> dict[str, str]:
    ids: dict[str, str] = {}
    for kind, names in ENTITIES.items():
        for name in names:
            ids[name] = str((await getattr(m, kind).Create(label=name).save()).id)
    return ids


def gathering(ids, label: str) -> dict:
    """A gathering with two guests in roles at the mill (`InRole.at`, a wrapper's own relation)"""
    return {
        "type": "Activity",
        "label": label,
        "when": day(1500, 5, 1),
        "carried_out_by": ref(ids["host"]),
        "participants": [
            {
                "type": "InRole",
                "role": "guest",
                "at": ref(ids["mill"], "Place"),
                "target": [ref(ids["ada"])],
            },  # fmt: skip
            {
                "type": "InRole",
                "role": "guest",
                "at": ref(ids["mill"], "Place"),
                "target": [ref(ids["ben"])],
            },  # fmt: skip
        ],
    }


def giving(ids, label: str, when: dict | None, to: str = "receiver", kind: str = "Person") -> dict:  # fmt: skip
    told = {
        "type": "Transfer",
        "label": label,
        "given_by": ref(ids["doer"]),
        "given_to": ref(ids[to], kind),
    }
    return told if when is None else {**told, "when": when}


def factoids(ids) -> list[dict]:
    """The planted world's shapes: a birth told twice, a making and a painting, a gathering asserted and denied, an
    order carried out, and a prohibition at odds with a group's statute"""
    return [
        {"type": "Factoid", "label": "The birth of Guido", "source": ref(ids["chronicle"], "Source"), "statements": [
            {"type": "Birth", "label": "Guido is born", "when": day(880, 3, 2), "person": ref(ids["guido"]), "place": ref(ids["spoleto"], "Place")},
        ]},
        {"type": "Factoid", "label": "Another account of the birth of Guido", "source": ref(ids["annals"], "Source"), "statements": [
            {"type": "Birth", "label": "Guido is born, again", "when": day(880), "person": ref(ids["guido"]), "place": ref(ids["spoleto"], "Place")},
        ]},
        {"type": "Factoid", "label": "A thing made", "source": ref(ids["chronicle"], "Source"), "statements": [
            {"type": "Making", "label": "The maker makes a thing", "when": day(1490, 6), "made_by": ref(ids["maker"]), "made": ref(ids["picture"], "Picture")},
        ]},
        {"type": "Factoid", "label": "A picture painted", "source": ref(ids["annals"], "Source"), "statements": [
            {"type": "MakingOfPicture", "label": "The maker paints a picture", "when": day(1490), "made_by": ref(ids["maker"]), "picture_made": ref(ids["picture"], "Picture")},
        ]},
        {"type": "Factoid", "label": "A gathering", "source": ref(ids["chronicle"], "Source"), "statements": [
            gathering(ids, "The host gathers people"),
        ]},
        {"type": "Factoid", "label": "No gathering", "source": ref(ids["annals"], "Source"), "statements": [
            {"type": "Negative", "contents": [gathering(ids, "The host did not gather people")]},
        ]},
        {"type": "Factoid", "label": "An order", "source": ref(ids["chronicle"], "Source"), "statements": [
            {"type": "Order", "label": "The orderer orders the doer", "when": day(1500, 5, 20), "ordered_by": ref(ids["orderer"]), "ordered_to": [ref(ids["doer"])],
             "thing_ordered": {"type": "Ordered", "contents": [giving(ids, "The doer is to give", day(1500, 6, 2))]}},
        ]},
        {"type": "Factoid", "label": "What the doer did", "source": ref(ids["annals"], "Source"), "statements": [
            giving(ids, "The doer gives", day(1500, 6, 2)),
        ]},
        {"type": "Factoid", "label": "A prohibition", "source": ref(ids["chronicle"], "Source"), "statements": [
            {"type": "Order", "label": "The orderer forbids the doer", "when": day(1500, 7, 1), "ordered_by": ref(ids["orderer"]), "ordered_to": [ref(ids["doer"])],
             "thing_ordered": {"type": "Forbidden", "contents": [giving(ids, "The doer is not to give to the guild", None, "guild", "Group")]}},
        ]},
        {"type": "Factoid", "label": "A statute of the guild", "source": ref(ids["annals"], "Source"), "statements": [
            {"type": "Rule", "label": "The statute of the guild", "when": day(1490), "ruled_by": ref(ids["guild"], "Group"), "binds": [ref(ids["doer"])],
             "ruled": {"type": "Obliged", "contents": [giving(ids, "The doer is to give to the guild", None, "guild", "Group")]}},
        ]},
    ]  # fmt: skip


# The planted world's truth of the pairs (by the labels of the statements): `planted.RELATION_OF`
TRUTH = {
    ("Guido is born", "Guido is born, again"): ("agree", ()),
    ("The maker makes a thing", "The maker paints a picture"): ("agree", ()),
    ("The host gathers people", "The host did not gather people"): (
        "contradiction",
        (),
    ),  # fmt: skip
    ("The doer is to give", "The doer gives"): ("carried_out", ()),
    ("The doer is not to give to the guild", "The doer is to give to the guild"): (
        "orders_at_odds",
        (),
    ),  # fmt: skip
}


def labels_of(payload: Any) -> list[dict]:
    """Every node of a payload that has a label, at any depth"""
    found: list[dict] = []
    if isinstance(payload, dict):
        if "label" in payload and "type" in payload:
            found.append(payload)
        for value in payload.values():
            found += labels_of(value)
    elif isinstance(payload, list):
        for value in payload:
            found += labels_of(value)
    return found


def expected(written: list[dict], stored: dict[str, str]) -> dict[str, maths.Told]:
    """What `statements_of` makes of the payloads, by the label of each statement, with the database's ids and the
    dates as `pangloss_dates` works them out"""
    import dataclasses

    by_label = {node["label"]: node for f in written for node in labels_of(f)}
    world = SimpleNamespace(
        factoids=written,
        events={},
        told={label: SimpleNamespace(event=label) for label in by_label},
    )
    made, _ = maths_tests().statements_of(world)
    found = {}
    holders = {"Order", "Rule"}
    for told in made:
        node = by_label[told.id]
        signature = told.signature
        if signature.prescribed_by is not None:
            signature = dataclasses.replace(signature, prescribed_by=stored[signature.prescribed_by])  # fmt: skip
        if signature.grounded_by is not None:
            signature = dataclasses.replace(
                signature,
                grounded_by=dataclasses.replace(
                    signature.grounded_by, head=stored[signature.grounded_by.head]
                ),  # fmt: skip
            )
        prescribed = told.prescribed
        if prescribed is not None:
            holder = next(
                n for n in by_label.values()
                if n["type"] in holders and node in labels_of(n)[1:]
            )  # fmt: skip
            prescribed = dataclasses.replace(prescribed, at=span(holder["when"]) if "when" in holder else None)  # fmt: skip
        found[told.id] = dataclasses.replace(
            told,
            id=stored[told.id],
            head=stored[told.head],
            signature=signature,
            dates={"when": span(node["when"])} if "when" in node else {},
            prescribed=prescribed,
        )
    return found


@no_type_check
async def written_world(
    m, db_driver
) -> tuple[list[dict], dict[str, str], dict[str, str]]:
    """The payloads written: the payloads, the entities' ids by name, and the stored ids by label"""
    ids = await entities(m)
    written = factoids(ids)
    for factoid in written:
        await m.Factoid.Create(**factoid).save()
    labels = sorted({node["label"] for f in written for node in labels_of(f)})
    rows = run(
        db_driver,
        "UNWIND $labels AS l MATCH (n:PGIndexableNode {label: l}) WHERE n:Document RETURN n.label AS label, n.id AS id",  # fmt: skip
        labels=labels,
    )
    stored = {r["label"]: r["id"] for r in rows}
    assert set(stored) == set(labels)
    return written, ids, stored


async def read_all(ids) -> dict[str, maths.Told]:
    from pangloss_core import backend

    database = backend.current().database()

    @database.read_transaction
    async def go(tx):
        return await read(tx, ids, see_unpublished=True)

    return await go()


@no_type_check
async def test_a_stored_statement_reads_as_statements_of_makes_its_payload(
    clear_database, db_driver
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    written, _, stored = await written_world(m, db_driver)
    want = expected(written, stored)
    # (two births, two makings, two gatherings, two orders and the rule, and what each of the three prescribes, and
    # what the doer did)
    assert len(want) == 13

    got = await read_all(list(stored.values()))

    # (the factoids, the spaces and the orders' holders are no statements of compared classes: only those)
    assert set(got) == {told.id for told in want.values()}
    for label, told in want.items():
        assert got[told.id] == told, label


@no_type_check
async def test_the_verdict_on_the_stored_pairs_is_the_planted_truth(
    clear_database, db_driver
):
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    _, _, stored = await written_world(m, db_driver)
    got = await read_all(list(stored.values()))

    for (a, b), (relation, fields) in TRUTH.items():
        found = maths.verdict(got[stored[a]], got[stored[b]], rules())
        assert (found.relation, found.fields) == (relation, fields), (a, b)


@no_type_check
async def test_what_is_not_a_compared_statement_is_not_read(clear_database, db_driver):
    """An id that is not there, an entity, a factoid, a space, a statement of a class that is not compared"""
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    _, ids, stored = await written_world(m, db_driver)
    member = await m.Factoid.Create(
        label="A member",
        statements=[
            {
                "type": "MemberOf",
                "label": "Ada is a member",
                "member": ref(ids["ada"]),
                "group": ref(ids["guild"], "Group"),
            }
        ],  # fmt: skip
    ).save()
    spaces = run(db_driver, "MATCH (n:SemanticSpace) RETURN n.id AS id")
    member_statement = run(db_driver, "MATCH (n:MemberOf) RETURN n.id AS id")[0]["id"]

    got = await read_all(
        [
            str(uuid4()),
            ids["ada"],
            str(member.id),
            member_statement,
            *[r["id"] for r in spaces],
        ]  # fmt: skip
    )

    assert got == {}


@no_type_check
async def test_a_statement_inside_a_space_left_out_of_comparison_is_not_read(
    clear_database, db_driver
):
    from pangloss_compare import CompareMeta
    from pangloss_models import ModelRegistry
    from pangloss_testing.similar_models import declare

    m = declare(compared=True)
    _, _, stored = await written_world(m, db_driver)
    # (the denial's space, as if it said `CompareMeta(compared=False)`)
    ModelRegistry._model_dict["Negative"]._compare_meta = CompareMeta(compared=False)
    try:
        got = await read_all(list(stored.values()))
    finally:
        del ModelRegistry._model_dict["Negative"]._compare_meta

    assert stored["The host did not gather people"] not in got
    assert stored["The host gathers people"] in got
