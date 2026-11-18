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
