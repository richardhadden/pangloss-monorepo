"""Derived relations, on the backend under test: the cases of step 0 of the plan (two members of one family from two
factoids; one in a `Negative`; one through an `Identification` with two alternatives; a deleted factoid; an unpublished
one), and the worker's handling of writes"""

from typing import no_type_check

import pytest
from pangloss_models import initialise
from pangloss_models.model_bases.conjunction import Conjunction
from pangloss_models.model_bases.document import Document
from pangloss_models.model_bases.edge_model import EdgeModel
from pangloss_models.model_bases.entity import Entity
from pangloss_models.model_bases.helpers import ViaEdge
from pangloss_models.model_bases.reified_relation import ReifiedRelation
from pangloss_models.model_bases.semantic_space import SemanticSpace
from pangloss_testing.live import run

from pangloss_derived import Derived, DerivedMeta, RuleType, Var, rule
from pangloss_derived.worker import run_pending_derivations
from pangloss_derived import read

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def models(hypothetical_blocks: bool = False):
    class Probability(EdgeModel):
        percent: int

    class Negative[T](SemanticSpace[T]):
        pass

    class Hypothetical[T](SemanticSpace[T]):
        if hypothetical_blocks:
            _derived_meta = DerivedMeta(derivation="block")

    class Alternative[T](Conjunction):
        _derived_meta = DerivedMeta(exclusive=True)
        alternatives: list[T]

    class Identification[T](ReifiedRelation[T]):
        identified_by: str

    class Person(Entity):
        pass

    class Group(Entity):
        pass

    class MemberOf(Document):
        member: Person | Identification[Alternative[ViaEdge[Person, Probability]]]
        group: Group

    class Factoid(Document):
        statements: list[MemberOf | Negative[MemberOf] | Hypothetical[MemberOf]]

    family = RuleType("family", "Ties of family")

    class SameFamily(Derived):
        """Members of the same family"""

        _meta = Derived.Meta(symmetric=True)
        first: Person
        second: Person
        family: Group

    @rule(types=[family])
    def same_family(a: Var[Person], b: Var[Person], f: Var[Group]):
        """Two people said to be members of one family"""
        return SameFamily.Derive(first=a, second=b, family=f).when(
            MemberOf.Where(member=a, group=f),
            MemberOf.Where(member=b, group=f),
        )

    initialise()
    return Person, Group, MemberOf, Factoid, SameFamily


def member(person, group, *, label="m"):
    return {
        "type": "MemberOf",
        "label": label,
        "member": {"type": "Person", "id": person.id},
        "group": {"type": "Group", "id": group.id},
    }


def identified(group, *alternatives, label="m?"):
    return {
        "type": "MemberOf",
        "label": label,
        "member": {
            "type": "Identification",
            "identified_by": "Smith",
            "target": [
                {
                    "type": "Alternative",
                    "alternatives": [
                        {
                            "type": "Person",
                            "id": p.id,
                            "edge_properties": {"percent": pc},
                        }
                        for p, pc in alternatives
                    ],
                }
            ],
        },
        "group": {"type": "Group", "id": group.id},
    }


def inside(space, *statements):
    return {"type": space, "contents": list(statements)}


async def pairs(SameFamily):
    page = await read.list_facts(SameFamily, page_size=100)
    return sorted(
        (
            tuple(sorted([v.first.label, v.second.label])),
            v.family.label,
            tuple(v.context_labels),
            v.qualified_only,
        )
        for v in page["results"]
    )


@no_type_check
async def make(clear_database, **options):
    Person, Group, MemberOf, Factoid, SameFamily = models(**options)
    people = {n: await Person.Create(label=n).save() for n in ("A", "B", "C", "D")}
    group = await Group.Create(label="G").save()
    return Person, Group, Factoid, SameFamily, people, group


