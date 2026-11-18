"""A cited basis (`PGCitedBasis`; implementation_docs/derived-edges-and-documents.md, "Citing a derived document"): a
citation of something that cannot itself be cited is written as citations of what it rests on, with a record of what
was chosen. The core knows only the hooks: here an app of the test says that a `Digest` is cited through the
statements it was made of, as `pangloss-derived` says of a derived document"""

import uuid
from types import SimpleNamespace
from typing import no_type_check

import pytest
from pangloss_core import backend
from pangloss_cypher import citations as cypher_citations
from pangloss_models import (
    Cites,
    Document,
    Entity,
    ModelRegistry,
    PanglossCitedError,
    PanglossReferenceError,
    citations,
    hooks,
    initialise,
)

from .helpers import run
from .test_merge_api import api  # noqa: F401

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def resolving():
    """An app that resolves citations, for the length of a test: what each digest rests on is in `rests_on` (by its
    id: the (class, id) of each statement), and `asked` records each time it is asked, and whether in a transaction"""
    rests_on: dict[str, list[tuple[str, str]]] = {}
    asked: list[tuple[str, bool]] = []
    marked: list[hooks.CitationMark] = []

    async def resolver(type_name, id, tx):
        asked.append((type_name, tx is not None))
        found = rests_on.get(str(id))
        if type_name != "Digest" or found is None:
            return None
        return hooks.ResolvedCitation(
            targets=tuple(found), rule="digest", key=f"key-{id}", label="A digest"
        )

    before = citations._basis_enabled
    hooks.resolve_citation.append(resolver)
    hooks.citation_marked.append(marked.append)
    citations.enable_cited_basis()
    yield SimpleNamespace(
        rests_on=rests_on, asked=asked, marked=marked, resolver=resolver
    )
    hooks.resolve_citation.remove(resolver)
    hooks.citation_marked.remove(marked.append)
    citations._basis_enabled = before
    cypher_citations._marks.clear()
    # (a class declared for this test is not left for the next one's models)
    ModelRegistry._reset()


def models():
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

    class Digest(Document):
        """What stands for something that cannot be cited itself (a derived document)"""

        text: str = ""

    class Argument(Document):
        evidence: list[Cites[Statement]]  # ty: ignore[invalid-type-form]
        main: Cites[Birth] | None = None  # ty: ignore[invalid-type-form]

    initialise()
    return SimpleNamespace(**{k: v for k, v in locals().items() if isinstance(v, type)})


def cite(node) -> dict:
    return {"type": node.type, "id": node.id}


@no_type_check
async def world(m, resolving):
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
    digest = await m.Digest.Create(label="Ann, in short", text="b. 1800").save()
    resolving.rests_on[str(digest.id)] = [
        ("Birth", str(birth.id)),
        ("Naming", str(naming.id)),
    ]
    return SimpleNamespace(
        ann=ann, factoid=factoid, birth=birth, naming=naming, digest=digest
    )


def as_update(view, **changes):
    data = view.model_dump(mode="json", exclude={"meta"})
    data.update(changes)
    return type(view)._owner.Update(**data)


@no_type_check
async def test_there_is_such_a_class_only_when_an_app_asks_for_it():
    before = citations._basis_enabled
    citations._basis_enabled = False
    try:
        m = models()
        assert "PGCitedBasis" not in ModelRegistry._model_dict
        assert [
            o.annotated_type.__name__
            for o in m.Argument._meta.fields["evidence"].type_options
        ] == ["PGCitation"]
        ModelRegistry._reset()
        citations.enable_cited_basis()
        m = models()
        assert "PGCitedBasis" in ModelRegistry._model_dict
        assert sorted(
            o.annotated_type.__name__
            for o in m.Argument._meta.fields["evidence"].type_options
        ) == ["PGCitation", "PGCitedBasis"]
        # (asked for after the models were declared: still before they are initialised)
        ModelRegistry._reset()
        citations._basis_enabled = False

        class Note(Document):
            pass

        class Essay(Document):
            see: list[Cites[Note]]  # ty: ignore[invalid-type-form]

        citations.enable_cited_basis()
        initialise(bind_database=False)
        assert sorted(
            o.annotated_type.__name__ for o in Essay._meta.fields["see"].type_options
        ) == ["PGCitation", "PGCitedBasis"]
    finally:
        citations._basis_enabled = before
        ModelRegistry._reset()


