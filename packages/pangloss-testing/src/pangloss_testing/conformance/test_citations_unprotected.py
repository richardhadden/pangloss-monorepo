"""A citation that does not protect what it cites (a `Cites` with `protect = False`; implementation_docs/
derived-edges-and-documents.md, part 3): written, read and listed as a citation is, but what it cites may be changed
and deleted freely, is never marked, and is not written to. Its nodes are of a class of their own, so that the work
done for what is cited does not meet them"""

from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_core import backend, storage_of
from pangloss_cypher import citations as cypher_citations
from pangloss_models import (
    Cites,
    Document,
    Entity,
    ModelRegistry,
    PanglossCitedError,
    PanglossReferenceError,
    initialise,
)
from pangloss_models.export import export_models
from pangloss_users import see_unpublished

from .helpers import run
from .test_merge_api import api  # noqa: F401

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class RestsOn[Target](Cites[Target]):
        """A citation that does not protect"""

        protect = False

    class Person(Entity):
        pass

    class Statement(Document):
        _meta = Document.Meta(abstract=True)

    class Birth(Statement):
        person: Person
        year: int | None = None

    class Naming(Statement):
        name: str = ""

    class Factoid(Document):
        statements: list[Statement]  # ty: ignore[invalid-type-form]

    class Summary(Document):
        """What follows from some statements: it follows them, and never holds them as they are"""

        text: str = ""
        sources: list[RestsOn[Statement | Factoid]]  # ty: ignore[invalid-type-form]

    class OnlyBirths(Document):
        source: RestsOn[Birth] | None = None  # ty: ignore[invalid-type-form]

    class Argument(Document):
        evidence: list[Cites[Statement]]  # ty: ignore[invalid-type-form]

    initialise()
    return SimpleNamespace(**{k: v for k, v in locals().items() if isinstance(v, type)})


def cite(node) -> dict:
    return {"type": node.type, "id": node.id}


@no_type_check
async def world(m):
    ann = await m.Person.Create(label="Ann").save()
    factoid = await m.Factoid.Create(
        label="Parish register",
        statements=[
            {
                "type": "Birth",
                "label": "Ann is born",
                "person": {"type": "Person", "id": ann.id},
                "year": 1800,
            },
            {"type": "Naming", "label": "Called Anna", "name": "Anna"},
        ],
    ).save(detail=True)
    birth, naming = factoid.statements
    return SimpleNamespace(ann=ann, factoid=factoid, birth=birth, naming=naming)


def as_update(m, view, **changes):
    data = view.model_dump(mode="json", exclude={"meta"})
    data.update(changes)
    return type(view)._owner.Update(**data)


@no_type_check
async def test_it_is_a_class_of_its_own_and_only_where_it_is_used():
    m = models()
    assert "PGUnprotectedCitation" in ModelRegistry._model_dict
    assert "PGCitation" in ModelRegistry._model_dict
    option = next(iter(m.Summary._meta.fields["sources"].type_options))
    assert option.annotated_type.__name__ == "PGUnprotectedCitation"
    assert option.protect is False
    assert {c.__name__ for c in option.cited} == {"Statement", "Factoid"}
    protecting = next(iter(m.Argument._meta.fields["evidence"].type_options))
    assert protecting.annotated_type.__name__ == "PGCitation" and protecting.protect
    # (the interface is told which is which: only the one that does not protect says so)
    exported = export_models()["models"]
    (sources,) = [f for f in exported["Summary"]["fields"] if f["name"] == "sources"]
    assert [(o["type"], o.get("protects")) for o in sources["options"]] == [
        ("PGUnprotectedCitation", False)
    ]
    (evidence,) = [f for f in exported["Argument"]["fields"] if f["name"] == "evidence"]
    assert all("protects" not in o for o in evidence["options"])
    # (a project with only citations that protect has no such class)
    ModelRegistry._reset()

    class Note(Document):
        pass

    class Essay(Document):
        see: list[Cites[Note]]  # ty: ignore[invalid-type-form]

    initialise(bind_database=False)
    assert "PGUnprotectedCitation" not in ModelRegistry._model_dict


