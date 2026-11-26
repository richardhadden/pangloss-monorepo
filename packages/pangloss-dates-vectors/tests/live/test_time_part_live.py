"""The time part on the backend under test (implementation_docs/similarity-build-plan.md, step 9.3): the suite every
part passes (`pangloss_testing.parts.PartSuite`) on the dated models (`declare(dated=True)`, whose payloads then say
dates), whose slow way here reads every date with a query of its own and makes each item's vector with
`maths.vector`; and the part's own claims: whose vector a date is (a nested statement and its head, a range and a
period once, a wrapper's date for the head alone, a person born, an unknown date for nothing), what an update does to
them, a class without vectors, and a refresh before any rebuild."""

import json
from collections import defaultdict
from typing import Any, no_type_check

import pangloss_core.settings as core_settings
import pytest
from pangloss_dates_vectors import maths
from pangloss_dates_vectors.part import NAME, PART
from pangloss_models.citations import BASIS, CITATION_TYPES
from pangloss_models.spaces import registered_spaces, signature
from pangloss_testing.live import run
from pangloss_testing.parts import PartSuite, differences, one_turn, stored, writes
from pangloss_testing.parts.suite import drop_vector_indexes
from pangloss_vectors import Changed, Item, meta

pytestmark = pytest.mark.asyncio(loop_scope="session")

RING = maths.Ring(dimension=128, width=2.0)


def dates_query() -> str:
    """(written plainly here, not the part's: every date not held by a date and not only unknown, with what holds it,
    the holder's own stored path (not the date's, which the part reads) and its head, whose head is there, not
    deleted and not merged into another)"""
    from pangloss_core import backend

    path = backend.current().dialect.meta_property("n", "path")
    return f"""
    MATCH (d:Date)-[r]->(n)
    WHERE r.reverse = true AND NOT n:Date AND coalesce(d.precision, '') <> 'unknown'
    MATCH (h:HeadNode {{id: d.head_node_id}})
    WHERE NOT coalesce(h.deleted, false) AND h.merged_into IS NULL
    RETURN [d.earliest_fuzzy, d.earliest_strict, d.latest_strict, d.latest_fuzzy] AS bounds,
           n.id AS holder, n.type AS holder_type, labels(n) AS holder_labels, {path} AS holder_path,
           h.id AS head, h.type AS head_type
    """


def holder_denied(value: Any, labels: Any, spaces: dict) -> bool:
    """Whether the walk over the holder's stored path (a list, or JSON text on Neo4j) says it is denied; of a
    holder that is a wrapper, over the path of the statement the wrapper is in"""
    path = json.loads(value) if isinstance(value, str) else list(value or [])
    if {"ReifiedRelation", "Embedded"} & set(labels):
        while path and path[-1]["kind"] in ("reified", "embedded"):
            path.pop()
        path = path[:-1]
    return signature(path, spaces).veridical == -1


def dates_now(db_driver) -> dict[str, list[tuple[int, int, int, int]]]:
    """The dates each item has, by id: its head's and, if it is a document or an entity (not a citation), what holds
    it; none of a date whose holder is denied; only items of a class that has vectors"""
    found: dict[str, list[tuple[int, int, int, int]]] = defaultdict(list)
    skipped = {*CITATION_TYPES, BASIS}
    spaces = registered_spaces()
    for row in run(db_driver, dates_query()):
        if holder_denied(row["holder_path"], row["holder_labels"], spaces):
            continue
        items = {row["head"]: row["head_type"]}
        if {"Document", "Entity"} & set(row["holder_labels"]) and (
            row["holder_type"] not in skipped
        ):
            items[row["holder"]] = row["holder_type"]
        for of, type_name in items.items():
            if meta.included(type_name):
                found[of].append(tuple(row["bounds"]))
    return dict(found)


def vector(dates) -> Any:
    return maths.vector(dates, RING)


async def by_their_dates(db_driver) -> dict[str, Any]:
    """The slow way: every item's dates read now, and its vector from them"""
    return {of: vector(dates) for of, dates in dates_now(db_driver).items()}


