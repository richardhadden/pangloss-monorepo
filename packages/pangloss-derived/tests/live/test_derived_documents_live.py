"""Derived documents on the backend under test, nobody writes one but the worker (and what
the worker writes records its rule); what a rule that derives documents finds (each pair once, nothing through what
qualifies unless allowed, its sources), written through its template as the worker will write it; a rule that reads
derived documents, and one that blocks them; the routes and the commands"""

from typing import Annotated, no_type_check

import httpx2 as httpx
import pytest
from pangloss_api import create_app
from pangloss_models import Document, Entity, SemanticSpace, Text, initialise

from pangloss_derived import (
    DerivedDocument,
    DerivedDocumentMeta,
    DerivedEdge,
    DerivedFrom,
    PanglossDerivedDocumentError,
    SymmetricLabel,
    Var,
    read,
    rule,
    store,
    unordered,
    writing_derived,
)
from pangloss_derived.registry import DerivedRegistry
from pangloss_derived.templates import fill
from pangloss_derived.worker import database, run_pending_derivations

pytestmark = pytest.mark.asyncio(loop_scope="session")


class Names(dict):
    __getattr__ = dict.__getitem__


@no_type_check
def models(max_per_seed=2_000):
    class Negative[T](SemanticSpace[T]):
        pass

    class Person(Entity):
        pass

    class Statement(Document):
        _meta = Document.Meta(abstract=True, create_directly=False)

    class ChildOf(Statement):
        child: Person
        parent: Person

    class Sibling(Statement):
        people: list[Person]
        kind: str = "full"

    class Factoid(Document):
        statements: list[Statement | Negative[Statement]]

    class Hearsay(Document):
        statements: list[Sibling]

    class DerivedFactoid(Document, DerivedDocument):
        """What follows from what factoids say"""

        _derived_document_meta = DerivedDocumentMeta(max_per_seed=max_per_seed)
        sources: list[DerivedFrom[Factoid | DerivedFactoid]]
        statements: list[Statement]

    class Kin(DerivedEdge):
        """Said to be siblings, by anyone or anything"""

        _meta = DerivedEdge.Meta(symmetric=True)
        first: Annotated[Person, SymmetricLabel("kin")]
        second: Annotated[Person, SymmetricLabel("kin")]

    class SaidKin(DerivedEdge):
        """Said to be siblings by what people wrote"""

        _meta = DerivedEdge.Meta(symmetric=True)
        first: Annotated[Person, SymmetricLabel("kin")]
        second: Annotated[Person, SymmetricLabel("kin")]

    @rule
    def siblings(a: Var[Person], b: Var[Person], p: Var[Person]):
        """Two children of one parent are siblings"""
        return DerivedFactoid.Derive(
            label="Siblings",
            statements=[
                Sibling.Template(label="Siblings", people=[a, b], kind="derived")
            ],
        ).when(
            ChildOf.Where(child=a, parent=p),
            ChildOf.Where(child=b, parent=p),
            unordered(a, b),
        )

    @rule
    def siblings_even_if_denied(a: Var[Person], b: Var[Person], p: Var[Person]):
        return DerivedFactoid.Derive(
            label="Siblings?",
            statements=[Sibling.Template(label="Siblings?", people=[a, b])],
        ).when(
            ChildOf.Where(child=a, parent=p),
            ChildOf.Where(child=b, parent=p),
            unordered(a, b),
            allow=[Negative],
        )

    @rule
    def kin(s: Var[Sibling], a: Var[Person], b: Var[Person]):
        return Kin.Derive(first=a, second=b).when(
            Sibling.Where(is_=s, people=a), Sibling.Where(is_=s, people=b)
        )

    @rule
    def said_kin(s: Var[Sibling], a: Var[Person], b: Var[Person]):
        return SaidKin.Derive(first=a, second=b).when(
            Sibling.Where(is_=s, people=a),
            Sibling.Where(is_=s, people=b),
            block=[DerivedFactoid, Hearsay],
        )

    initialise()
    return Names(locals())


def ref(item):
    return {"type": "Person", "id": item.id}


def child_of(child, parent):
    return {"type": "ChildOf", "label": "c", "child": ref(child), "parent": ref(parent)}