@no_type_check
async def test_a_citation_of_what_cannot_be_cited_is_written_as_its_basis(
    clear_database, db_driver, resolving
):
    m = models()
    w = await world(m, resolving)
    made = await m.Argument.Create(
        label="A", evidence=[cite(w.digest), cite(w.birth)], main=cite(w.digest)
    ).save(detail=True)
    basis, plain = made.evidence
    assert basis.type == "PGCitedBasis" and plain.type == "PGCitation"
    assert (basis.via_id, basis.via_type) == (w.digest.id, "Digest")
    assert (basis.via_rule, basis.via_key, basis.via_label) == (
        "digest",
        f"key-{w.digest.id}",
        "A digest",
    )
    assert basis.derivation_state == "" and basis.via_state == "there"
    assert basis.via_label_now == "Ann, in short"
    # (citations as any other, of what it rests on: whatever the field's own class, here a Naming among them)
    assert [(c.type, c.target_type, c.target_label) for c in basis.basis] == [
        ("PGCitation", "Birth", "Ann is born"),
        ("PGCitation", "Naming", "Called Anna"),
    ]
    assert all(c.target_head_id == w.factoid.id for c in basis.basis)
    assert all(c.cited_hash and c.cited_version == 1 for c in basis.basis)
    # (a field of one holds one node: the basis, though it stands for two citations)
    assert made.main.type == "PGCitedBasis" and len(made.main.basis) == 2
    # (what was chosen is not itself cited: nothing names it but the record)
    assert run(
        db_driver,
        "MATCH (c:PGCitation {target_id: $id}) RETURN count(c) AS n",
        id=str(w.digest.id),
    ) == [{"n": 0}]
    assert run(
        db_driver,
        "MATCH (b:PGCitedBasis {via_id: $id}) RETURN count(b) AS n",
        id=str(w.digest.id),
    ) == [{"n": 2}]
    # (asked when the payload was read, and nothing more: what it made is what was written)
    assert ("Digest", False) in resolving.asked


@no_type_check
async def test_what_was_chosen_is_free_and_what_it_rests_on_is_protected(
    clear_database, resolving
):
    m = models()
    w = await world(m, resolving)
    argument = await m.Argument.Create(label="A", evidence=[cite(w.digest)]).save(
        detail=True
    )
    # (the digest: changed and deleted with nothing asked, as its worker must be able to)
    await m.Digest.Update(id=w.digest.id, label="Ann, shorter", text="b.").save()
    assert (await m.Argument.get(argument.id)).evidence[0].via_label_now == (
        "Ann, shorter"
    )
    assert await m.Digest.cited_by(w.digest.id) == []
    await m.Digest.delete(w.digest.id)
    read = await m.Argument.get(argument.id)
    assert read.evidence[0].via_state == "removed"
    assert read.evidence[0].via_label == "A digest"
    # (the statements: cited, so a change of one needs the acknowledgement, and the factoid cannot be deleted)
    assert [r["type"] for r in await m.Factoid.cited_by(w.factoid.id)] == [
        "Argument",
        "Argument",
    ]
    factoid = await m.Factoid.get(w.factoid.id)
    statements = [s.model_dump(mode="json") for s in factoid.statements]
    statements[1]["name"] = "Anne"
    with pytest.raises(PanglossCitedError):
        await m.Factoid.Update(
            id=factoid.id, label=factoid.label, statements=statements
        ).save()
    with pytest.raises(PanglossCitedError):
        await m.Factoid.delete(factoid.id)
    await m.Factoid.Update(
        id=factoid.id, label=factoid.label, statements=statements
    ).save(acknowledge_citations=True)
    marked = (await m.Argument.get(argument.id)).evidence[0].basis
    assert [c.changed_since_cited for c in marked] == [False, True]


