"""Rules of more than two patterns, a node shared by patterns, literal values in the head, constraints, a rule changed or
removed, the limit per seed, and what does not trigger anything"""

from typing import no_type_check

import pytest
from pangloss_models import Document, Entity, ReifiedRelation, SemanticSpace, initialise
from pangloss_testing.live import run

from pangloss_derived import Derived, DerivedMeta, RuleType, Var, read, rule
from pangloss_derived.registry import DerivedRegistry
from pangloss_derived.worker import run_pending_derivations, worker

pytestmark = pytest.mark.asyncio(loop_scope="session")


@no_type_check
def office_models(max_per_seed: int = 10_000, reported: str = "qualify"):
    class Reported[T](SemanticSpace[T]):
        _derived_meta = DerivedMeta(derivation=reported)

    class InRole[T](ReifiedRelation[T]):
        role: str

    class Person(Entity):
        pass

    class Office(Entity):
        pass

    class Organisation(Entity):
        pass

    class Place(Entity):
        pass

    class HoldsOffice(Document):
        person: Person
        office: Office
        year: int

    class OfficeIn(Document):
        office: Office
        organisation: Organisation

    class Meeting(Document):
        participants: list[Person | InRole[Person]]
        place: Place

    class Factoid(Document):
        statements: list[HoldsOffice | OfficeIn | Meeting | Reported[HoldsOffice]]

    social = RuleType("social", "Social ties")

    class SameOrganisation(Derived):
        """Held offices in the same organisation"""

        _meta = Derived.Meta(symmetric=True, max_per_seed=max_per_seed)
        first: Person
        second: Person
        organisation: Organisation

    class HeldOfficeInYear(Derived):
        person: Person
        organisation: Organisation
        year: int

    class Met(Derived):
        _meta = Derived.Meta(symmetric=True)
        first: Person
        second: Person
        place: Place

    @rule(types=[social])
    def same_organisation(
        a: Var[Person],
        b: Var[Person],
        office_a: Var[Office],
        office_b: Var[Office],
        org: Var[Organisation],
    ):
        return SameOrganisation.Derive(first=a, second=b, organisation=org).when(
            HoldsOffice.Where(person=a, office=office_a),
            HoldsOffice.Where(person=b, office=office_b),
            OfficeIn.Where(office=office_a, organisation=org),
            OfficeIn.Where(office=office_b, organisation=org),
        )

    @rule
    def held_office_in_year(
        a: Var[Person], o: Var[Office], org: Var[Organisation], y: Var[int]
    ):
        return HeldOfficeInYear.Derive(person=a, organisation=org, year=y).when(
            HoldsOffice.Where(person=a, office=o, year=y),
            OfficeIn.Where(office=o, organisation=org),
            y > 1400,
        )

    @rule(types=[social])
    def met(a: Var[Person], b: Var[Person], m: Var[Meeting], p: Var[Place]):
        return Met.Derive(first=a, second=b, place=p).when(
            Meeting.Where(is_=m, participants=a, place=p),
            Meeting.Where(is_=m, participants=b),
        )

    initialise()
    return {k: v for k, v in locals().items() if isinstance(v, type)}


def ref(entity):
    return {
        "type": type(entity).__name__.removesuffix("ReferenceView"),
        "id": entity.id,
    }


@no_type_check
async def setup(clear_database, **options):
    m = office_models(**options)
    names = {}
    for kind, labels in {
        "Person": "ABCDE",
        "Office": ["Chancellor", "Notary", "Bishop"],
        "Organisation": ["Court", "Church"],
        "Place": ["Vienna"],
    }.items():
        for label in labels:
            names[label] = await m[kind].Create(label=label).save()
    await run_pending_derivations()
    return m, names


def holds(person, office, year=1450):
    return {
        "type": "HoldsOffice",
        "label": "h",
        "person": ref(person),
        "office": ref(office),
        "year": year,
    }


def office_in(office, organisation):
    return {
        "type": "OfficeIn",
        "label": "o",
        "office": ref(office),
        "organisation": ref(organisation),
    }


async def labels(model, **where):
    page = await read.list_facts(
        model, model.Where(**where) if where else None, page_size=100
    )
    out = []
    for v in page["results"]:
        data = v.model_dump()
        out.append(
            tuple(
                data[f]["label"] if isinstance(data[f], dict) else data[f]
                for f in model._fields
            )
        )
    return sorted(out)