async def people(m, names):
    return Names({n: await m.Person.Create(label=n).save() for n in names})


async def found(name):
    """What the rule finds in the data as it is: its justifications, each to be one document"""
    checked = DerivedRegistry.documents[name]
    db = database()

    @db.read_transaction
    async def find(tx):
        seed = checked.seeds[0]
        ids = await store.ids_of_class(tx, seed.model.__name__)
        result = store.Found()
        await store.run_seeded(tx, checked, seed.node, ids, result)
        return result

    return await find()


async def write(m, name, justification, source="Factoid"):
    """A document of a justification, written as the worker will: its template filled, its sources those of the
    justification, inside `writing_derived`"""
    checked = DerivedRegistry.documents[name]
    payload = fill(
        checked.template,
        {k: {"type": "Person", "id": v} for k, v in justification.values.items()},
    )
    payload["sources"] = [{"type": source, "id": s} for s in justification.sources]
    with writing_derived(name, justification.context_labels):
        return await m.DerivedFactoid.Create.model_validate(payload).save()


def pairs(n, result):
    """The pairs of people of the justifications, by label"""
    labels = {str(p.id): label for label, p in n.items()}
    return sorted(
        tuple(labels[str(v)] for v in j.values.values())
        for j in result.documents.values()
    )


async def edges(m, name):
    page = await read.list_facts(m[name], page_size=100)
    return sorted(
        tuple(sorted((v.first.label, v.second.label))) for v in page["results"]
    )


# ---------------------------------------------------------------------------
# Nobody writes one but the worker
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_derived_document_is_written_only_inside_writing_derived(
    clear_database,
):
    m = models()
    n = await people(m, "AB")
    statement = {"type": "Sibling", "label": "s", "people": [ref(n.A), ref(n.B)]}
    with pytest.raises(PanglossDerivedDocumentError) as refused:
        await m.DerivedFactoid.Create(
            label="Mine", sources=[], statements=[statement]
        ).save()
    assert "A DerivedFactoid is derived: it is not made by hand" in str(refused.value)
    assert "convert it" in str(refused.value)
    assert (await m.DerivedFactoid.list()).results == []

    with writing_derived("siblings", ["Negative"]):
        made = await m.DerivedFactoid.Create(
            label="Derived", sources=[], statements=[statement]
        ).save()
    (listed,) = (await m.DerivedFactoid.list()).results
    assert listed.id == made.id
    # (what it was written for is recorded, and read with every reference to it)
    assert listed.derived_by == "siblings" and listed.derived_context == ["Negative"]
    # (a document people write is written as ever)
    await m.Factoid.Create(label="F", statements=[child_of(n.A, n.B)]).save()

    with pytest.raises(PanglossDerivedDocumentError, match="it is not changed by hand"):
        await m.DerivedFactoid.Update(
            id=made.id, label="Changed", sources=[], statements=[]
        ).save()
    assert (await m.DerivedFactoid.get(made.id)).label == "Derived"
    with writing_derived("siblings"):
        await m.DerivedFactoid.Update(
            id=made.id, label="Changed", sources=[], statements=[statement]
        ).save()
    (listed,) = (await m.DerivedFactoid.list()).results
    assert listed.label == "Changed" and listed.derived_context == []

    with pytest.raises(PanglossDerivedDocumentError, match="it is not deleted by hand"):
        await m.DerivedFactoid.delete(made.id)
    assert await m.DerivedFactoid.get(made.id) is not None
    with writing_derived("siblings"):
        await m.DerivedFactoid.delete(made.id)
    assert await m.DerivedFactoid.get(made.id) is None
    with pytest.raises(
        PanglossDerivedDocumentError, match="it is not undeleted by hand"
    ):
        await m.DerivedFactoid.undelete(made.id)
    assert await m.DerivedFactoid.get(made.id) is None
    with writing_derived("siblings"):
        await m.DerivedFactoid.undelete(made.id)
    assert (await m.DerivedFactoid.get(made.id)).label == "Changed"