@no_type_check
async def test_what_was_read_can_be_sent_back(clear_database, resolving):
    m = models()
    w = await world(m, resolving)
    made = await m.Argument.Create(
        label="A", evidence=[cite(w.digest)], main=cite(w.digest)
    ).save(detail=True)
    resolving.asked.clear()
    # (even when what was chosen has gone, or is no longer what it was: the document has this basis already)
    resolving.rests_on[str(w.digest.id)] = [("Birth", str(w.birth.id))]
    await m.Digest.delete(w.digest.id)
    saved = await as_update(made, label="A again").save(detail=True)
    assert saved.label == "A again"
    assert [c.target_type for c in saved.evidence[0].basis] == ["Birth", "Naming"]
    assert saved.evidence[0].via_key == f"key-{w.digest.id}"
    assert resolving.asked == []
    # (what is recorded of what was chosen is the document's own, whatever is sent)
    data = saved.model_dump(mode="json", exclude={"meta"})
    data["evidence"][0]["via_rule"] = "another"
    data["evidence"][0]["via_label"] = "Something else"
    again = await m.Argument.Update(**data).save(detail=True)
    assert (again.evidence[0].via_rule, again.evidence[0].via_label) == (
        "digest",
        "A digest",
    )
    # (one of the two removed: the other stays)
    data = again.model_dump(mode="json", exclude={"meta"})
    data["main"] = None
    less = await m.Argument.Update(**data).save(detail=True)
    assert less.main is None and len(less.evidence) == 1


@no_type_check
async def test_a_basis_that_is_not_what_was_chosen_rests_on_is_refused(
    clear_database, resolving
):
    m = models()
    w = await world(m, resolving)
    other = await m.Factoid.Create(
        label="Another",
        statements=[{"type": "Naming", "label": "Called Nan", "name": "Nan"}],
    ).save(detail=True)

    def forged(via, *targets, via_type="Digest"):
        return {
            "type": "PGCitedBasis",
            "via_id": via,
            "via_type": via_type,
            "basis": [cite(t) for t in targets],
        }

    # (a naming put where only births go, by calling it the basis of something)
    with pytest.raises(
        PanglossReferenceError,
        match="is not what it\n?.*rests on|is not what it rests on",
    ):
        await m.Argument.Create(
            label="A", evidence=[], main=forged(w.digest.id, other.statements[0])
        ).save()
    # (one statement left out, one added)
    for targets in ([w.birth], [w.birth, w.naming, other.statements[0]]):
        with pytest.raises(PanglossReferenceError, match="is not what it rests on"):
            await m.Argument.Create(
                label="A", evidence=[forged(w.digest.id, *targets)]
            ).save()
    # (of something nothing resolves: a factoid, an id there is not)
    for via, via_type in ((w.factoid.id, "Factoid"), (uuid.uuid4(), "Digest")):
        with pytest.raises(
            PanglossReferenceError, match="is not something that is cited through"
        ):
            await m.Argument.Create(
                label="A", evidence=[forged(via, w.birth, via_type=via_type)]
            ).save()
    assert (await m.Argument.list()).results == []
    # (asked in the transaction of the write)
    assert ("Digest", True) in resolving.asked
    # (the whole of it, as it is: taken, and what is recorded of it is the app's)
    made = await m.Argument.Create(
        label="A", evidence=[forged(w.digest.id, w.naming, w.birth)]
    ).save(detail=True)
    assert made.evidence[0].via_rule == "digest"
    # (and on an update: a basis the document has not, and that is not right)
    data = made.model_dump(mode="json", exclude={"meta"})
    data["evidence"].append(forged(w.digest.id, w.birth))
    with pytest.raises(PanglossReferenceError, match="is not what it rests on"):
        await m.Argument.Update(**data).save()
    assert len((await m.Argument.get(made.id)).evidence) == 1


@no_type_check
async def test_without_an_app_that_resolves_it_a_citation_is_as_it_was(
    clear_database, resolving
):
    m = models()
    w = await world(m, resolving)
    hooks.resolve_citation.remove(resolving.resolver)
    try:
        # (a digest is no statement: refused as any citation of a class the field does not take)
        with pytest.raises(PanglossReferenceError, match="cannot be cited here"):
            await m.Argument.Create(label="A", evidence=[cite(w.digest)]).save()
        made = await m.Argument.Create(label="A", evidence=[cite(w.birth)]).save(
            detail=True
        )
        assert made.evidence[0].type == "PGCitation"
    finally:
        hooks.resolve_citation.append(resolving.resolver)
    # (what the resolver does not answer for is cited as it is)
    resolving.asked.clear()
    plain = await m.Argument.Create(label="B", evidence=[cite(w.naming)]).save(
        detail=True
    )
    assert plain.evidence[0].type == "PGCitation"
    assert resolving.asked == [("Naming", False)]


