"""Changing the class of a document in place: `New.Update(...).save(changing_class_from=Old)`, as of an entity
(`test_change_class.py`).

The head keeps its id, whether it is published, who made it and what cites it; its labels and `type` become those of
the new class, and everything in it is written again, as in any update. It is a change to what is cited, and is
refused if a citation of the document is in a field that cannot hold the new class."""

from types import SimpleNamespace
from typing import no_type_check
from uuid import uuid7

import pytest
from pangloss_models import (
    Cites,
    Document,
    Entity,
    PanglossCitedError,
    PanglossClassChangeError,
    PanglossVersionConflictError,
    PanglossWriteError,
    hooks,
    initialise,
)

from .helpers import labels_of, run

pytestmark = pytest.mark.asyncio(loop_scope="session")


def declare():
    class Person(Entity):
        pass

    class Statement(Document):
        _meta = Document.Meta(create_directly=False)
        person: Person
        text: str = ""

    class Record(Document):
        _meta = Document.Meta(abstract=True)
        statements: list[Statement]

    class Draft(Record):
        worked_out_by: str = ""

    class Factoid(Record):
        source: str = ""

    class Letter(Document):
        text: str = ""

    class Essay(Document):
        about_any: list[Cites[Record]]  # ty: ignore[invalid-type-form]
        about_drafts: list[Cites[Draft]]  # ty: ignore[invalid-type-form]
        parts: list[Cites[Statement]]  # ty: ignore[invalid-type-form]

    initialise()
    return SimpleNamespace(
        Person=Person,
        Statement=Statement,
        Record=Record,
        Draft=Draft,
        Factoid=Factoid,
        Letter=Letter,
        Essay=Essay,
    )


@no_type_check
async def a_draft(m):
    made = await m.Person.Create(label="Ann").save()
    ann = {"type": "Person", "id": made.id}
    draft = await m.Draft.Create(
        label="A draft",
        worked_out_by="a rule",
        statements=[
            {"type": "Statement", "label": "Ann, once", "person": ann, "text": "one"},
            {"type": "Statement", "label": "Ann, twice", "person": ann, "text": "two"},
        ],
    ).save(detail=True)
    return made, draft


def statements_of(document, keep_ids=True) -> list[dict]:
    return [
        {
            "type": "Statement",
            **({"id": s.id} if keep_ids else {}),
            "label": s.label,
            "person": {"type": "Person", "id": s.person.id},
            "text": s.text,
        }
        for s in document.statements
    ]


@no_type_check
async def test_a_document_changes_class_and_keeps_its_id(db_driver, clear_database):
    m = declare()
    ann, draft = await a_draft(m)
    events = []
    hooks.after_write.append(events.append)
    try:
        saved = await m.Factoid.Update(
            id=draft.id,
            label="A factoid now",
            source="f. 3",
            statements=statements_of(draft),
        ).save(expected_version=1, changing_class_from=m.Draft, detail=True)
    finally:
        hooks.after_write.remove(events.append)

    assert saved.id == draft.id
    assert saved.type == "Factoid"
    labels = labels_of(db_driver, draft.id)
    assert {"Factoid", "Record", "Document", "HeadNode"} <= labels
    assert "Draft" not in labels
    assert await m.Draft.get(draft.id) is None
    factoid = await m.Factoid.get(draft.id)
    assert factoid.label == "A factoid now"
    assert factoid.source == "f. 3"
    assert factoid.meta.version == 2
    # (what it had and the new class has not is gone from the node)
    assert run(
        db_driver, "MATCH (n {id: $id}) RETURN n.worked_out_by AS w", id=str(draft.id)
    ) == [{"w": None}]
    # the statements are those it had: their ids were sent
    assert [s.id for s in factoid.statements] == [s.id for s in draft.statements]
    assert [s.text for s in factoid.statements] == ["one", "two"]
    # read by the parent class, it is a Factoid; and it is listed as one
    assert (await m.Record.get(draft.id)).type == "Factoid"
    assert [d.id for d in (await m.Factoid.list()).results] == [draft.id]
    assert (await m.Draft.list()).results == []
    # the entity it names sees it as what it is now
    person = await m.Person.get(ann.id)
    assert {s.type for s in person.person_reverse} == {"Statement"}
    # and the write says what it was before
    assert [(e.op, e.model, e.changed_class_from) for e in events] == [
        ("update", m.Factoid, m.Draft)
    ]