@no_type_check
async def test_derived_documents_are_searched_by_their_rule(clear_database):
    m = models()
    n = await people(m, "AB")
    statement = {"type": "Sibling", "label": "s", "people": [ref(n.A), ref(n.B)]}
    for name, label in (("siblings", "One"), ("siblings", "Two"), ("other", "Three")):
        with writing_derived(name):
            await m.DerivedFactoid.Create(
                label=label, sources=[], statements=[statement]
            ).save()
    by_rule = await m.DerivedFactoid.search(
        m.DerivedFactoid.Where(derived_by=Text(eq="siblings"))
    )
    assert sorted(r.label for r in by_rule.results) == ["One", "Two"]
    assert {r.derived_by for r in by_rule.results} == {"siblings"}
    # ("derived / not derived" is whether a rule is recorded)
    derived = await m.DerivedFactoid.search(
        m.DerivedFactoid.Where(derived_by=Text(exists=True))
    )
    assert len(derived.results) == 3


@no_type_check
async def test_the_api_gives_the_class_no_post_and_says_it_is_not_created(
    clear_database,
):
    m = models()
    n = await people(m, "AB")
    with writing_derived("siblings"):
        made = await m.DerivedFactoid.Create(
            label="Derived",
            sources=[],
            statements=[{"type": "Sibling", "label": "s", "people": [ref(n.A)]}],
        ).save()
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.post("/api/DerivedFactoid", json={})).status_code == 405
        # (a class people write has the route: it is who asks, or what, that is refused)
        assert (await client.post("/api/Factoid", json={})).status_code != 405
        read_back = await client.get(f"/api/DerivedFactoid/{made.id}")
        assert read_back.status_code == 200 and read_back.json()["label"] == "Derived"
        listed = (await client.get("/api/DerivedFactoid")).json()["results"]
        assert listed[0]["derivedBy"] == "siblings"
        schema = (await client.get("/api/derived")).json()
        assert schema["rules"]["siblings"]["class"] == "DerivedFactoid"
        assert schema["rules"]["siblings"]["document"] is True
        assert schema["rules"]["siblings"]["datalog"].startswith("DerivedFactoid{")
        assert "document" not in schema["rules"]["kin"]
        # (a class of edges it is not)
        assert "DerivedFactoid" not in schema["classes"]


# ---------------------------------------------------------------------------
# What a rule that derives documents finds, and writes
# ---------------------------------------------------------------------------


@no_type_check
async def test_each_pair_is_found_once_with_the_documents_it_rests_on(clear_database):
    m = models()
    n = await people(m, "ABCPQ")
    one = await m.Factoid.Create(
        label="One", statements=[child_of(n.A, n.P), child_of(n.B, n.P)]
    ).save()
    two = await m.Factoid.Create(label="Two", statements=[child_of(n.C, n.P)]).save()
    await m.Factoid.Create(label="Three", statements=[child_of(n.Q, n.A)]).save()
    result = await found("siblings")
    # (three children of P: three pairs, each once and never one with itself; Q is the only child of A)
    assert [tuple(sorted(p)) for p in pairs(n, result)] == [
        ("A", "B"),
        ("A", "C"),
        ("B", "C"),
    ]
    assert result.facts == {}
    by_pair = {
        tuple(sorted(pair)): j
        for pair, j in zip(
            [
                tuple(
                    {str(p.id): label for label, p in n.items()}[str(v)]
                    for v in j.values.values()
                )
                for j in result.documents.values()
            ],
            result.documents.values(),
            strict=True,
        )
    }
    assert by_pair[("A", "B")].sources == [str(one.id)]
    assert by_pair[("A", "C")].sources == sorted([str(one.id), str(two.id)])
    assert all(j.context_labels == [] for j in result.documents.values())

    # (written as the worker will write them)
    for justification in result.documents.values():
        source_ids = justification.sources
        made = await write(m, "siblings", justification)
        read_back = await m.DerivedFactoid.get(made.id)
        assert sorted(str(c.target_id) for c in read_back.sources) == source_ids
        (statement,) = read_back.statements
        assert statement.type == "Sibling" and statement.kind == "derived"
        assert sorted(str(p.id) for p in statement.people) == sorted(
            str(v) for v in justification.values.values()
        )
    assert len((await m.DerivedFactoid.list()).results) == 3
    # (and a source is changed and deleted freely: what rests on it does not hold it)
    await m.Factoid.Update(id=two.id, label="Two, changed", statements=[]).save()
    await m.Factoid.delete(one.id)
    assert pairs(n, await found("siblings")) == []