def database():
    return backend.current().database()


async def mark(via, state):
    db = database()

    @db.write_transaction
    async def write(tx):
        return await cypher_citations.mark_via(tx, via, state)

    count = await write()
    cypher_citations.flush_marks()
    return count


@no_type_check
async def test_a_basis_is_marked_when_what_was_chosen_changes_or_goes(
    clear_database, db_driver, resolving
):
    m = models()
    w = await world(m, resolving)
    first = await m.Argument.Create(
        label="First", evidence=[cite(w.digest)], main=cite(w.digest)
    ).save(detail=True)
    second = await m.Argument.Create(label="Second", evidence=[cite(w.digest)]).save()
    untouched = await m.Argument.Create(label="Third", evidence=[cite(w.birth)]).save()

    assert await mark(w.digest.id, citations.BASIS_LOST) == 3
    read = await m.Argument.get(first.id)
    assert read.evidence[0].derivation_state == "lost"
    assert read.main.derivation_state == "lost"
    assert (await m.Argument.get(second.id)).evidence[0].derivation_state == "lost"
    # (the listeners are told of each document, when the write has committed)
    assert sorted(
        (str(x.head_id), x.head_type, x.state, str(x.via_id)) for x in resolving.marked
    ) == sorted(
        [
            (str(first.id), "Argument", "lost", str(w.digest.id)),
            (str(first.id), "Argument", "lost", str(w.digest.id)),
            (str(second.id), "Argument", "lost", str(w.digest.id)),
        ]
    )
    assert {x.basis_id for x in resolving.marked} == {
        read.evidence[0].id,
        read.main.id,
        (await m.Argument.get(second.id)).evidence[0].id,
    }
    # (the same again marks nothing, and tells nobody)
    resolving.marked.clear()
    assert await mark(w.digest.id, citations.BASIS_LOST) == 0
    assert resolving.marked == []
    assert await mark(w.digest.id, citations.BASIS_CHANGED) == 3
    assert {x.state for x in resolving.marked} == {"changed"}
    # (back: cleared)
    resolving.marked.clear()
    assert await mark(w.digest.id, "") == 3
    assert (await m.Argument.get(first.id)).evidence[0].derivation_state == ""
    assert {x.state for x in resolving.marked} == {""}
    # (of something nothing was cited through: nothing)
    assert await mark(uuid.uuid4(), citations.BASIS_LOST) == 0
    assert (await m.Argument.get(untouched.id)).evidence[0].type == "PGCitation"
    # (the mark stays through a save that sends it back, and goes with one that sends it empty)
    await mark(w.digest.id, citations.BASIS_LOST)
    kept = await as_update(await m.Argument.get(first.id), label="Saved").save(
        detail=True
    )
    assert kept.evidence[0].derivation_state == "lost"
    data = kept.model_dump(mode="json", exclude={"meta"})
    data["evidence"][0]["derivation_state"] = ""
    looked = await m.Argument.Update(**data).save(detail=True)
    assert looked.evidence[0].derivation_state == ""
    assert looked.main.derivation_state == "lost"


@no_type_check
async def test_an_app_marks_in_the_transaction_of_the_write_that_changes_what_was_chosen(
    clear_database, resolving
):
    m = models()
    w = await world(m, resolving)
    states = {"update": "changed", "delete": "lost", "undelete": "", "create": ""}
    seen = []

    async def in_write(tx, op, model, id):
        seen.append((op, model.__name__))
        if model.__name__ == "Digest":
            await cypher_citations.mark_via(tx, id, states[op])

    hooks.in_write.append(in_write)
    try:
        argument = await m.Argument.Create(label="A", evidence=[cite(w.digest)]).save()
        assert seen == [("create", "Argument")]

        async def state():
            return (await m.Argument.get(argument.id)).evidence[0].derivation_state

        await m.Digest.Update(id=w.digest.id, label="Changed", text="").save()
        assert await state() == "changed"
        assert [(x.state, x.head_id) for x in resolving.marked] == [
            ("changed", argument.id)
        ]
        await m.Digest.delete(w.digest.id)
        assert await state() == "lost"
        await m.Digest.undelete(w.digest.id)
        assert await state() == ""
        assert [x.state for x in resolving.marked] == ["changed", "lost", ""]
        assert seen[1:] == [
            ("update", "Digest"),
            ("delete", "Digest"),
            ("undelete", "Digest"),
        ]

        # (a write that fails marks nothing: the hook is in its transaction)
        async def failing(tx, op, model, id):
            if model.__name__ == "Digest" and op == "delete":
                raise RuntimeError("no")

        hooks.in_write.append(failing)
        try:
            with pytest.raises(RuntimeError):
                await m.Digest.delete(w.digest.id)
        finally:
            hooks.in_write.remove(failing)
        cypher_citations._marks.clear()
        assert await state() == ""
        assert (await m.Digest.get(w.digest.id)).label == "Changed"
    finally:
        hooks.in_write.remove(in_write)


