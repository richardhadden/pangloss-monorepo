"""A document that cites a document (`Cites[T]`; implementation_docs/entity-identity.md, part 3).

A citation is written with the citing document and names another document, or a part of one, by its id. What it
names is checked when it is written; what is cited may be changed only by a write that acknowledges the citations
(each is then marked changed), and may not be removed, nor its document deleted, while a published document cites
it. Citations from deleted documents do not count; those from unpublished documents never refuse anything."""

import asyncio
import uuid
from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_core import storage_of
from pangloss_models import (
    Cites,
    Document,
    Entity,
    PanglossCitedError,
    PanglossReferenceError,
    SemanticSpace,
    initialise,
)
from pangloss_models.citations import acknowledging

from .helpers import run

pytestmark = pytest.mark.asyncio(loop_scope="session")


def models():
    class Person(Entity):
        pass

    class Statement(Document):
        _meta = Document.Meta(abstract=True)

    class Birth(Statement):
        person: Person
        year: int | None = None
        witnesses: list[Person]

    class Naming(Statement):
        name: str = ""

    class Negative[T](SemanticSpace[T]):
        pass

    class Note(Document):
        text: str = ""

    class Factoid(Document):
        _meta = Document.Meta(cited_with=["source"])
        source: str = ""
        notes: str = ""
        statements: list[Statement | Negative[Statement]]  # ty: ignore[invalid-type-form]

    class SameAs(Document):
        people: list[Person]
        evidence: list[Cites[Statement]]  # ty: ignore[invalid-type-form]
        see: Cites[Note | Factoid] | None = None  # ty: ignore[invalid-type-form]

    initialise()
    return SimpleNamespace(
        Person=Person,
        Birth=Birth,
        Naming=Naming,
        Note=Note,
        Factoid=Factoid,
        SameAs=SameAs,
    )


def ref(entity) -> dict:
    return {"type": "Person", "id": entity.id}


def cite(node) -> dict:
    return {"type": node.type, "id": node.id}


@no_type_check
async def world(m):
    """A factoid with two statements, one of them in a space, and a person"""
    ann = await m.Person.Create(label="Ann").save()
    bob = await m.Person.Create(label="Bob").save()
    factoid = await m.Factoid.Create(
        label="Parish register",
        source="register, f. 3",
        statements=[
            {
                "type": "Birth",
                "label": "Ann is born",
                "person": ref(ann),
                "year": 1800,
                "witnesses": [ref(bob)],
            },
            {
                "type": "Negative",
                "contents": [
                    {"type": "Naming", "label": "Not called Anna", "name": "Anna"}
                ],
            },
        ],
    ).save(detail=True)
    birth = factoid.statements[0]
    naming = factoid.statements[1].contents[0]
    return SimpleNamespace(
        ann=ann, bob=bob, factoid=factoid, birth=birth, naming=naming
    )


@no_type_check
async def same_as(m, w, *cited, label="Ann is Bob", **more):
    return await m.SameAs.Create(
        label=label,
        people=[ref(w.ann), ref(w.bob)],
        evidence=[cite(c) for c in cited],
        **more,
    ).save(detail=True)


def as_update(m, factoid, **changes) -> dict:
    """The factoid as it was read, to be written again with `changes`"""
    data = factoid.model_dump(mode="json", exclude={"meta"})
    data.update(changes)
    return data


@no_type_check
async def update(m, factoid, acknowledge=None, **changes):
    return await m.Factoid.Update(**as_update(m, factoid, **changes)).save(
        detail=True, acknowledge_citations=acknowledge
    )


def citation_nodes(db_driver) -> list[dict]:
    rows = run(
        db_driver,
        "MATCH (c:PGCitation) RETURN properties(c) AS c ORDER BY c.target_id, c.id",
    )
    return [row["c"] for row in rows]


# --- writing and reading ----------------------------------------------------------------------------------------------