@no_type_check
async def test_two_members_of_one_family_in_two_factoids_are_of_the_same_family(
    clear_database,
):
    Person, Group, Factoid, SameFamily, p, g = await make(clear_database)
    await run_pending_derivations()
    await Factoid.Create(label="F1", statements=[member(p["A"], g)]).save()
    # (nothing is derived in the write itself)
    assert await pairs(SameFamily) == []
    await Factoid.Create(label="F2", statements=[member(p["B"], g)]).save()
    done = await run_pending_derivations()
    assert done["heads"] == 2
    assert await pairs(SameFamily) == [(("A", "B"), "G", (), False)]
    # (a third member: two more pairs)
    await Factoid.Create(label="F3", statements=[member(p["C"], g)]).save()
    await run_pending_derivations()
    assert [x[0] for x in await pairs(SameFamily)] == [
        ("A", "B"),
        ("A", "C"),
        ("B", "C"),
    ]


@no_type_check
async def test_a_member_in_a_negative_is_derived_with_its_context(clear_database):
    Person, Group, Factoid, SameFamily, p, g = await make(clear_database)
    await Factoid.Create(label="F1", statements=[member(p["A"], g)]).save()
    await Factoid.Create(
        label="F2", statements=[inside("Negative", member(p["B"], g))]
    ).save()
    await run_pending_derivations()
    assert await pairs(SameFamily) == [(("A", "B"), "G", ("Negative",), True)]


@no_type_check
async def test_a_blocked_space_derives_nothing(clear_database):
    Person, Group, Factoid, SameFamily, p, g = await make(
        clear_database, hypothetical_blocks=True
    )
    await Factoid.Create(label="F1", statements=[member(p["A"], g)]).save()
    await Factoid.Create(
        label="F2", statements=[inside("Hypothetical", member(p["B"], g))]
    ).save()
    await Factoid.Create(
        label="F3", statements=[inside("Negative", member(p["C"], g))]
    ).save()
    await run_pending_derivations()
    assert [x[0] for x in await pairs(SameFamily)] == [("A", "C")]


@no_type_check
async def test_an_identification_with_two_alternatives_gives_each_with_its_probability(
    clear_database,
):
    Person, Group, Factoid, SameFamily, p, g = await make(clear_database)
    await Factoid.Create(label="F1", statements=[member(p["A"], g)]).save()
    await Factoid.Create(
        label="F2", statements=[identified(g, (p["B"], 40), (p["C"], 60))]
    ).save()
    await run_pending_derivations()
    found = await pairs(SameFamily)
    # (not B with C: "Smith, who is B or C" says nothing of B and C together)
    assert found == [
        (("A", "B"), "G", ("Alternative", "Identification"), True),
        (("A", "C"), "G", ("Alternative", "Identification"), True),
    ]
    page = await read.list_facts(
        SameFamily, SameFamily.Where(first=p["A"], second=p["B"])
    )
    (fact,) = page["results"]
    detail = await read.get_fact(SameFamily, fact.id)
    (justification,) = detail.justifications
    assert justification.rule == "same_family"
    assert justification.description == "Two people said to be members of one family"
    assert sorted(e.label for e in justification.evidence) == ["F1", "F2"]
    relations = justification.context.relations
    assert [r["through"] for r in relations if r["field"] == "member"] == [
        [],
        ["Identification", "Alternative"],
    ]
    assert [r["properties"] for r in relations if r["field"] == "member"] == [
        {},
        {"percent": 40},
    ]


@no_type_check
async def test_deleting_a_factoid_hides_at_once_and_removes_when_the_worker_has_run(
    clear_database, db_driver
):
    Person, Group, Factoid, SameFamily, p, g = await make(clear_database)
    await Factoid.Create(label="F1", statements=[member(p["A"], g)]).save()
    f2 = await Factoid.Create(label="F2", statements=[member(p["B"], g)]).save()
    await run_pending_derivations()
    assert len(await pairs(SameFamily)) == 1
    await Factoid.delete(f2.id)
    # (hidden before the worker runs: its only justification rests on a deleted document)
    assert await pairs(SameFamily) == []
    assert run(db_driver, "MATCH (d:PGDerived) RETURN count(d) AS n")[0]["n"] == 1
    await run_pending_derivations()
    assert run(db_driver, "MATCH (d:PGDerived) RETURN count(d) AS n")[0]["n"] == 0
    assert run(db_driver, "MATCH (j:PGJustification) RETURN count(j) AS n")[0]["n"] == 0
    # (and back again)
    await Factoid.undelete(f2.id)
    await run_pending_derivations()
    assert len(await pairs(SameFamily)) == 1