@no_type_check
async def test_a_document_changed_without_ids_gets_new_parts(db_driver, clear_database):
    m = declare()
    _, draft = await a_draft(m)
    await m.Factoid.Update(
        id=draft.id,
        label="A factoid now",
        statements=statements_of(draft, keep_ids=False)[:1],
    ).save(changing_class_from=m.Draft)
    factoid = await m.Factoid.get(draft.id)
    assert len(factoid.statements) == 1
    assert factoid.statements[0].id != draft.statements[0].id
    # nothing of what it had is left behind
    assert (
        run(
            db_driver,
            "MATCH (n:Statement) RETURN count(n) AS c",
        )[0]["c"]
        == 1
    )


@no_type_check
async def test_a_document_class_change_needs_the_class_it_is_changed_from(
    db_driver, clear_database
):
    m = declare()
    _, draft = await a_draft(m)
    letter = await m.Letter.Create(label="A letter").save()

    with pytest.raises(PanglossClassChangeError, match="is a Letter, not a Draft"):
        await m.Factoid.Update(id=letter.id, label="No", statements=[]).save(
            changing_class_from=m.Draft
        )
    with pytest.raises(PanglossWriteError):
        await m.Factoid.Update(id=uuid7(), label="No", statements=[]).save(
            changing_class_from=m.Draft
        )
    # without it, an update cannot change the class
    with pytest.raises(PanglossWriteError):
        await m.Factoid.Update(id=draft.id, label="No", statements=[]).save()
    assert "Draft" in labels_of(db_driver, draft.id)
    assert (await m.Draft.get(draft.id)).meta.version == 1


@no_type_check
async def test_a_document_inside_another_does_not_change_class(
    db_driver, clear_database
):
    m = declare()
    _, draft = await a_draft(m)
    inside = draft.statements[0]
    with pytest.raises(PanglossWriteError):
        await m.Letter.Update(id=inside.id, label="No").save(
            changing_class_from=m.Statement
        )
    assert "Statement" in labels_of(db_driver, inside.id)


@no_type_check
async def test_a_document_class_change_checks_the_version(db_driver, clear_database):
    m = declare()
    _, draft = await a_draft(m)
    with pytest.raises(PanglossVersionConflictError):
        await m.Factoid.Update(id=draft.id, label="No", statements=[]).save(
            expected_version=4, changing_class_from=m.Draft
        )
    assert (await m.Draft.get(draft.id)).label == "A draft"


@no_type_check
async def test_a_cited_document_changes_class_only_when_acknowledged(
    db_driver, clear_database
):
    m = declare()
    _, draft = await a_draft(m)
    essay = await m.Essay.Create(
        label="An essay",
        about_any=[{"type": "Draft", "id": draft.id}],
        about_drafts=[],
        parts=[],
    ).save(detail=True)
    update = m.Factoid.Update(
        id=draft.id, label="A factoid now", statements=statements_of(draft)
    )

    with pytest.raises(PanglossCitedError) as refused:
        await update.save(changing_class_from=m.Draft)
    assert [str(c["id"]) for c in refused.value.changed] == [str(essay.id)]
    assert "Draft" in labels_of(db_driver, draft.id)

    await update.save(changing_class_from=m.Draft, acknowledge_citations=True)
    assert "Factoid" in labels_of(db_driver, draft.id)
    again = await m.Essay.get(essay.id)
    (citation,) = again.about_any
    assert citation.target_id == draft.id
    assert citation.target_type == "Factoid"
    assert citation.changed_since_cited is True
    # the essay can be saved again as it was read
    await m.Essay.Update(
        id=essay.id,
        label="An essay",
        about_any=[
            {
                "type": "PGCitation",
                "id": citation.id,
                "target_type": "Factoid",
                "target_id": draft.id,
            }
        ],
        about_drafts=[],
        parts=[],
    ).save()