@no_type_check
async def test_a_citation_is_written_with_what_it_records_and_read_with_what_it_names(
    db_driver, clear_database
):
    m = models()
    w = await world(m)
    made = await same_as(m, w, w.birth, w.naming, see=cite(w.factoid))

    first, second = made.evidence
    assert (first.type, first.target_id, first.target_type) == (
        "PGCitation",
        w.birth.id,
        "Birth",
    )
    assert first.target_label == "Ann is born"
    assert (first.target_head_id, first.target_head_type, first.target_head_label) == (
        w.factoid.id,
        "Factoid",
        "Parish register",
    )
    assert first.target_state == "there" and first.target_spaces == []
    assert first.cited_version == 1 and first.cited_hash.startswith("1:")
    assert not first.changed_since_cited
    # (the one in a space says so)
    assert second.target_spaces == ["Negative"]
    # (a head document is cited as a part is)
    assert (
        made.see.target_id == w.factoid.id and made.see.target_head_id == w.factoid.id
    )

    # Nothing points into the cited document
    edges = run(
        db_driver,
        "MATCH (c:PGCitation)-[e]-(n) WHERE n.id IN $ids RETURN count(e) AS n",
        ids=[str(w.birth.id), str(w.naming.id), str(w.factoid.id)],
    )
    assert edges[0]["n"] == 0

    # Read again, and written again as it was read
    read = await m.SameAs.get(made.id)
    assert [c.target_id for c in read.evidence] == [w.birth.id, w.naming.id]
    again = await m.SameAs.Update(
        **read.model_dump(mode="json", exclude={"meta"})
    ).save(detail=True)
    assert [c.id for c in again.evidence] == [c.id for c in read.evidence]
    assert again.evidence[0].cited_hash == first.cited_hash


@no_type_check
async def test_what_a_citation_names_is_checked(db_driver, clear_database):
    m = models()
    w = await world(m)
    note = await m.Note.Create(label="A note").save()

    with pytest.raises(PanglossReferenceError, match="does not exist"):
        await m.SameAs.Create(
            label="x", people=[], evidence=[{"type": "Birth", "id": uuid.uuid4()}]
        ).save()
    with pytest.raises(PanglossReferenceError, match="cannot be cited here"):
        await m.SameAs.Create(label="x", people=[], evidence=[cite(note)]).save()
    with pytest.raises(PanglossReferenceError, match="is an entity"):
        await m.SameAs.Create(
            label="x", people=[], evidence=[{"type": "Birth", "id": w.ann.id}]
        ).save()
    with pytest.raises(PanglossReferenceError, match="cannot be cited here"):
        await m.SameAs.Create(
            label="x", people=[], evidence=[], see=cite(w.birth)
        ).save()
    # (nothing of a refused write is left)
    assert run(db_driver, "MATCH (n:SameAs) RETURN n.id") == []
    assert citation_nodes(db_driver) == []

    # The class it is said to be is put right
    made = await m.SameAs.Create(
        label="x", people=[], evidence=[{"type": "Naming", "id": w.birth.id}]
    ).save(detail=True)
    assert made.evidence[0].target_type == "Birth"

    # What is in a deleted document cannot be cited
    await m.Factoid.delete(w.factoid.id, acknowledge_citations="removals")
    with pytest.raises(PanglossReferenceError, match="does not exist"):
        await same_as(m, w, w.birth)


@no_type_check
async def test_a_document_may_cite_its_own_parts(db_driver, clear_database):
    class Claim(Document):
        _meta = Document.Meta(create_with_id=True)
        text: str = ""
        because: list[Cites[Claim]]  # ty: ignore[invalid-type-form]

    class Argument(Document):
        claims: list[Claim]

    initialise()
    first, second = uuid.uuid7(), uuid.uuid7()
    made = await Argument.Create(
        label="An argument",
        claims=[
            {
                "type": "Claim",
                "id": second,
                "create_new": True,
                "label": "so",
                "because": [{"type": "Claim", "id": first}],
            },
            {
                "type": "Claim",
                "id": first,
                "create_new": True,
                "label": "since",
                "because": [],
            },
        ],
    ).save(detail=True)
    assert made.claims[0].because[0].target_label == "since"

    # It is written again with what it cites: changing the cited claim needs no acknowledgement
    data = made.model_dump(mode="json", exclude={"meta"})
    data["claims"][1]["text"] = "changed"
    again = await Argument.Update(**data).save(detail=True)
    assert not again.claims[0].because[0].changed_since_cited

    # Removing it while it is cited is a citation of nothing
    data = again.model_dump(mode="json", exclude={"meta"})
    del data["claims"][1]
    with pytest.raises(PanglossReferenceError, match="does not exist"):
        await Argument.Update(**data).save()


# --- protecting what is cited -----------------------------------------------------------------------------------------