class TestTheTimePart(PartSuite):
    parts = {"time": by_their_dates}
    dated = True


# ---------------------------------------------------------------------------
# The part's own
# ---------------------------------------------------------------------------


@pytest.fixture
def database(db_driver, clear_database):
    drop_vector_indexes(db_driver)
    yield db_driver
    drop_vector_indexes(db_driver)


@no_type_check
async def built(database) -> tuple[Any, dict[str, str]]:
    from pangloss_testing.similar_models import declare
    from pangloss_vectors.rebuild import rebuild

    m = declare(dated=True)
    ids = await writes.write_shapes(m, database)
    await rebuild()
    await one_turn(database)
    return m, ids


def held(database, holder: str) -> list[tuple[int, int, int, int]]:
    """The bounds of the dates the node holds itself (not those its dates hold)"""
    return [
        tuple(row["bounds"])
        for row in run(
            database,
            "MATCH (d:Date)-[r]->(n {id: $id}) WHERE r.reverse = true "
            "RETURN [d.earliest_fuzzy, d.earliest_strict, d.latest_strict, d.latest_fuzzy] AS bounds",
            id=holder,
        )
    ]


def dates_under(database, head: str) -> int:
    return run(
        database,
        "MATCH (d:PGIndexableNode {head_node_id: $head}) WHERE d:Date RETURN count(d) AS n",
        head=head,
    )[0]["n"]


@no_type_check
async def test_a_nested_statement_s_date_gives_it_and_its_head_a_vector_and_the_head_s_is_of_all_its_statements_dates(
    database,
):
    m, ids = await built(database)
    have = await stored(database, NAME)
    [fay], [gus] = held(database, ids["fay member"]), held(database, ids["gus member"])
    assert fay != gus
    want = {
        "fay member": vector([fay]),
        "gus member": vector([gus]),
        "members": vector([fay, gus]),
    }
    assert differences({name: have[ids[name]] for name in want}, want) == []
    # (and the head's is neither statement's)
    assert differences({"x": have[ids["members"]]}, {"x": vector([fay])}) != []
    # (a factoid whose statement has none has none; nor has that statement)
    assert ids["inference"] not in have and ids["inference statement"] not in have


@no_type_check
async def test_a_date_range_and_a_period_count_once_and_not_their_ends_as_well(
    database,
):
    from pangloss_vectors.rebuild import rebuild

    m, ids = await built(database)
    ranged = await m.Factoid.Create(
        label="a gift in a range",
        statements=[
            writes.dated(
                m,
                writes.transfer(writes.people(ids, "Ada", "Ben", "Cy")),
                when=writes.A_RANGE,
            )
        ],
    ).save()
    statement = str((await m.Factoid.get(ranged.id)).statements[0].id)
    await rebuild()
    await one_turn(database)
    have = await stored(database, NAME)
    # (the range and its two ends are three dates under the head; the range alone counts)
    assert dates_under(database, str(ranged.id)) == 3
    [range_] = held(database, statement)
    want = vector([range_])
    assert (
        differences(
            {"head": have[str(ranged.id)], "statement": have[statement]},
            {"head": want, "statement": want},
        )
        == []
    )

    # (a period from one year to another, which an update gives Fay's parent)
    await writes.update_that_replaces_its_statements(m, ids)
    await one_turn(database)
    have = await stored(database, NAME)
    assert dates_under(database, ids["Fay's parent"]) == 3
    [new] = [
        row["id"]
        for row in run(
            database,
            "MATCH (n:PGIndexableNode {head_node_id: $head}) WHERE n.type = 'Transfer' RETURN n.id AS id",
            head=ids["Fay's parent"],
        )
    ]
    [period] = held(database, new)
    assert (
        differences(
            {"head": have[ids["Fay's parent"]], "statement": have[new]},
            {"head": vector([period]), "statement": vector([period])},
        )
        == []
    )


