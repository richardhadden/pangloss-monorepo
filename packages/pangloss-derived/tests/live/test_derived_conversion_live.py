"""Making a derived document a document of one's own: the class changes in place, the justification is adopted, the
worker leaves it alone and says when its derivation stops holding"""

from typing import no_type_check

import pytest
from pangloss_derived import convert, why, written
from pangloss_derived.worker import pending_status, run_pending_derivations
from pangloss_derived.registry import DerivedRegistry
from pangloss_models import ModelRegistry

from test_derived_documents_worker_live import (
    derived,
    family,
    head,
    models,
    query,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def converted_one(m):
    n, factoids = await family(m)
    await run_pending_derivations()
    (doc,) = (await derived(m)).values()
    form = await convert.prefill("DerivedFactoid", doc.id, "Own")
    initial = form["initial"]
    initial["source"] = "my own note"
    summary = await convert.convert(
        "DerivedFactoid", doc.id, "Own", initial, form["version"]
    )
    return n, factoids, doc, form, summary


@no_type_check
async def test_conversion_keeps_the_id_history_and_adopts_the_justification(
    db_driver, clear_database
):
    m = models(with_kinship=False)
    from pangloss_derived.worker import worker

    await worker.take_lease()
    _, _, doc, form, summary = await converted_one(m)
    assert form["type"] == "Own" and form["version"] == 1
    assert [s["targetId"] for s in form["sources"]]
    assert summary["id"] == str(doc.id) and summary["type"] == "Own"

    own = await m.Own.get(doc.id)
    assert own.source == "my own note"
    assert own.meta.version == 2
    assert await m.DerivedFactoid.get(doc.id) is None
    assert [s.id for s in own.statements] == [s.id for s in doc.statements]
    # the derivation stays recorded on it
    (row,) = await query(
        "MATCH (h:HeadNode {id: $id}) RETURN h.derived_by AS by", id=str(doc.id)
    )
    assert row["by"] == "siblings"
    (j,) = await query(
        "MATCH (j:PGJustification {document_id: $id}) RETURN j.adopted AS adopted, j.adopted_by AS by",
        id=str(doc.id),
    )
    assert j["adopted"] is True
    info = await why.of_document("Own", doc.id)
    assert info["converted"] and info["holds"] and info["rule"] == "siblings"
    await worker.give_up_lease()


@no_type_check
async def test_the_worker_leaves_a_converted_document_alone(db_driver, clear_database):
    m = models(with_kinship=False)
    from pangloss_derived.worker import worker

    await worker.take_lease()
    n, factoids, doc, _, _ = await converted_one(m)
    await run_pending_derivations()
    assert (await head(doc.id)).updates == 1
    # a rebuild finds it again and leaves it
    await worker.rebuild(DerivedRegistry.documents["siblings"])
    await run_pending_derivations()
    assert (await m.Own.get(doc.id)).meta.version == 2
    assert len((await m.DerivedFactoid.list()).results) == 0
    status = await pending_status()
    assert status["converted"] == {"siblings": {"converted": 1, "lost": 0}}
    assert status["written"].get("siblings", 0) == 0

    # the source goes: the document stays, and says its derivation no longer holds
    await m.Factoid.delete(factoids["A"].id)
    await run_pending_derivations()
    own = await m.Own.get(doc.id)
    assert own is not None and not (await head(doc.id)).deleted
    assert (await why.of_document("Own", doc.id))["holds"] is False
    assert [r["id"] for r in (await pending_status())["lost"]] == [str(doc.id)]

    # and when the derivation holds again, it is said so
    await m.Factoid.undelete(factoids["A"].id)
    await run_pending_derivations()
    assert (await why.of_document("Own", doc.id))["holds"] is True
    await worker.give_up_lease()


@no_type_check
async def test_a_removed_rule_keeps_a_converted_document(db_driver, clear_database):
    m = models(with_kinship=False)
    from pangloss_derived.worker import worker

    await worker.take_lease()
    _, _, doc, _, _ = await converted_one(m)
    await worker.remove_rule("siblings")
    assert await m.Own.get(doc.id) is not None
    assert (await why.of_document("Own", doc.id))["holds"] is False
    await worker.give_up_lease()


@no_type_check
async def test_only_the_classes_it_may_become(db_driver, clear_database):
    m = models(with_kinship=False, converts=False)
    assert convert.targets_of(m.DerivedFactoid) == []
    with pytest.raises(Exception, match="cannot be made"):
        convert.target_class(m.DerivedFactoid, "Own")
    with pytest.raises(Exception, match="not a derived document class"):
        convert.derived_class("Own")
    assert ModelRegistry._model_dict["Own"]
    assert written.KINDS


@no_type_check
async def test_a_class_change_that_is_not_a_conversion_is_refused(
    db_driver, clear_database
):
    from pangloss_derived import PanglossDerivedDocumentError

    m = models(with_kinship=False)
    await family(m)
    await run_pending_derivations()
    (doc,) = (await derived(m)).values()
    statements = [s.model_dump(mode="json") for s in doc.statements]
    with pytest.raises(PanglossDerivedDocumentError, match="only by converting"):
        await m.Own.Update(id=doc.id, label="Mine", statements=statements).save(
            changing_class_from=m.DerivedFactoid
        )
    assert (await m.DerivedFactoid.get(doc.id)) is not None
    (j,) = await query(
        "MATCH (j:PGJustification {document_id: $id}) RETURN j.adopted AS adopted",
        id=str(doc.id),
    )
    assert j["adopted"] is None


@no_type_check
async def test_a_document_whose_derivation_is_gone_is_not_converted(
    db_driver, clear_database
):
    """Between the justification going and the worker deleting the document: nothing is written"""
    from pangloss_derived.registry import PanglossDerivedError

    m = models(with_kinship=False)
    await family(m)
    await run_pending_derivations()
    (doc,) = (await derived(m)).values()
    form = await convert.prefill("DerivedFactoid", doc.id, "Own")
    db = __import__("pangloss_derived.worker", fromlist=["database"]).database()

    @db.write_transaction
    async def drop(tx):
        await (
            await tx.run(
                "MATCH (j:PGJustification {document_id: $id}) DETACH DELETE j",
                id=str(doc.id),
            )
        ).consume()

    await drop()
    with pytest.raises(PanglossDerivedError, match="no longer holds"):
        await convert.convert(
            "DerivedFactoid", doc.id, "Own", form["initial"], form["version"]
        )
    assert (await m.DerivedFactoid.get(doc.id)) is not None
    assert await m.Own.get(doc.id) is None


@no_type_check
async def test_a_justification_adopted_since_it_was_read_is_not_deleted(
    db_driver, clear_database
):
    """The worker read it as not adopted and then goes to delete it: a conversion committed between the two keeps
    its record, which is marked lost"""
    from pangloss_derived import store

    m = models(with_kinship=False)
    n, factoids, doc, _, _ = await converted_one(m)
    (j,) = await query(
        "MATCH (j:PGJustification {document_id: $id}) RETURN j.key AS key",
        id=str(doc.id),
    )
    db = __import__("pangloss_derived.worker", fromlist=["database"]).database()

    @db.write_transaction
    async def as_the_worker_would(tx):
        went = await written.run(tx, written.DELETE_UNADOPTED_QUERY, keys=[j["key"]])
        lost = await written.run(tx, written.LOSE_ADOPTED_QUERY, keys=[j["key"]])
        return went, lost

    went, lost = await as_the_worker_would()
    assert went == [] and [r["document"] for r in lost] == [str(doc.id)]
    assert (await why.of_document("Own", doc.id))["holds"] is False
    assert store.JUSTIFICATION


@no_type_check
async def test_what_the_form_starts_with_and_who_sees_why(db_driver, clear_database):
    from test_derived_documents_worker_live import as_a_reader

    m = models(with_kinship=False)
    await family(m)
    await run_pending_derivations()
    (doc,) = (await derived(m)).values()
    form = await convert.prefill("DerivedFactoid", doc.id, "Own")
    # the document stays the one it is, and so do the nodes in it
    assert form["initial"]["id"] == str(doc.id)
    assert [s["id"] for s in form["initial"]["statements"]] == [
        str(s.id) for s in doc.statements
    ]
    assert "sources" not in form["initial"] and "derivedBy" not in form["initial"]

    assert (await why.of_document("DerivedFactoid", doc.id))["convertsTo"] == ["Own"]
    # one that is not published is not described to a reader who may not see it
    await written.storage_of().operations.set_published_in_db(
        m.DerivedFactoid, doc.id, False
    )
    with as_a_reader():
        assert await why.of_document("DerivedFactoid", doc.id) is None
    assert await why.of_document("DerivedFactoid", doc.id) is not None


@no_type_check
async def test_the_author_clears_what_the_derivation_passed_through(
    db_driver, clear_database
):
    """A converted document keeps the context of its derivation (D19) until its author says that it no longer rests
    on it: then rules that read it read it as plain"""
    from test_derived_documents_worker_live import child_of, people

    m = models(maybe=True, with_siblings=False)
    n = await people(m, "ABP")
    await m.Factoid.Create(label="A of P", statements=[child_of(n.A, n.P)]).save()
    await m.Factoid.Create(
        label="B not of P",
        statements=[{"type": "Negative", "contents": [child_of(n.B, n.P)]}],
    ).save()
    await run_pending_derivations()
    (maybe,) = (await derived(m, "maybe_siblings")).values()
    assert (await why.of_document("DerivedFactoid", maybe.id))["context"] == [
        "Negative"
    ]
    # (a derived document's context is the worker's: not cleared)
    with pytest.raises(Exception, match="not a document made from a derived one"):
        await convert.clear_context("DerivedFactoid", maybe.id)

    form = await convert.prefill("DerivedFactoid", maybe.id, "Own")
    assert form["derivedContext"] == ["Negative"]
    await convert.convert(
        "DerivedFactoid", maybe.id, "Own", form["initial"], form["version"]
    )
    info = await why.of_document("Own", maybe.id)
    assert info["converted"] and info["context"] == ["Negative"]
    version = (await m.Own.get(maybe.id)).meta.version

    from pangloss_testing.live import run

    run(db_driver, "MATCH (p:PGPending) DETACH DELETE p")
    assert await convert.clear_context("Own", maybe.id) is True
    info = await why.of_document("Own", maybe.id)
    assert info["converted"] and info["context"] == []
    (row,) = await query(
        "MATCH (h:HeadNode {id: $id}) RETURN h.derived_context AS context, h.derived_by AS by",
        id=str(maybe.id),
    )
    assert row == {"context": [], "by": "maybe_siblings"}
    (j,) = await query(
        "MATCH (j:PGJustification {document_id: $id}) RETURN j.context_cleared_by AS by, "
        "j.context_labels AS labels",
        id=str(maybe.id),
    )
    # (the justification still says what the derivation passed through: it is the record)
    assert j["by"] is not None and j["labels"] == ["Negative"]
    # (not a version of the document; and it is marked for the rules that read it, as a write of it is)
    assert (await m.Own.get(maybe.id)).meta.version == version
    pending = await query(
        "MATCH (p:PGPending {head_id: $id}) RETURN p.kind AS kind", id=str(maybe.id)
    )
    assert "derive" in [p["kind"] for p in pending]
    # (again: nothing more to clear, and still what it is)
    assert await convert.clear_context("Own", maybe.id) is True
    # (a document nobody made from a derived one: not one)
    own = await m.Own.Create(label="Mine", statements=[child_of(n.A, n.P)]).save()
    assert await convert.clear_context("Own", own.id) is False


@no_type_check
async def test_the_filter_of_derived_documents_in_a_search(db_driver, clear_database):
    from pangloss_models import Match, PanglossSearchError
    from pangloss_models.search_where import export_search_patterns

    m = models(with_kinship=False)
    _, _, doc, _, _ = await converted_one(m)
    # (the family again, with another child: one derived document that stays derived)
    from test_derived_documents_worker_live import child_of, people

    n = await people(m, "CDQ")
    for child in (n.C, n.D):
        await m.Factoid.Create(label="x", statements=[child_of(child, n.Q)]).save()
    await run_pending_derivations()
    (still,) = (await m.DerivedFactoid.list()).results

    async def found(model, where):
        return sorted(
            str(r.id) for r in (await model.search(Match(where=where))).results
        )

    # (of a derived class: all of them are, and none is not)
    assert await found(m.DerivedFactoid, {"$derived_document": True}) == [str(still.id)]
    assert await found(m.DerivedFactoid, {"$derived_document": False}) == []
    # (one a person made their own is theirs)
    assert await found(m.Own, {"$derived_document": True}) == []
    assert await found(m.Own, {"$derived_document": False}) == [str(doc.id)]
    assert await found(m.Own, {"$not": {"$derived_document": False}}) == []
    typed = await m.DerivedFactoid.search(
        m.DerivedFactoid.Where(derived_document_=True)
    )
    assert [r.id for r in typed.results] == [still.id]
    with pytest.raises(PanglossSearchError, match="true or false"):
        await found(m.Own, {"$derived_document": "yes"})
    with pytest.raises(PanglossSearchError, match="only for document"):
        await found(m.Person, {"$derived_document": True})
    # (the search form is offered it only where it divides: neither class has derived and other documents below it)
    patterns = export_search_patterns(ModelRegistry._models)
    assert "flags" not in patterns["DerivedFactoid"]
    assert "flags" not in patterns["Own"] and "flags" not in patterns["Person"]