@no_type_check
async def test_an_update_that_removes_a_member_removes_the_pair_and_one_that_changes_nothing_writes_nothing(
    clear_database, db_driver
):
    Person, Group, Factoid, SameFamily, p, g = await make(clear_database)
    await Factoid.Create(label="F1", statements=[member(p["A"], g)]).save()
    f2 = await Factoid.Create(
        label="F2", statements=[member(p["B"], g), member(p["C"], g)]
    ).save()
    await run_pending_derivations()
    assert [x[0] for x in await pairs(SameFamily)] == [
        ("A", "B"),
        ("A", "C"),
        ("B", "C"),
    ]
    # (a label changed: the statements are written again with new ids, so the justifications are new; the facts stay)
    keys = {r["key"] for r in run(db_driver, "MATCH (d:PGDerived) RETURN d.key AS key")}
    await Factoid.Update(
        id=f2.id, label="F2 again", statements=[member(p["B"], g), member(p["C"], g)]
    ).save()
    await run_pending_derivations()
    assert {
        r["key"] for r in run(db_driver, "MATCH (d:PGDerived) RETURN d.key AS key")
    } == keys
    assert run(db_driver, "MATCH (j:PGJustification) RETURN count(j) AS n")[0]["n"] == 3
    # (C taken out)
    await Factoid.Update(id=f2.id, label="F2", statements=[member(p["B"], g)]).save()
    await run_pending_derivations()
    assert [x[0] for x in await pairs(SameFamily)] == [("A", "B")]
    assert run(db_driver, "MATCH (j:PGJustification) RETURN count(j) AS n")[0]["n"] == 1


@no_type_check
async def test_an_unpublished_factoid_is_seen_only_by_who_may_see_it(
    clear_database, db_driver
):
    from pangloss_users import see_unpublished

    Person, Group, Factoid, SameFamily, p, g = await make(clear_database)
    await Factoid.Create(label="F1", statements=[member(p["A"], g)]).save()
    f2 = await Factoid.Create(label="F2", statements=[member(p["B"], g)]).save()
    # (as `pangloss-review` leaves a document that is not checked; derived from all the same)
    run(
        db_driver, "MATCH (h:HeadNode {id: $id}) SET h.published = false", id=str(f2.id)
    )
    await run_pending_derivations()
    token = see_unpublished.set(True)
    try:
        assert len(await pairs(SameFamily)) == 1
        see_unpublished.set(False)
        assert await pairs(SameFamily) == []
    finally:
        see_unpublished.reset(token)


@no_type_check
async def test_a_head_written_again_while_it_is_worked_on_is_done_again(
    clear_database, db_driver
):
    from pangloss_cypher import pending

    Person, Group, Factoid, SameFamily, p, g = await make(clear_database)
    await run_pending_derivations()
    await Factoid.Create(label="F1", statements=[member(p["A"], g)]).save()
    f2 = await Factoid.Create(label="F2", statements=[member(p["B"], g)]).save()
    from pangloss_derived.worker import KIND, database as db_of

    db = db_of()

    @db.write_transaction
    async def claim(tx):
        return await pending.claim(tx, KIND, 100, 60)

    claimed = await claim()
    assert len(claimed) == 2
    # (written again after the claim, and before the work is complete)
    await Factoid.Update(id=f2.id, label="F2", statements=[member(p["C"], g)]).save()

    @db.write_transaction
    async def complete(tx):
        return await pending.complete(tx, KIND, claimed)

    assert await complete() == 1
    assert run(db_driver, "MATCH (p:PGPending) RETURN p.head_id AS id") == [
        {"id": str(f2.id)}
    ]