@no_type_check
async def test_a_date_on_a_wrapper_counts_for_the_head_and_not_for_the_statement_that_holds_the_wrapper(
    database,
):
    m, ids = await built(database)
    have = await stored(database, NAME)
    [day] = held(database, ids["activity"])
    [during] = [
        tuple(row["bounds"])
        for row in run(
            database,
            "MATCH (d:Date)-[r]->(w:InRole) WHERE r.reverse = true AND d.head_node_id = $head "
            "RETURN [d.earliest_fuzzy, d.earliest_strict, d.latest_strict, d.latest_fuzzy] AS bounds",
            head=ids["meeting"],
        )
    ]
    assert (
        differences(
            {"activity": have[ids["activity"]], "meeting": have[ids["meeting"]]},
            {"activity": vector([day]), "meeting": vector([day, during])},
        )
        == []
    )
    # (the wrapper itself is no item)
    wrappers = [
        row["id"]
        for row in run(
            database,
            "MATCH (w:InRole {head_node_id: $head}) RETURN w.id AS id",
            head=ids["meeting"],
        )
    ]
    assert wrappers and not set(wrappers) & set(have)


@no_type_check
async def test_a_person_born_has_a_vector_and_loses_it_when_an_update_takes_the_date_away(
    database,
):
    m, ids = await built(database)
    have = await stored(database, NAME)
    [born] = held(database, ids["Ada"])
    assert differences({"Ada": have[ids["Ada"]]}, {"Ada": vector([born])}) == []
    assert ids["Ben"] not in have
    # (a date a head holds itself is under it: its `head_node_id` is the head's, which the refresh looks by)
    assert [
        row["head"]
        for row in run(
            database,
            "MATCH (d:Date)-[r]->(p:Person {id: $id}) WHERE r.reverse = true RETURN d.head_node_id AS head",
            id=ids["Ada"],
        )
    ] == [ids["Ada"]]

    await m.Person.Update(id=ids["Ada"], label="Ada").save()
    await one_turn(database)
    assert ids["Ada"] not in await stored(database, NAME)
    assert ids["Ada"] not in await by_their_dates(database)


@no_type_check
async def test_a_factoid_whose_update_changes_a_date_has_the_new_date_s_vector_after_one_turn(
    database,
):
    """("members": Fay's date changed, Gus's as it was. Not "gift": its statement is cited, and cannot change)"""
    m, ids = await built(database)
    before = (await stored(database, NAME))[ids["members"]]
    [gus] = held(database, ids["gus member"])
    await m.Factoid.Update(
        id=ids["members"],
        label="members",
        statements=[
            {
                "type": "MemberOf",
                "label": f"{name} of the guild",
                "member": writes.ref_to(ids[name]),
                "group": writes.ref_to(ids["group"], "Group"),
                "when": when,
            }
            for name, when in [
                ("Fay", {"type": "ExactDate", "year": 1550, "month": 4}),
                ("Gus", {"type": "ExactDate", "year": 1495, "month": 7}),
            ]
        ],
    ).save()
    await one_turn(database)
    have = await stored(database, NAME)
    new = {
        row["label"]: row["id"]
        for row in run(
            database,
            "MATCH (n:PGIndexableNode {head_node_id: $head}) WHERE n.type = 'MemberOf' "
            "RETURN n.id AS id, n.label AS label",
            head=ids["members"],
        )
    }
    [fay] = held(database, new["Fay of the guild"])
    assert held(database, new["Gus of the guild"]) == [gus]
    assert (
        differences(
            {
                "members": have[ids["members"]],
                "fay": have[new["Fay of the guild"]],
                "gus": have[new["Gus of the guild"]],
            },
            {
                "members": vector([fay, gus]),
                "fay": vector([fay]),
                "gus": vector([gus]),
            },
        )
        == []
    )
    assert differences({"x": before}, {"x": vector([fay, gus])}) != []
    # (the statements it replaced have none)
    assert not {ids["fay member"], ids["gus member"]} & set(have)