@no_type_check
async def test_four_patterns_give_people_of_one_organisation(clear_database):
    m, n = await setup(clear_database)
    F = m["Factoid"]
    await F.Create(label="1", statements=[holds(n["A"], n["Chancellor"])]).save()
    await F.Create(label="2", statements=[holds(n["B"], n["Notary"])]).save()
    await run_pending_derivations()
    assert await labels(m["SameOrganisation"]) == []
    # (the offices are said to be of the court only now: the pair follows from a write of a third factoid)
    await F.Create(
        label="3",
        statements=[
            office_in(n["Chancellor"], n["Court"]),
            office_in(n["Notary"], n["Court"]),
        ],
    ).save()
    await run_pending_derivations()
    assert await labels(m["SameOrganisation"]) == [("A", "B", "Court")]
    # (and the literal of the head, with the constraint y > 1400)
    assert await labels(m["HeldOfficeInYear"]) == [
        ("A", "Court", 1450),
        ("B", "Court", 1450),
    ]
    await F.Create(label="4", statements=[holds(n["C"], n["Notary"], year=1300)]).save()
    await run_pending_derivations()
    assert await labels(m["HeldOfficeInYear"]) == [
        ("A", "Court", 1450),
        ("B", "Court", 1450),
    ]
    assert await labels(m["SameOrganisation"]) == [
        ("A", "B", "Court"),
        ("A", "C", "Court"),
        ("B", "C", "Court"),
    ]


@no_type_check
async def test_a_node_shared_by_two_patterns(clear_database):
    m, n = await setup(clear_database)
    meeting = {
        "type": "Meeting",
        "label": "m",
        "participants": [
            ref(n["A"]),
            {"type": "InRole", "role": "host", "target": [ref(n["B"])]},
            ref(n["C"]),
        ],
        "place": ref(n["Vienna"]),
    }
    await m["Factoid"].Create(label="1", statements=[meeting]).save()
    await run_pending_derivations()
    assert await labels(m["Met"]) == [
        ("A", "B", "Vienna"),
        ("A", "C", "Vienna"),
        ("B", "C", "Vienna"),
    ]
    # (one meeting each: nobody met anybody)
    await (
        m["Factoid"]
        .Create(label="2", statements=[{**meeting, "participants": [ref(n["D"])]}])
        .save()
    )
    await run_pending_derivations()
    assert len(await labels(m["Met"])) == 3


@no_type_check
@pytest.mark.parametrize(
    "reported, expected", [("qualify", ["Reported"]), ("transparent", [])]
)
async def test_a_transparent_space_is_left_out_of_the_context(
    clear_database, reported, expected
):
    m, n = await setup(clear_database, reported=reported)
    F = m["Factoid"]
    await F.Create(
        label="1",
        statements=[
            holds(n["A"], n["Chancellor"]),
            office_in(n["Chancellor"], n["Court"]),
        ],
    ).save()
    await F.Create(
        label="2",
        statements=[{"type": "Reported", "contents": [holds(n["B"], n["Chancellor"])]}],
    ).save()
    await run_pending_derivations()
    page = await read.list_facts(m["SameOrganisation"])
    (fact,) = page["results"]
    assert fact.context_labels == expected
    assert fact.qualified_only == bool(expected)


@no_type_check
async def test_writes_of_a_class_no_rule_is_about_leave_nothing_pending(
    clear_database, db_driver
):
    m, n = await setup(clear_database)
    await m["Person"].Create(label="F").save()
    await m["Place"].Update(id=n["Vienna"].id, label="Wien").save()
    assert run(db_driver, "MATCH (p:PGPending) RETURN count(p) AS n")[0]["n"] == 0
    await m["Factoid"].Create(label="1", statements=[]).save()
    assert run(db_driver, "MATCH (p:PGPending) RETURN count(p) AS n")[0]["n"] == 1
    assert sorted(DerivedRegistry.triggers) == [
        "Factoid",
        "HoldsOffice",
        "Meeting",
        "OfficeIn",
    ]


@no_type_check
async def test_a_seed_past_the_limit_gives_nothing_and_is_counted(
    clear_database, db_driver
):
    m, n = await setup(clear_database, max_per_seed=2)
    F = m["Factoid"]
    for person in "ABCD":
        await F.Create(
            label=person, statements=[holds(n[person], n["Chancellor"])]
        ).save()
    await run_pending_derivations()
    await F.Create(
        label="court", statements=[office_in(n["Chancellor"], n["Court"])]
    ).save()
    await run_pending_derivations()
    # (the OfficeIn gives 6 pairs, more than 2: none are written from it; each HoldsOffice gives at most 3 from
    # its own seed, but those were written before there was an OfficeIn)
    assert await labels(m["SameOrganisation"]) == []
    state = run(
        db_driver,
        "MATCH (r:PGDeriveRule {name: 'same_organisation'}) RETURN r.overflows AS n",
    )
    assert state[0]["n"] >= 1