@no_type_check
async def test_a_change_to_what_is_cited_is_refused_until_acknowledged(
    db_driver, clear_database
):
    m = models()
    w = await world(m)
    citing = await same_as(m, w, w.birth)

    statements = as_update(m, w.factoid)["statements"]
    statements[0]["year"] = 1801

    with pytest.raises(PanglossCitedError) as refused:
        await update(m, w.factoid, statements=statements)
    assert refused.value.removed == []
    assert refused.value.changed == [
        {
            "target": str(w.birth.id),
            "target_label": "Ann is born",
            "id": str(citing.id),
            "type": "SameAs",
            "label": "Ann is Bob",
        }
    ]
    assert "acknowledge_citations" in refused.value.fix
    # (nothing was written)
    assert (await m.Factoid.get(w.factoid.id)).statements[0].year == 1800
    assert (await m.Factoid.get(w.factoid.id)).meta.version == 1

    after = await update(m, w.factoid, acknowledge=True, statements=statements)
    assert after.statements[0].year == 1801
    read = await m.SameAs.get(citing.id)
    assert read.evidence[0].changed_since_cited
    # (what was recorded when it was cited is as it was)
    assert read.evidence[0].cited_version == 1
    assert read.evidence[0].cited_hash == citing.evidence[0].cited_hash

    # The mark stays through a save of the citing document that sends it back, and goes when it is sent false:
    # the citation is then of what is there now
    data = read.model_dump(mode="json", exclude={"meta"})
    kept = await m.SameAs.Update(**data).save(detail=True)
    assert kept.evidence[0].changed_since_cited
    data = kept.model_dump(mode="json", exclude={"meta"})
    data["evidence"][0]["changed_since_cited"] = False
    seen = await m.SameAs.Update(**data).save(detail=True)
    assert not seen.evidence[0].changed_since_cited
    assert seen.evidence[0].cited_version == 2
    assert seen.evidence[0].cited_hash != citing.evidence[0].cited_hash


@no_type_check
async def test_what_counts_as_a_change(db_driver, clear_database):
    m = models()
    w = await world(m)
    await same_as(m, w, w.birth)

    # Not a change of what is cited: the document's other fields, its other statements, the order of things sent,
    # a statement added
    statements = as_update(m, w.factoid)["statements"]
    statements[1]["contents"][0]["name"] = "Hannah"
    statements.append({"type": "Naming", "label": "Called Nan", "name": "Nan"})
    after = await update(
        m, w.factoid, notes="checked", label="Register", statements=statements
    )
    assert after.meta.version == 2

    # A change: a value of the statement, an entity it names, a list of them, a field of the document that is cited
    # with its statements (`cited_with`)
    carl = await m.Person.Create(label="Carl").save()
    for change in (
        lambda s: s[0].update(year=1799),
        lambda s: s[0].update(person=ref(carl)),
        lambda s: s[0].update(witnesses=[]),
        lambda s: s[0].update(label="Ann was born"),
    ):
        statements = as_update(m, after)["statements"]
        change(statements)
        with pytest.raises(PanglossCitedError):
            await update(m, after, statements=statements)
    with pytest.raises(PanglossCitedError):
        await update(m, after, source="register, f. 4")

    # The ids of what is inside a cited statement are not part of it: sent without them, they are made anew
    statements = as_update(m, after)["statements"]
    assert (await update(m, after, statements=statements)).meta.version == 3


@no_type_check
async def test_what_is_cited_cannot_be_removed_nor_its_document_deleted(
    db_driver, clear_database
):
    m = models()
    w = await world(m)
    citing = await same_as(m, w, w.birth)
    statements = as_update(m, w.factoid)["statements"][1:]

    for acknowledge in (None, True):
        with pytest.raises(PanglossCitedError) as refused:
            await update(m, w.factoid, acknowledge=acknowledge, statements=statements)
        assert [r["id"] for r in refused.value.removed] == [str(citing.id)]
        assert "Change the citations first" in refused.value.fix

    check = await storage_of().operations.check_deletable(m.Factoid, w.factoid.id)
    assert not check.deletable and "cites this" in check.reason
    assert [r["id"] for r in check.referenced_by] == [str(citing.id)]
    with pytest.raises(PanglossCitedError):
        await m.Factoid.delete(w.factoid.id)
    assert (await m.Factoid.get(w.factoid.id)) is not None

    # The same id given to another statement is a change, not a removal
    replaced = [{"type": "Naming", "id": str(w.birth.id), "label": "Something else"}]
    with pytest.raises(PanglossCitedError) as refused:
        await update(m, w.factoid, statements=replaced)
    assert refused.value.removed == [] and len(refused.value.changed) == 1

    # Once the citation is taken out, both go through
    data = citing.model_dump(mode="json", exclude={"meta"})
    data["evidence"] = []
    await m.SameAs.Update(**data).save()
    await update(m, w.factoid, statements=statements)
    assert (
        await storage_of().operations.check_deletable(m.Factoid, w.factoid.id)
    ).deletable
    await m.Factoid.delete(w.factoid.id)