@no_type_check
async def test_the_same_pair_in_another_source_is_another_document(clear_database):
    m = models()
    n = await people(m, "ABPQ")
    await m.Factoid.Create(
        label="One", statements=[child_of(n.A, n.P), child_of(n.B, n.P)]
    ).save()
    await m.Factoid.Create(
        label="Two", statements=[child_of(n.A, n.Q), child_of(n.B, n.Q)]
    ).save()
    result = await found("siblings")
    assert [tuple(sorted(p)) for p in pairs(n, result)] == [("A", "B"), ("A", "B")]
    assert len({j.key for j in result.documents.values()}) == 2


@no_type_check
async def test_nothing_is_derived_through_a_denial_unless_the_rule_allows_it(
    clear_database,
):
    m = models()
    n = await people(m, "ABP")
    await m.Factoid.Create(
        label="One",
        statements=[
            child_of(n.A, n.P),
            {"type": "Negative", "contents": [child_of(n.B, n.P)]},
        ],
    ).save()
    assert pairs(n, await found("siblings")) == []
    allowed = await found("siblings_even_if_denied")
    assert [tuple(sorted(p)) for p in pairs(n, allowed)] == [("A", "B")]
    (justification,) = allowed.documents.values()
    assert justification.context_labels == ["Negative"]
    made = await write(m, "siblings_even_if_denied", justification)
    (listed,) = (await m.DerivedFactoid.list()).results
    assert listed.id == made.id and listed.derived_context == ["Negative"]
    assert listed.derived_by == "siblings_even_if_denied"


@no_type_check
async def test_a_rule_reads_derived_documents_unless_it_blocks_them(clear_database):
    m = models()
    n = await people(m, "ABCDEFP")
    await m.Factoid.Create(
        label="One", statements=[child_of(n.A, n.P), child_of(n.B, n.P)]
    ).save()
    await m.Factoid.Create(
        label="Said",
        statements=[{"type": "Sibling", "label": "s", "people": [ref(n.C), ref(n.D)]}],
    ).save()
    await m.Hearsay.Create(
        label="Heard",
        statements=[{"type": "Sibling", "label": "s", "people": [ref(n.E), ref(n.F)]}],
    ).save()
    assert DerivedRegistry.readers["siblings"] == ["kin"]
    assert DerivedRegistry.order.index("siblings") < DerivedRegistry.order.index("kin")
    await run_pending_derivations()
    # (the derived factoid's statement is a statement like any other to a rule that does not block its class; and
    # one that blocks two classes reads inside neither)
    assert await edges(m, "Kin") == [("A", "B"), ("C", "D"), ("E", "F")]
    assert await edges(m, "SaidKin") == [("C", "D")]
    derived = [
        d for d in (await m.DerivedFactoid.list()).results if d.derived_by == "siblings"
    ]
    # (and what it derives from one rests on it: on each derived factoid that says so)
    fact = next(
        v
        for v in (await read.list_facts(m.Kin, page_size=10))["results"]
        if {v.first.label, v.second.label} == {"A", "B"}
    )
    why = await read.get_fact(m.Kin, fact.id)
    evidence = {str(e.id) for j in why.justifications for e in j.evidence}
    assert str(derived[0].id) in evidence
    assert {e.type for j in why.justifications for e in j.evidence} == {
        "DerivedFactoid"
    }


@no_type_check
async def test_a_written_document_that_holds_too_many_gives_none(clear_database):
    m = models(max_per_seed=2)
    n = await people(m, "ABCDP")
    await m.Factoid.Create(
        label="Many", statements=[child_of(n[c], n.P) for c in "ABCD"]
    ).save()
    result = await found("siblings")
    # (each child's statement is in three pairs: more than the two the class allows from one node)
    assert DerivedRegistry.documents["siblings"].max_per_seed == 2
    assert result.overflowed and len(result.documents) < 6