@no_type_check
async def test_a_changed_rule_is_built_again_and_a_removed_one_is_taken_away(
    clear_database, db_driver
):
    m, n = await setup(clear_database)
    F = m["Factoid"]
    await F.Create(
        label="1",
        statements=[holds(n["A"], n["Chancellor"]), holds(n["B"], n["Notary"])],
    ).save()
    await F.Create(
        label="2",
        statements=[
            office_in(n["Chancellor"], n["Court"]),
            office_in(n["Notary"], n["Court"]),
        ],
    ).save()
    await run_pending_derivations()
    assert await labels(m["SameOrganisation"]) == [("A", "B", "Court")]
    first_hash = DerivedRegistry.checked["same_organisation"].hash

    # (the same models, and a rule changed: only the same office counts now)
    HoldsOffice, OfficeIn = m["HoldsOffice"], m["OfficeIn"]
    SameOrganisation, Person, Office, Organisation = (
        m[k] for k in ("SameOrganisation", "Person", "Office", "Organisation")
    )

    @rule(name="same_organisation")
    def changed(
        a: Var[Person], b: Var[Person], office: Var[Office], org: Var[Organisation]
    ):
        return SameOrganisation.Derive(first=a, second=b, organisation=org).when(
            HoldsOffice.Where(person=a, office=office),
            HoldsOffice.Where(person=b, office=office),
            OfficeIn.Where(office=office, organisation=org),
        )

    del DerivedRegistry.rules["met"]
    from pangloss_derived import initialise as initialise_derived

    initialise_derived()
    assert DerivedRegistry.checked["same_organisation"].hash != first_hash
    done = await run_pending_derivations()
    assert done["rules"] == {"same_organisation": "built", "met": "removed"}
    assert await labels(m["SameOrganisation"]) == []
    assert run(
        db_driver, "MATCH (r:PGDeriveRule) RETURN r.name AS name ORDER BY name"
    ) == [
        {"name": "held_office_in_year"},
        {"name": "same_organisation"},
    ]
    await F.Create(label="3", statements=[holds(n["C"], n["Chancellor"])]).save()
    await run_pending_derivations()
    assert await labels(m["SameOrganisation"]) == [("A", "C", "Court")]


@no_type_check
async def test_rebuild_finds_what_was_written_without_marks_and_removes_what_is_wrong(
    clear_database, db_driver
):
    m, n = await setup(clear_database)
    F = m["Factoid"]
    await F.Create(
        label="1",
        statements=[holds(n["A"], n["Chancellor"]), holds(n["B"], n["Chancellor"])],
    ).save()
    await F.Create(
        label="2", statements=[office_in(n["Chancellor"], n["Court"])]
    ).save()
    # (as a bulk load leaves it: nothing pending)
    run(db_driver, "MATCH (p:PGPending) DELETE p")
    await run_pending_derivations()
    assert await labels(m["SameOrganisation"]) == []
    counts = await worker.rebuild(DerivedRegistry.checked["same_organisation"])
    assert counts["new"] == 1 and counts["removed"] == 0
    assert await labels(m["SameOrganisation"]) == [("A", "B", "Court")]
    # (a fact written by hand that nothing justifies is removed by a rebuild)
    run(
        db_driver,
        "MATCH (d:PGDerived) MATCH (h:HeadNode {label: '1'}) "
        "CREATE (j:PGJustification {key: 'stray', rule: 'same_organisation', context_labels: [], types: []})-[:justifies]->(d), "
        "(j)-[:evidence]->(h)",
    )
    counts = await worker.rebuild(DerivedRegistry.checked["same_organisation"])
    assert counts["removed"] == 1