@no_type_check
async def test_an_admin_may_override_a_removal_and_the_citation_says_removed(
    db_driver, clear_database
):
    m = models()
    w = await world(m)
    citing = await same_as(m, w, w.birth, w.naming)

    after = await update(
        m,
        w.factoid,
        acknowledge="removals",
        statements=as_update(m, w.factoid)["statements"][1:],
    )
    assert len(after.statements) == 1
    read = await m.SameAs.get(citing.id)
    assert [c.target_state for c in read.evidence] == ["removed", "there"]
    assert read.evidence[0].target_label is None
    # (what it was is still recorded: the version of the document that had it)
    assert read.evidence[0].cited_version == 1

    lost = await storage_of().operations.citations_pointing_at_nothing()
    assert [(row["target"], row["id"], row["label"]) for row in lost] == [
        (str(w.birth.id), str(citing.id), "Ann is Bob")
    ]

    # The citing document can be saved as it is; a new citation of what is gone cannot be made
    await m.SameAs.Update(**read.model_dump(mode="json", exclude={"meta"})).save()
    with pytest.raises(PanglossReferenceError):
        await same_as(m, w, w.birth, label="Another")

    # A deleted document: the same
    await m.Factoid.delete(w.factoid.id, acknowledge_citations="removals")
    read = await m.SameAs.get(citing.id)
    assert [c.target_state for c in read.evidence] == ["removed", "removed"]
    # ... and there again when it is undeleted
    await m.Factoid.undelete(w.factoid.id)
    read = await m.SameAs.get(citing.id)
    assert [c.target_state for c in read.evidence] == ["removed", "there"]


@no_type_check
async def test_citations_from_deleted_documents_do_not_count(db_driver, clear_database):
    m = models()
    w = await world(m)
    citing = await same_as(m, w, w.birth)
    await m.SameAs.delete(citing.id)

    after = await update(
        m, w.factoid, statements=as_update(m, w.factoid)["statements"][1:]
    )
    assert len(after.statements) == 1
    assert (
        await storage_of().operations.check_deletable(m.Factoid, w.factoid.id)
    ).deletable

    # Undeleted, its citation is of what is gone (decision 31)
    await m.SameAs.undelete(citing.id)
    read = await m.SameAs.get(citing.id)
    assert read.evidence[0].target_state == "removed"


@no_type_check
async def test_citations_from_unpublished_documents_do_not_refuse_but_are_marked(
    db_driver, clear_database
):
    m = models()
    w = await world(m)
    citing = await same_as(m, w, w.birth)
    run(db_driver, "MATCH (n:SameAs) SET n.published = false")

    statements = as_update(m, w.factoid)["statements"]
    statements[0]["year"] = 1801
    await update(m, w.factoid, statements=statements)
    assert (await m.SameAs.get(citing.id)).evidence[0].changed_since_cited

    by = await storage_of().operations.cited_by(w.factoid.id)
    assert [(row["target"], row["published"], row["changed"]) for row in by] == [
        (str(w.birth.id), False, True)
    ]
    assert (
        await storage_of().operations.check_deletable(m.Factoid, w.factoid.id)
    ).deletable


@no_type_check
async def test_who_cites_a_document_and_its_parts(db_driver, clear_database):
    m = models()
    w = await world(m)
    first = await same_as(m, w, w.birth, label="First")
    second = await same_as(m, w, w.birth, w.naming, label="Second", see=cite(w.factoid))

    by = await storage_of().operations.cited_by(w.factoid.id)
    assert [(row["label"], row["target"]) for row in by] == sorted(
        [
            ("First", str(w.birth.id)),
            ("Second", str(w.birth.id)),
            ("Second", str(w.naming.id)),
            ("Second", str(w.factoid.id)),
        ]
    )
    assert {row["id"] for row in by} == {str(first.id), str(second.id)}
    assert all(not row["hidden"] and not row["changed"] for row in by)
    assert await storage_of().operations.cited_by(first.id) == []


# --- what must not make a citation look changed -----------------------------------------------------------------------