@no_type_check
async def test_a_factoid_whose_update_takes_every_date_away_has_none(database):
    m, ids = await built(database)
    assert ids["members"] in await stored(database, NAME)
    await m.Factoid.Update(
        id=ids["members"],
        label="members",
        statements=[
            {
                "type": "MemberOf",
                "label": f"{name} of the guild",
                "member": writes.ref_to(ids[name]),
                "group": writes.ref_to(ids["group"], "Group"),
            }
            for name in ["Fay", "Gus"]
        ],
    ).save()
    await one_turn(database)
    have = await stored(database, NAME)
    statements = [
        row["id"]
        for row in run(
            database,
            "MATCH (n:PGIndexableNode {head_node_id: $head}) WHERE n.type = 'MemberOf' RETURN n.id AS id",
            head=ids["members"],
        )
    ]
    assert len(statements) == 2
    assert not {ids["members"], *statements} & set(have)
    assert differences(have, await by_their_dates(database)) == []


@no_type_check
async def test_an_unknown_date_alone_gives_no_vector_and_a_range_with_one_end_unknown_gives_one(
    database,
):
    m, ids = await built(database)
    people = writes.people(ids, "Ada", "Ben", "Cy")
    vague = await m.Factoid.Create(
        label="vague",
        statements=[{**writes.transfer(people), "when": {"type": "UnknownDate"}}],
    ).save()
    half = await m.Factoid.Create(
        label="half",
        statements=[
            {
                **writes.transfer(people),
                "when": {
                    "type": "DateRange",
                    "not_before": {"type": "ExactDate", "year": 1500, "month": 8},
                    "not_after": {"type": "UnknownDate"},
                },
            }
        ],
    ).save()
    await one_turn(database)
    have = await stored(database, NAME)
    vague_statement = str((await m.Factoid.get(vague.id)).statements[0].id)
    half_statement = str((await m.Factoid.get(half.id)).statements[0].id)
    assert not {str(vague.id), vague_statement} & set(have)
    [range_] = held(database, half_statement)
    assert (
        differences(
            {"half": have[str(half.id)], "statement": have[half_statement]},
            {"half": vector([range_]), "statement": vector([range_])},
        )
        == []
    )


@no_type_check
async def test_a_class_excluded_gets_no_time_vector_while_its_head_still_does(
    database, monkeypatch
):
    monkeypatch.setattr(core_settings.SETTINGS, "VECTORS_EXCLUDE", ["Activity"])
    m, ids = await built(database)
    have = await stored(database, NAME)
    assert ids["activity"] not in have
    assert ids["meeting"] in have
    assert differences(have, await by_their_dates(database)) == []
    # (and after a write of the head, the same)
    await writes.update_that_drops_a_reference(m, ids)
    await one_turn(database)
    have = await stored(database, NAME)
    assert not {
        row["id"]
        for row in run(
            database,
            "MATCH (n:PGIndexableNode {head_node_id: $head}) WHERE n.type = 'Activity' RETURN n.id AS id",
            head=ids["meeting"],
        )
    } & set(have)
    assert differences(have, await by_their_dates(database)) == []


@no_type_check
async def test_a_head_written_of_a_class_that_no_longer_has_vectors_loses_its_time_vector(
    database, monkeypatch
):
    """(as a head whose class was changed in place to one without vectors: here `Person` is left out after the
    rebuild, and Ada, who still has her date, refreshed by the part alone: in a turn of the worker the class part,
    refreshed first, would take every vector of hers away, `store.set_vectors`)"""
    m, ids = await built(database)
    assert ids["Ada"] in await stored(database, NAME)
    monkeypatch.setattr(core_settings.SETTINGS, "VECTORS_EXCLUDE", ["Person"])
    written = []

    async def write(rows) -> None:
        written.extend(rows)

    refreshed = await PART.refresh(
        Changed(written=(Item(ids["Ada"], "Person"),)), write
    )
    assert (refreshed.written, written) == (0, [])
    have = await stored(database, NAME)
    assert ids["Ada"] not in have
    # (only the head written: Eve, born too, keeps hers until a rebuild, which the signature says is due)
    assert ids["Eve"] in have