@no_type_check
async def test_it_is_written_and_read_as_a_citation_and_writes_nothing_on_what_it_cites(
    clear_database, db_driver
):
    m = models()
    w = await world(m)
    made = await m.Summary.Create(
        label="Ann", text="born 1800", sources=[cite(w.birth), cite(w.factoid)]
    ).save(detail=True)
    first, second = made.sources
    assert first.type == "PGUnprotectedCitation"
    assert (first.target_id, first.target_type) == (w.birth.id, "Birth")
    assert first.target_label == "Ann is born" and first.cited_label == "Ann is born"
    assert first.target_head_id == w.factoid.id and first.target_head_type == "Factoid"
    assert first.target_state == "there"
    assert (second.target_id, second.target_head_id) == (w.factoid.id, w.factoid.id)
    stored = run(
        db_driver,
        "MATCH (c:PGUnprotectedCitation) RETURN c.target_id AS target, c.target_head_id AS head, "
        "c.target_type AS type, c.cited_label AS label, labels(c) AS labels ORDER BY c.target_type",
    )
    assert [(r["type"], r["head"]) for r in stored] == [
        ("Birth", str(w.factoid.id)),
        ("Factoid", str(w.factoid.id)),
    ]
    assert all("PGCitation" not in r["labels"] for r in stored)
    assert run(db_driver, "MATCH (c:PGCitation) RETURN count(c) AS n") == [{"n": 0}]
    # (the head that is cited was not written to: a citation that protects marks it, `pg_cited`)
    assert run(
        db_driver,
        "MATCH (h:HeadNode {id: $id}) RETURN h.pg_cited AS cited",
        id=str(w.factoid.id),
    ) == [{"cited": None}]
    await m.Argument.Create(label="A", evidence=[cite(w.birth)]).save()
    (touched,) = run(
        db_driver,
        "MATCH (h:HeadNode {id: $id}) RETURN h.pg_cited AS cited",
        id=str(w.factoid.id),
    )
    assert touched["cited"] is not None


@no_type_check
async def test_what_it_cites_is_changed_and_deleted_freely_and_it_is_never_marked(
    clear_database, db_driver
):
    m = models()
    w = await world(m)
    summary = await m.Summary.Create(
        label="Ann", sources=[cite(w.birth), cite(w.naming)]
    ).save(detail=True)
    # (a change of what is cited: no acknowledgement asked for, nothing marked)
    factoid = await m.Factoid.get(w.factoid.id)
    statements = [s.model_dump(mode="json") for s in factoid.statements]
    statements[0]["year"] = 1801
    await m.Factoid.Update(
        id=factoid.id, label=factoid.label, statements=statements
    ).save()
    again = await m.Summary.get(summary.id)
    assert [c.target_state for c in again.sources] == ["there", "there"]
    assert not hasattr(again.sources[0], "changed_since_cited")
    # (a part removed, with the ids of the rest kept: the citation of it names nothing now)
    await m.Factoid.Update(
        id=factoid.id, label=factoid.label, statements=statements[:1]
    ).save()
    again = await m.Summary.get(summary.id)
    assert [c.target_state for c in again.sources] == ["there", "removed"]
    # (and the whole document deleted)
    await m.Factoid.delete(factoid.id)
    again = await m.Summary.get(summary.id)
    assert [c.target_state for c in again.sources] == ["removed", "removed"]
    assert again.sources[0].cited_label == "Ann is born"
    await m.Factoid.undelete(factoid.id)
    assert (await m.Summary.get(summary.id)).sources[0].target_state == "there"


@no_type_check
async def test_beside_a_citation_that_protects_only_that_one_refuses(clear_database):
    m = models()
    w = await world(m)
    await m.Summary.Create(label="Ann", sources=[cite(w.birth)]).save()
    argument = await m.Argument.Create(label="A", evidence=[cite(w.birth)]).save(
        detail=True
    )
    factoid = await m.Factoid.get(w.factoid.id)
    statements = [s.model_dump(mode="json") for s in factoid.statements]
    statements[0]["year"] = 1801
    with pytest.raises(PanglossCitedError) as error:
        await m.Factoid.Update(
            id=factoid.id, label=factoid.label, statements=statements
        ).save()
    # (only the argument is named: the summary does not count)
    assert [row["type"] for row in error.value.changed] == ["Argument"]
    with pytest.raises(PanglossCitedError):
        await m.Factoid.delete(factoid.id)
    await m.Argument.delete(argument.id)
    await m.Factoid.delete(factoid.id)