@no_type_check
async def test_a_merge_of_entities_a_cited_statement_names_changes_nothing(
    db_driver, clear_database
):
    m = models()
    w = await world(m)
    citing = await same_as(m, w, w.birth)

    # (Bob, a witness, is merged into a new person: the statement now names that one)
    carl = await m.Person.Create(label="Carl").save()
    await m.Person.merge(absorb=w.bob.id, into=carl.id)
    read = await m.Factoid.get(w.factoid.id)
    assert [p.id for p in read.statements[0].witnesses] == [carl.id]

    # The factoid is saved as it now is, and with a correction elsewhere: no citation is in the way
    await update(m, read, notes="seen")
    assert not (await m.SameAs.get(citing.id)).evidence[0].changed_since_cited


# --- at the same moment -----------------------------------------------------------------------------------------------


async def outcome(awaitable):
    try:
        return await awaitable
    except Exception as error:
        return error


@no_type_check
async def test_a_citation_written_while_its_target_is_removed(
    db_driver, clear_database
):
    """Decision 30: the two writes are of different heads. Whichever commits first, the other sees it: either the
    citation is refused (its target is gone), or the removal is (it is cited). Never a citation of nothing."""
    m = models()
    for round_ in range(6):
        w = await world(m)
        statements = as_update(m, w.factoid)["statements"][1:]
        results = await asyncio.gather(
            *[
                outcome(same_as(m, w, w.birth, label=f"Citing {round_} {i}"))
                for i in range(4)
            ],
            outcome(update(m, w.factoid, statements=statements)),
            *[
                outcome(same_as(m, w, w.birth, label=f"Citing {round_} {i}"))
                for i in range(4, 8)
            ],
        )
        removal = results[4]
        written = [r for r in results[:4] + results[5:] if not isinstance(r, Exception)]
        refused = [r for r in results[:4] + results[5:] if isinstance(r, Exception)]
        assert all(isinstance(r, PanglossReferenceError) for r in refused), refused
        if isinstance(removal, Exception):
            assert isinstance(removal, PanglossCitedError), removal
            assert written
        else:
            assert written == [], (
                "a citation was written of a statement that was removed"
            )
        assert await storage_of().operations.citations_pointing_at_nothing() == []


@no_type_check
async def test_a_citation_written_while_its_target_is_changed(
    db_driver, clear_database
):
    """A citation records what it cited. A change made at the same moment either comes first, and is what is cited;
    or comes second, and is refused."""
    m = models()
    for round_ in range(6):
        w = await world(m)
        statements = as_update(m, w.factoid)["statements"]
        statements[0]["year"] = 1900 + round_
        results = await asyncio.gather(
            *[
                outcome(same_as(m, w, w.birth, label=f"Citing {round_} {i}"))
                for i in range(3)
            ],
            outcome(update(m, w.factoid, statements=statements)),
            *[
                outcome(same_as(m, w, w.birth, label=f"Citing {round_} {i}"))
                for i in range(3, 6)
            ],
        )
        change = results[3]
        citing = results[:3] + results[4:]
        assert not any(isinstance(r, Exception) for r in citing), citing
        versions = {c.evidence[0].cited_version for c in citing}
        if isinstance(change, Exception):
            assert isinstance(change, PanglossCitedError), change
            assert versions == {1}
        else:
            # (no citation of the earlier version was left unmarked beside the change)
            for c in citing:
                read = await m.SameAs.get(c.id)
                assert (
                    read.evidence[0].cited_version == 2
                    or read.evidence[0].changed_since_cited
                )


@no_type_check
async def test_many_citations_of_one_document_at_once_are_all_written(
    db_driver, clear_database
):
    m = models()
    w = await world(m)
    results = await asyncio.gather(
        *[
            outcome(same_as(m, w, w.birth, w.naming, label=f"Citing {i}"))
            for i in range(12)
        ]
    )
    assert [r for r in results if isinstance(r, Exception)] == []
    assert len(citation_nodes(db_driver)) == 24
    assert len(await storage_of().operations.cited_by(w.factoid.id)) == 24


# --- inside the block -------------------------------------------------------------------------------------------------


@no_type_check
async def test_writes_inside_a_block_acknowledge(db_driver, clear_database):
    m = models()
    w = await world(m)
    citing = await same_as(m, w, w.birth)
    statements = as_update(m, w.factoid)["statements"]
    statements[0]["year"] = 1801
    with acknowledging("changes"):
        await update(m, w.factoid, statements=statements)
    assert (await m.SameAs.get(citing.id)).evidence[0].changed_since_cited