@no_type_check
async def test_a_basis_over_the_api(clear_database, resolving, api):  # noqa: F811
    m = models()
    client, users = await api()
    w = await world(m, resolving)
    made = await client.post(
        "/api/Argument?detail=true",
        json={
            "type": "Argument",
            "label": "A",
            # (as any citation is written: by the class and id of what is chosen)
            "evidence": [{"type": "Digest", "id": str(w.digest.id)}],
        },
        headers=users["ann"],
    )
    assert made.status_code in (200, 201), made.text
    (basis,) = made.json()["evidence"]
    assert basis["type"] == "PGCitedBasis" and basis["viaId"] == str(w.digest.id)
    assert (basis["viaRule"], basis["viaState"], basis["derivationState"]) == (
        "digest",
        "there",
        "",
    )
    assert [c["targetLabel"] for c in basis["basis"]] == ["Ann is born", "Called Anna"]
    # (sent back as it was read)
    body = {k: v for k, v in made.json().items() if k != "meta"}
    body["label"] = "A again"
    saved = await client.put(
        f"/api/Argument/{body['id']}",
        json=body,
        headers={**users["ann"], "If-Match": "*"},
    )
    assert saved.status_code in (200, 204), saved.text
    # (a basis made up: 422, with why)
    body["evidence"][0]["basis"] = body["evidence"][0]["basis"][:1]
    refused = await client.put(
        f"/api/Argument/{body['id']}",
        json=body,
        headers={**users["ann"], "If-Match": "*"},
    )
    assert refused.status_code == 422, refused.text
    assert "is not what it rests on" in refused.text


@no_type_check
async def test_what_is_recorded_as_chosen_may_be_the_whole_of_what_was_named(
    clear_database, resolving
):
    """A part of something that is cited through what it rests on (a statement inside a derived document): the app
    says the whole is what was chosen (`ResolvedCitation.via`), so the basis is found, and marked, by the whole"""
    m = models()
    w = await world(m, resolving)
    part = await m.Factoid.Create(
        label="Another",
        statements=[{"type": "Naming", "label": "Called Nan", "name": "Nan"}],
    ).save(detail=True)
    (naming,) = part.statements
    whole = ("Digest", w.digest.id)

    async def of_the_whole(type_name, id, tx):
        if str(id) not in (str(naming.id), str(w.digest.id)):
            return None
        return hooks.ResolvedCitation(
            targets=(("Birth", str(w.birth.id)),),
            rule="digest",
            key="k",
            label="A digest",
            via=whole,
        )

    hooks.resolve_citation.insert(0, of_the_whole)
    try:
        argument = await m.Argument.Create(label="A", evidence=[cite(naming)]).save()
        (basis,) = (await m.Argument.get(argument.id)).evidence
        # (the statement was named; the digest is recorded, and asked about again in the write)
        assert basis.type == "PGCitedBasis"
        assert (basis.via_id, basis.via_type) == (w.digest.id, "Digest")
        assert [c.target_id for c in basis.basis] == [w.birth.id]
        # (read and sent back as it is: taken, as the basis the document has)
        await as_update(await m.Argument.get(argument.id), label="A, again").save()
        (again,) = (await m.Argument.get(argument.id)).evidence
        assert (again.via_id, again.via_type) == (w.digest.id, "Digest")

        assert await mark(w.digest.id, "lost") == 1
        assert (await m.Argument.get(argument.id)).evidence[
            0
        ].derivation_state == "lost"
    finally:
        hooks.resolve_citation.remove(of_the_whole)