@no_type_check
async def test_a_refresh_before_any_rebuild_writes_nothing_and_fails_nothing(database):
    from pangloss_testing.similar_models import declare

    m = declare(dated=True)
    ada = await m.Person.Create(
        label="Ada", born={"type": "ExactDate", "year": 1470}
    ).save()
    written = []

    async def write(rows) -> None:
        written.extend(rows)

    refreshed = await PART.refresh(
        Changed(written=(Item(str(ada.id), "Person"),)), write
    )
    assert (refreshed.written, refreshed.stale, written) == (0, 0, [])
    assert run(database, "MATCH (v:PGVector) RETURN count(v) AS n")[0]["n"] == 0
    # (and the worker's turn, which skips a part never built, neither)
    await one_turn(database)
    assert await stored(database, NAME) == {}


@no_type_check
async def test_a_person_born_merged_into_one_not_born_is_merged_and_the_survivor_has_the_date(
    database,
):
    from pangloss_testing.similar_models import declare

    m = declare(dated=True)
    born = await m.Person.Create(
        label="Eve", born={"type": "ExactDate", "year": 1475}
    ).save()
    unborn = await m.Person.Create(label="Dee").save()
    await m.Person.merge(absorb=born.id, into=unborn.id)
    assert (await m.Person.get(unborn.id)).born is not None


# ---------------------------------------------------------------------------
# A date that is denied (implementation_docs/spaces-and-comparison-plan.md, step 5.2, D4)
# ---------------------------------------------------------------------------


def statement_ids(database, head: str) -> dict[str, str]:
    """The statements under a head that are documents, by label"""
    return {
        row["label"]: row["id"]
        for row in run(
            database,
            "MATCH (n:PGIndexableNode {head_node_id: $head}) WHERE n:Statement "
            "RETURN n.id AS id, n.label AS label",
            head=head,
        )
    }


@no_type_check
async def test_a_dated_statement_in_a_not_has_no_time_vector_and_its_date_is_not_in_its_head_s(
    database,
):
    """("no gift": its one statement is in a `Negative`, so neither has a vector. "half denied": the same factoid
    with a statement beside it, whose date alone makes the head's vector)"""
    from pangloss_vectors.rebuild import rebuild

    m, ids = await built(database)
    have = await stored(database, NAME)
    assert dates_under(database, ids["no gift"]) == 3
    assert not {ids["no gift"], ids["denied"]} & set(have)

    people = writes.people(ids, "Ada", "Ben", "Cy")
    plain = {**writes.transfer(people), "label": "Ada gave to Ben, yes"}
    half = await m.Factoid.Create(
        label="half denied",
        statements=[
            {
                "type": "Negative",
                "contents": [
                    writes.dated(m, writes.transfer(people), when=writes.A_RANGE)
                ],
            },
            writes.dated(m, plain, when=writes.A_YEAR),
        ],
    ).save()
    await rebuild()
    await one_turn(database)
    have = await stored(database, NAME)
    under = statement_ids(database, str(half.id))
    [year] = held(database, under["Ada gave to Ben, yes"])
    assert under["Ada gave to Ben or Cy"] not in have
    assert (
        differences(
            {"head": have[str(half.id)], "plain": have[under["Ada gave to Ben, yes"]]},
            {"head": vector([year]), "plain": vector([year])},
        )
        == []
    )
    assert differences(have, await by_their_dates(database)) == []


@no_type_check
async def test_a_refresh_after_an_update_that_puts_a_dated_statement_in_a_not_removes_its_vector(
    database,
):
    """(a factoid of a `Negative` and two dated statements; its update moves one of them, with its id and date, into
    the `Negative`, which keeps its id too, in the place of the undated one it held: a "not" holds one)"""
    from pangloss_vectors.rebuild import rebuild

    m, ids = await built(database)
    people = writes.people(ids, "Ada", "Ben", "Cy")

    def statement(label: str, year: int | None = None) -> dict:
        payload = {**writes.transfer(people), "label": label}
        return (
            payload
            if year is None
            else {**payload, "when": {"type": "ExactDate", "year": year}}
        )

    made = await m.Factoid.Create(
        label="moved",
        statements=[
            {"type": "Negative", "contents": [statement("not given")]},
            statement("moved in", 1500),
            statement("left", 1530),
        ],
    ).save()
    await rebuild()
    await one_turn(database)
    under = statement_ids(database, str(made.id))
    have = await stored(database, NAME)
    assert under["moved in"] in have
    [moved], [left] = held(database, under["moved in"]), held(database, under["left"])

    read = await m.Factoid.get(made.id)
    negative, moved_in, kept = [
        s.model_dump(mode="json", exclude={"meta"}) for s in read.statements
    ]
    await m.Factoid.Update(
        id=str(made.id),
        label="moved",
        statements=[{**negative, "contents": [moved_in]}, kept],
    ).save()
    await one_turn(database)
    have = await stored(database, NAME)
    # (the same statement, with its date, under the `Negative` now)
    assert statement_ids(database, str(made.id)) == {
        "moved in": under["moved in"],
        "left": under["left"],
    }
    assert held(database, under["moved in"]) == [moved]
    assert under["moved in"] not in have
    assert (
        differences(
            {"head": have[str(made.id)], "left": have[under["left"]]},
            {"head": vector([left]), "left": vector([left])},
        )
        == []
    )
    assert differences(have, await by_their_dates(database)) == []