@no_type_check
async def test_a_crash_between_claim_and_write_leaves_the_claim_to_run_out(
    clear_database, db_driver
):
    from pangloss_cypher import pending
    from pangloss_derived.worker import KIND, database as db_of

    Person, Group, Factoid, SameFamily, p, g = await make(clear_database)
    await run_pending_derivations()
    await Factoid.Create(label="F1", statements=[member(p["A"], g)]).save()
    await Factoid.Create(label="F2", statements=[member(p["B"], g)]).save()
    db = db_of()

    @db.write_transaction
    async def claim(tx, lease):
        return await pending.claim(tx, KIND, 100, lease)

    assert (
        len(await claim(-1)) == 2
    )  # (a claim that has already run out: the worker that made it is gone)
    await run_pending_derivations()
    assert len(await pairs(SameFamily)) == 1
    assert run(db_driver, "MATCH (p:PGPending) RETURN count(p) AS n")[0]["n"] == 0


@no_type_check
async def test_a_rule_type_gives_a_graph(clear_database):
    Person, Group, Factoid, SameFamily, p, g = await make(clear_database)
    await Factoid.Create(
        label="F1", statements=[member(p["A"], g), member(p["B"], g)]
    ).save()
    await run_pending_derivations()
    (edge,) = await read.graph("family")
    assert {edge["source"]["label"], edge["target"]["label"]} == {"A", "B"}
    assert edge["attributes"]["family"]["label"] == "G"
    assert (
        edge["class"] == "SameFamily" and edge["plain"] and edge["justifications"] == 1
    )


@no_type_check
async def test_derived_section_of_a_person_and_not_of_its_evidence(clear_database):
    Person, Group, Factoid, SameFamily, p, g = await make(clear_database)
    f1 = await Factoid.Create(
        label="F1", statements=[member(p["A"], g), member(p["B"], g)]
    ).save()
    await run_pending_derivations()
    section = await read.derived_section(Person, await Person.get(p["A"].id))
    family = section["_derived"]["SameFamily"]
    assert family["count"] == 1
    assert family["type"] == "SameFamily" and family["symmetricLabel"] is None
    (item,) = family["items"]
    assert item["other"]["label"] == "B"
    assert item["otherField"] in ("first", "second")
    assert item["fields"]["family"]["label"] == "G"
    # (a document does not show what it is evidence of: that is what it says itself)
    assert await read.derived_section(Factoid, await Factoid.get(f1.id)) == {}


@no_type_check
async def test_the_join_order_goes_out_from_the_seed(clear_database):
    from pangloss_derived.compile import join_order
    from pangloss_derived.registry import DerivedRegistry

    models()
    rule = DerivedRegistry.checked["same_family"]
    order = join_order(rule, "n_1")
    assert order[0] == "UNWIND $seeds AS seed"
    # (from the seed: its own relations first, then back from the family to the other member, then on to that one)
    assert [
        line.split("=")[1].split("-[")[0].strip() if "rp_" in line else line
        for line in order[1:]
        if "rp_" in line
    ] == [
        "(n_1)",
        "(n_1)",
        "(n_0)",
        "(n_0)",
    ]
    assert "re_3:`group`" in order[[i for i, x in enumerate(order) if "rp_" in x][1]]
    # (a symmetric body: each pair once, in order of id)
    from pangloss_derived.compile import compile_rule

    assert rule.symmetric_body and "v_a.id < v_b.id" in compile_rule(rule, "n_0")[0]


@no_type_check
async def test_the_background_worker_is_woken_by_a_write_and_derives_on_its_own(
    clear_database,
):
    import asyncio
    import time

    from pangloss_models import hooks
    from pangloss_derived.worker import Settings, Worker

    Person, Group, Factoid, SameFamily, p, g = await make(clear_database)
    # (it would look only every minute: the write wakes it)
    background = Worker(Settings(idle=60))
    hooks.after_write.append(background.listen)
    task = asyncio.create_task(background.run())
    try:
        await asyncio.sleep(0.3)  # (it has started: its rules are built)
        began = time.monotonic()
        await Factoid.Create(
            label="F1", statements=[member(p["A"], g), member(p["B"], g)]
        ).save()
        while not await pairs(SameFamily):
            assert time.monotonic() - began < 10, "the worker did not derive the pair"
            await asyncio.sleep(0.05)
        assert time.monotonic() - began < 5
    finally:
        task.cancel()
        hooks.after_write.remove(background.listen)
        try:
            await task
        except asyncio.CancelledError:
            pass