@no_type_check
async def test_what_it_names_is_checked_when_it_is_written(clear_database):
    import uuid

    m = models()
    w = await world(m)
    with pytest.raises(PanglossReferenceError, match="does not exist"):
        await m.Summary.Create(
            label="S", sources=[{"type": "Birth", "id": uuid.uuid4()}]
        ).save()
    with pytest.raises(PanglossReferenceError, match="is an entity"):
        await m.Summary.Create(
            label="S", sources=[{"type": "Person", "id": w.ann.id}]
        ).save()
    with pytest.raises(
        PanglossReferenceError, match="is a Naming, which cannot be cited here"
    ):
        await m.OnlyBirths.Create(label="O", source=cite(w.naming)).save()
    made = await m.OnlyBirths.Create(label="O", source=cite(w.birth)).save(detail=True)
    assert made.source.target_id == w.birth.id
    # (nothing of a refused one was written)
    assert (await m.Summary.list()).results == []
    # (one whose source has gone cannot be saved again as it is: what wrote it writes it again without)
    await m.Factoid.delete(w.factoid.id)
    with pytest.raises(PanglossReferenceError, match="does not exist"):
        await as_update(m, made).save()
    await m.OnlyBirths.Update(id=made.id, label="O", source=None).save()


@no_type_check
async def test_who_cites_without_protecting_is_listed_apart(clear_database, db_driver):
    m = models()
    w = await world(m)
    first = await m.Summary.Create(label="First", sources=[cite(w.birth)]).save()
    second = await m.Summary.Create(
        label="Second", sources=[cite(w.factoid), cite(w.naming)]
    ).save()
    await m.Argument.Create(label="A", evidence=[cite(w.birth)]).save()
    # (who cites it, as before: the argument alone)
    assert [r["type"] for r in await m.Factoid.cited_by(w.factoid.id)] == ["Argument"]
    operations = storage_of().operations
    rows = await operations.cited_by(w.factoid.id, True)
    assert [(r["label"], r["target"], r["changed"], r["hidden"]) for r in rows] == [
        ("First", str(w.birth.id), False, False),
        ("Second", str(w.factoid.id), False, False),
        ("Second", str(w.naming.id), False, False),
    ]
    # (of a part)
    of_part = await operations.cited_by(w.naming.id, True)
    assert [r["label"] for r in of_part] == ["Second"]
    # (one in a deleted document does not count; one in a document the reader may not see is hidden)
    await m.Summary.delete(first.id)
    run(
        db_driver,
        "MATCH (h:HeadNode {id: $id}) SET h.published = false",
        id=str(second.id),
    )
    token = see_unpublished.set(False)
    try:
        hidden = await operations.cited_by(w.factoid.id, True)
    finally:
        see_unpublished.reset(token)
    assert [(r["label"], r["hidden"]) for r in hidden] == [(None, True), (None, True)]


@no_type_check
async def test_a_much_cited_head_is_not_found_by_what_protects(clear_database):
    """What is done before every save of a head that is cited (`before_change`) finds nothing for a head that only
    citations that do not protect name, however many: its save is that of a head nothing cites"""
    m = models()
    w = await world(m)
    for n in range(40):
        await m.Summary.Create(
            label=f"S{n}", sources=[cite(w.birth), cite(w.factoid)]
        ).save()
    db = backend.current().database()

    @db.read_transaction
    async def guard(tx):
        return (
            await cypher_citations.before_change(tx, w.factoid.id, "Factoid"),
            await cypher_citations.citing(tx, w.factoid.id),
        )

    assert await guard() == (None, [])
    assert len(await storage_of().operations.cited_by(w.factoid.id, True)) == 80
    await as_update(m, await m.Factoid.get(w.factoid.id), label="Changed").save()
    await m.Factoid.delete(w.factoid.id)


@no_type_check
async def test_the_api_lists_them_with_a_parameter(clear_database, db_driver, api):  # noqa: F811
    m = models()
    client, users = await api()
    w = await world(m)
    made = await client.post(
        "/api/Summary?detail=true",
        json={
            "type": "Summary",
            "label": "Ann",
            "sources": [{"type": "Birth", "id": str(w.birth.id)}],
        },
        headers=users["ann"],
    )
    assert made.status_code in (200, 201), made.text
    (citation,) = made.json()["sources"]
    assert citation["type"] == "PGUnprotectedCitation"
    assert citation["targetLabel"] == "Ann is born"
    assert citation["targetHeadType"] == "Factoid"
    cited = await client.get(f"/api/Factoid/{w.factoid.id}/cited")
    assert cited.json() == []
    apart = await client.get(
        f"/api/Factoid/{w.factoid.id}/cited", params={"unprotected": "true"}
    )
    assert apart.status_code == 200, apart.text
    (row,) = apart.json()
    assert (row["type"], row["label"], row["target"], row["changed"]) == (
        "Summary",
        "Ann",
        str(w.birth.id),
        False,
    )