@no_type_check
async def test_a_class_change_is_refused_if_a_citing_field_cannot_hold_the_new_class(
    db_driver, clear_database
):
    m = declare()
    _, draft = await a_draft(m)
    await m.Essay.Create(
        label="An essay on drafts",
        about_any=[],
        about_drafts=[{"type": "Draft", "id": draft.id}],
        parts=[],
    ).save()

    with pytest.raises(PanglossClassChangeError, match="An essay on drafts"):
        await m.Factoid.Update(
            id=draft.id, label="A factoid now", statements=statements_of(draft)
        ).save(changing_class_from=m.Draft, acknowledge_citations=True)
    # nothing changed
    assert "Draft" in labels_of(db_driver, draft.id)
    assert (await m.Draft.get(draft.id)).meta.version == 1


@no_type_check
async def test_a_class_change_that_removes_a_cited_part_is_refused_as_an_update_is(
    db_driver, clear_database
):
    m = declare()
    _, draft = await a_draft(m)
    await m.Essay.Create(
        label="An essay",
        about_any=[],
        about_drafts=[],
        parts=[{"type": "Statement", "id": draft.statements[1].id}],
    ).save()

    with pytest.raises(PanglossCitedError) as refused:
        await m.Factoid.Update(
            id=draft.id, label="A factoid now", statements=statements_of(draft)[:1]
        ).save(changing_class_from=m.Draft, acknowledge_citations=True)
    assert refused.value.removed
    assert "Draft" in labels_of(db_driver, draft.id)

    # with the part kept (its id sent), the cited part is what it was: nothing to acknowledge
    await m.Factoid.Update(
        id=draft.id, label="A factoid now", statements=statements_of(draft)
    ).save(changing_class_from=m.Draft)
    assert "Factoid" in labels_of(db_driver, draft.id)


@no_type_check
async def test_what_an_app_keeps_on_the_head_stays_through_a_class_change(
    db_driver, clear_database
):
    """`hooks.kept_head_properties`: kept by an update that does not write a property of that name"""
    m = declare()
    _, draft = await a_draft(m)
    run(db_driver, "MATCH (n {id: $id}) SET n.made_by = 'a rule'", id=str(draft.id))
    hooks.kept_head_properties.extend(["made_by", "worked_out_by"])
    try:
        # an update of the class that writes `worked_out_by` writes it
        await m.Draft.Update(
            id=draft.id,
            label="A draft",
            worked_out_by="another rule",
            statements=statements_of(draft),
        ).save()
        await m.Factoid.Update(
            id=draft.id, label="A factoid now", statements=statements_of(draft)
        ).save(changing_class_from=m.Draft)
        await m.Factoid.Update(
            id=draft.id, label="And again", statements=statements_of(draft)
        ).save()
    finally:
        del hooks.kept_head_properties[-2:]
    assert run(
        db_driver,
        "MATCH (n {id: $id}) RETURN n.made_by AS made, n.worked_out_by AS worked",
        id=str(draft.id),
    ) == [{"made": "a rule", "worked": "another rule"}]

    # without the hook, an update drops what it does not write
    await m.Factoid.Update(
        id=draft.id, label="Once more", statements=statements_of(draft)
    ).save()
    assert run(
        db_driver, "MATCH (n {id: $id}) RETURN n.made_by AS made", id=str(draft.id)
    ) == [{"made": None}]


@no_type_check
async def test_what_runs_in_the_write_is_told_of_the_class_change(
    db_driver, clear_database
):
    m = declare()
    _, draft = await a_draft(m)
    seen = []

    async def note(tx, op, model, id):
        seen.append((op, model, hooks.class_changed_from()))

    async def refuse(tx, op, model, id):
        if hooks.class_changed_from() is m.Draft and model is m.Letter:
            raise PanglossWriteError("Not a letter")

    hooks.in_write.extend([note, refuse])
    try:
        await m.Draft.Update(
            id=draft.id, label="A draft", statements=statements_of(draft)
        ).save()
        with pytest.raises(PanglossWriteError, match="Not a letter"):
            await m.Letter.Update(id=draft.id, label="A letter").save(
                changing_class_from=m.Draft
            )
        assert "Draft" in labels_of(db_driver, draft.id)
        await m.Factoid.Update(
            id=draft.id, label="A factoid now", statements=statements_of(draft)
        ).save(changing_class_from=m.Draft)
    finally:
        hooks.in_write.remove(note)
        hooks.in_write.remove(refuse)
    assert hooks.class_changed_from() is None
    assert [s for s in seen if s[0] == "update"] == [
        ("update", m.Draft, None),
        ("update", m.Letter, m.Draft),
        ("update", m.Factoid, m.Draft),
    ]