@no_type_check
async def test_a_rule_type_spans_classes(clear_database):
    m, n = await setup(clear_database)
    F = m["Factoid"]
    meeting = {
        "type": "Meeting",
        "label": "m",
        "participants": [ref(n["A"]), ref(n["E"])],
        "place": ref(n["Vienna"]),
    }
    await F.Create(
        label="1",
        statements=[
            holds(n["A"], n["Chancellor"]),
            holds(n["B"], n["Chancellor"]),
            office_in(n["Chancellor"], n["Court"]),
            meeting,
        ],
    ).save()
    await run_pending_derivations()
    edges = await read.graph("social")
    assert sorted(
        (e["class"], e["source"]["label"], e["target"]["label"]) for e in edges
    ) == [
        ("Met", "A", "E"),
        ("SameOrganisation", "A", "B"),
    ] or sorted(
        (e["class"], *sorted([e["source"]["label"], e["target"]["label"]]))
        for e in edges
    ) == [
        ("Met", "A", "E"),
        ("SameOrganisation", "A", "B"),
    ]
    assert all(
        set(e) >= {"source", "target", "attributes", "justifications", "plain"}
        for e in edges
    )


@no_type_check
async def test_a_variable_of_a_list_field_is_one_of_its_items(clear_database):
    """Two people with an alias in common (a list field), and the alias in the head"""

    class Person(Entity):
        aliases: list[str]

    class Statement(Document):
        about: Person

    class SharesAlias(Derived):
        _meta = Derived.Meta(symmetric=True)
        first: Person
        second: Person
        alias: str

    @rule
    def shares_alias(a: Var[Person], b: Var[Person], name: Var[str]):
        return SharesAlias.Derive(first=a, second=b, alias=name).when(
            Person.Where(is_=a, aliases=name),
            Person.Where(is_=b, aliases=name),
        )

    initialise()
    assert "Person" in DerivedRegistry.triggers
    await Person.Create(label="A", aliases=["Al", "Bert"]).save()
    await Person.Create(label="B", aliases=["Bert", "Cy"]).save()
    await Person.Create(label="C", aliases=["Cy", "Al"]).save()
    await Person.Create(label="D", aliases=["Dee"]).save()
    await run_pending_derivations()
    assert await labels(SharesAlias) == [
        ("A", "B", "Bert"),
        ("A", "C", "Al"),
        ("B", "C", "Cy"),
    ]
    # (an alias taken away: the pair goes)
    b = (await Person.list(search_terms="B")).results[0]
    await Person.Update(id=b.id, label="B", aliases=["Cy"]).save()
    await run_pending_derivations()
    assert await labels(SharesAlias) == [("A", "C", "Al"), ("B", "C", "Cy")]


@no_type_check
async def test_a_derived_class_in_a_search(clear_database):
    """`Person.Where(derived_=SameOrganisation.Where(organisation=court))`: the people with such a fact"""
    from pangloss_models import Match, PanglossSearchError

    m, n = await setup(clear_database)
    F = m["Factoid"]
    await F.Create(
        label="1",
        statements=[
            holds(n["A"], n["Chancellor"]),
            holds(n["B"], n["Notary"]),
            holds(n["C"], n["Bishop"]),
            office_in(n["Chancellor"], n["Court"]),
            office_in(n["Notary"], n["Court"]),
            office_in(n["Bishop"], n["Church"]),
        ],
    ).save()
    await run_pending_derivations()
    Person, SameOrganisation = m["Person"], m["SameOrganisation"]

    async def found(where):
        return sorted(p.label for p in (await Person.search(where)).results)

    assert await found(Person.Where(derived_=SameOrganisation.Where())) == ["A", "B"]
    assert await found(
        Person.Where(derived_=SameOrganisation.Where(organisation=n["Court"]))
    ) == ["A", "B"]
    assert (
        await found(
            Person.Where(derived_=SameOrganisation.Where(organisation=n["Church"]))
        )
        == []
    )
    assert await found(
        Person.Where(derived_=SameOrganisation.Where(rule_type="social"))
    ) == ["A", "B"]
    assert (
        await found(Person.Where(derived_=SameOrganisation.Where(rule_type="nothing")))
        == []
    )
    # (the JSON, as the API takes it; and with the person's own conditions)
    assert await found(
        Match(where={"$derived": {"type": "SameOrganisation"}, "label": {"eq": "A"}})
    ) == ["A"]
    # (not an entity, or an unknown class, or a class with no field of the kind)
    with pytest.raises(PanglossSearchError, match="only for entity patterns"):
        await m["Factoid"].search(
            Match(where={"$derived": {"type": "SameOrganisation"}})
        )
    with pytest.raises(PanglossSearchError, match="no derived class called"):
        await Person.search(Match(where={"$derived": {"type": "Nothing"}}))
    with pytest.raises(
        PanglossSearchError, match="no field of SameOrganisation is a Place"
    ):
        await m["Place"].search(Match(where={"$derived": {"type": "SameOrganisation"}}))