@no_type_check
async def test_the_overlay_of_a_plan_with_a_dated_statement_in_a_not_is_what_is_stored_after_it_is_written(
    database,
):
    from pangloss_cypher.write_functions import to_db_model, write_head_node
    from pangloss_cypher.write_plan import plan_create

    m, ids = await built(database)
    people = writes.people(ids, "Ada", "Ben", "Cy")
    plain = {**writes.transfer(people), "label": "Ada gave to Ben, yes"}
    instance = to_db_model(
        m.Factoid.Create(
            label="overlaid half denied",
            statements=[
                {
                    "type": "Negative",
                    "contents": [
                        writes.dated(m, writes.transfer(people), when=writes.A_RANGE)
                    ],
                },
                writes.dated(m, plain, when=writes.A_YEAR),
            ],
        )
    )
    head = str(instance.id)
    given = await PART.overlay(plan_create(instance))
    await write_head_node(instance)
    await one_turn(database)
    have = await stored(database, NAME)
    under = statement_ids(database, head)
    assert set(given) == {head, under["Ada gave to Ben, yes"]}
    assert under["Ada gave to Ben or Cy"] not in have
    assert differences(given, {of: have[of] for of in given}) == []


@no_type_check
async def test_a_dated_statement_in_a_space_that_does_not_deny_keeps_its_vector_and_cannot_have_been_does_not(
    database,
):
    """(`declare(compared=True)`: `Reported` and `Hypothetical` neither assert nor deny; `Negative[Hypothetical]`,
    "it cannot have been", is denied, the project's epistemic necessity committing)"""
    from pangloss_testing.similar_models import declare
    from pangloss_vectors.rebuild import rebuild

    m = declare(compared=True)
    ada = await m.Person.Create(label="Ada").save()
    ben = await m.Person.Create(label="Ben").save()

    def given(label: str, year: int) -> dict:
        return {
            "type": "Transfer",
            "label": label,
            "given_by": writes.ref(ada),
            "given_to": writes.ref(ben),
            "when": {"type": "ExactDate", "year": year},
        }

    made = await m.Factoid.Create(
        label="said and maybe",
        statements=[
            {"type": "Reported", "contents": [given("reported", 1500)]},
            {"type": "Hypothetical", "contents": [given("maybe", 1510)]},
            {
                "type": "Negative",
                "contents": [
                    {
                        "type": "Hypothetical",
                        "contents": [given("cannot have been", 1520)],
                    }
                ],
            },
        ],
    ).save()
    await rebuild()
    await one_turn(database)
    have = await stored(database, NAME)
    under = statement_ids(database, str(made.id))
    [reported], [maybe] = (
        held(database, under["reported"]),
        held(database, under["maybe"]),
    )
    assert under["cannot have been"] not in have
    assert (
        differences(
            {
                "head": have[str(made.id)],
                "reported": have[under["reported"]],
                "maybe": have[under["maybe"]],
            },
            {
                "head": vector([reported, maybe]),
                "reported": vector([reported]),
                "maybe": vector([maybe]),
            },
        )
        == []
    )
    assert differences(have, await by_their_dates(database)) == []
