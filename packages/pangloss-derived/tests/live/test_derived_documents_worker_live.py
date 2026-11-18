"""The worker writing derived documents, on the backend under test: made, kept as they are, changed in place, deleted
and brought back, published as what they rest on is; chains of rules; what a rebuild does; a rule changed or removed;
citing one; an entity only derived documents name"""

import contextlib
import uuid
from typing import no_type_check

import pytest
from pangloss_core import storage_of
from pangloss_models import (
    Cites,
    Document,
    Entity,
    PanglossReferenceError,
    SemanticSpace,
    initialise,
)

from pangloss_derived import (
    DerivedDocument,
    DerivedDocumentMeta,
    DerivedFrom,
    PanglossDerivedDocumentError,
    Var,
    rule,
    unordered,
    written,
)
from pangloss_derived.documents import node_id
from pangloss_derived.registry import DerivedRegistry
from pangloss_derived.worker import (
    database,
    pending_status,
    run_pending_derivations,
    worker,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


class Names(dict):
    __getattr__ = dict.__getitem__


@no_type_check
def models(
    max_per_seed=2_000,
    label="Siblings",
    kind="derived",
    with_siblings=True,
    with_kinship=True,
    maybe=False,
    max_people=None,
    converts=True,
):
    """`label`, `kind`: of the template of `siblings` (another is another hash, and another document).
    `with_siblings=False`: the rule is not there. `maybe`: a rule that derives through a denial as well"""
    from typing import Annotated

    from annotated_types import MaxLen
    from pangloss_models import ModelRegistry

    # (a test may declare the models again, as a project changed and started again would have them)
    ModelRegistry._reset()

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
        people: (
            Annotated[list[Person], MaxLen(max_people)] if max_people else list[Person]
        )
        kind: str = "full"

    class Kin(Statement):
        people: list[Person]

    class Factoid(Document):
        statements: list[Statement | Negative[Statement]]

    class Own(Document):
        """A document of someone's own: what a derived factoid is made when someone takes it over"""

        statements: list[Statement]
        source: str = ""

    class DerivedFactoid(Document, DerivedDocument):
        """What follows from what factoids say"""

        _derived_document_meta = DerivedDocumentMeta(
            max_per_seed=max_per_seed, converts_to=Own if converts else None
        )
        sources: list[DerivedFrom[Factoid | DerivedFactoid | Own]]
        statements: list[Statement]

    class Note(Document):
        """What someone writes, citing what they read"""

        evidence: list[Cites[Sibling | Kin | DerivedFactoid]] = []

    if with_siblings:

        @rule
        def siblings(a: Var[Person], b: Var[Person], p: Var[Person]):
            """Two children of one parent are siblings"""
            return DerivedFactoid.Derive(
                label=label,
                statements=[Sibling.Template(label=label, people=[a, b], kind=kind)],
            ).when(
                ChildOf.Where(child=a, parent=p),
                ChildOf.Where(child=b, parent=p),
                unordered(a, b),
            )

    if maybe:

        @rule
        def maybe_siblings(a: Var[Person], b: Var[Person], p: Var[Person]):
            return DerivedFactoid.Derive(
                label="Siblings?",
                statements=[
                    Sibling.Template(label="Siblings?", people=[a, b], kind="maybe")
                ],
            ).when(
                ChildOf.Where(child=a, parent=p),
                ChildOf.Where(child=b, parent=p),
                unordered(a, b),
                allow=[Negative],
            )

    if with_kinship:

        @rule
        def kinship(s: Var[Sibling], a: Var[Person], b: Var[Person]):
            """Siblings are kin: whoever, or whatever, says they are siblings"""
            return DerivedFactoid.Derive(
                label="Kin",
                statements=[Kin.Template(label="Kin", people=[a, b])],
            ).when(
                Sibling.Where(is_=s, people=a),
                Sibling.Where(is_=s, people=b),
                unordered(a, b),
            )

    initialise()
    return Names(locals())


def ref(item):
    return {"type": "Person", "id": item.id}


def child_of(child, parent):
    return {"type": "ChildOf", "label": "c", "child": ref(child), "parent": ref(parent)}


async def people(m, names):
    return Names({n: await m.Person.Create(label=n).save() for n in names})


async def family(m, children="AB", parent="P"):
    """A parent and children, each child in a factoid of its own. Gives the people and the factoids (by child)"""
    n = await people(m, children + parent)
    factoids = Names()
    for child in children:
        factoids[child] = await m.Factoid.Create(
            label=f"{child} of {parent}", statements=[child_of(n[child], n[parent])]
        ).save()
    return n, factoids


async def derived(m, by="siblings"):
    """The derived factoids of a rule that are there, read in full, by the labels of the people of their statement"""
    listed = (await m.DerivedFactoid.list(page_size=500)).results
    found = {}
    for item in listed:
        if item.derived_by != by:
            continue
        full = await m.DerivedFactoid.get(item.id)
        found[tuple(sorted(p.label for p in full.statements[0].people))] = full
    return found


async def query(cypher, **params):
    db = database()

    @db.read_transaction
    async def read(tx):
        result = await tx.run(cypher, **params)
        return [dict(r) async for r in result]

    return await read()


async def head(id):
    """What is on the head node of a document: how many times it was updated, deleted and undeleted, and its flags"""
    (row,) = await query(
        "MATCH (h:HeadNode {id: $id}) "
        "OPTIONAL MATCH (h)<-[:is_update_of]-(u) WITH h, count(u) AS updates "
        "OPTIONAL MATCH (h)<-[:is_deletion_of]-(d) WITH h, updates, count(d) AS deletions "
        "RETURN updates, deletions, coalesce(h.deleted, false) AS deleted, h.published AS published, "
        "       h.pg_derived_content AS content",
        id=str(id),
    )
    return Names(row)


async def writers(id):
    return sorted(
        r["username"]
        for r in await query(
            "MATCH (h:HeadNode {id: $id})<-[]-(record)-[:created_by|updated_by|deleted_by]->(u:PGUser) "
            "RETURN DISTINCT u.username AS username",
            id=str(id),
        )
    )


async def pending_of(kind):
    return sorted(
        r["id"]
        for r in await query(
            "MATCH (p:PGPending {kind: $kind}) RETURN p.head_id AS id", kind=kind
        )
    )


async def justifications(rule_name):
    return await query(
        "MATCH (j:PGJustification {rule: $rule}) "
        "RETURN j.key AS key, j.document_id AS document, j.nodes AS nodes, j.sources AS sources, "
        "       j.context_labels AS context_labels",
        rule=rule_name,
    )


async def change_statement(m, factoid_id, index, **changes):
    """Update a factoid with one statement changed, the ids of all its statements kept"""
    factoid = await m.Factoid.get(factoid_id)
    statements = [s.model_dump(mode="json") for s in factoid.statements]
    statements[index].update(changes)
    await m.Factoid.Update(
        id=factoid.id, label=factoid.label, statements=statements
    ).save()


@contextlib.contextmanager
def as_a_reader():
    """As a request that is not logged in: what is not published is not seen"""
    from pangloss_users import see_unpublished

    token = see_unpublished.set(False)
    try:
        yield
    finally:
        see_unpublished.reset(token)


def counts():
    """The counts of the worker of this process so far (a copy: compare one with a later one)"""
    import dataclasses

    return dataclasses.replace(worker.stats.documents)


def since(before):
    import dataclasses

    now = worker.stats.documents
    return {
        f.name: getattr(now, f.name) - getattr(before, f.name)
        for f in dataclasses.fields(now)
        if getattr(now, f.name) != getattr(before, f.name)
    }


# ---------------------------------------------------------------------------
# Made
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_document_is_made_for_each_justification(clear_database):
    m = models(with_kinship=False)
    n, f = await family(m, "ABC")
    await run_pending_derivations()
    found = await derived(m)
    assert sorted(found) == [("A", "B"), ("A", "C"), ("B", "C")]
    made = found["A", "B"]
    assert made.label == "Siblings" and made.type == "DerivedFactoid"
    # (what it rests on: the two factoids its patterns were found in, not the third)
    assert sorted(str(c.target_id) for c in made.sources) == sorted(
        [str(f.A.id), str(f.B.id)]
    )
    assert {c.type for c in made.sources} == {"PGUnprotectedCitation"}
    assert {c.target_type for c in made.sources} == {"Factoid"}
    (statement,) = made.statements
    assert statement.type == "Sibling" and statement.kind == "derived"
    assert statement.label == "Siblings"
    (listed,) = [d for d in (await m.DerivedFactoid.list()).results if d.id == made.id]
    assert listed.derived_by == "siblings" and listed.derived_context == []
    # (written by the user of the worker, as an ordinary write: once)
    assert await writers(made.id) == ["derived"]
    state = await head(made.id)
    assert state.updates == 0 and not state.deleted and state.published is True
    assert state.content
    # (nothing is left pending)
    status = await pending_status()
    assert status["pending"]["pending"] == 0
    assert status["documents"]["pending"] == 0 == status["retractions"]["pending"]
    assert status["written"] == {"siblings": 3}
    assert status["rules"]["siblings"]["state"] == "ready"


@no_type_check
async def test_its_id_and_those_of_its_nodes_are_worked_out(clear_database):
    m = models(with_kinship=False)
    n, f = await family(m)
    await run_pending_derivations()
    (made,) = (await derived(m)).values()
    (justification,) = await justifications("siblings")
    assert justification["document"] == str(made.id)
    assert str(made.id) == written.document_id(justification["key"], "DerivedFactoid")
    assert justification["sources"] == sorted([str(f.A.id), str(f.B.id)])
    assert made.statements[0].id == node_id(made.id, "statements/0")
    assert sorted(c.id for c in made.sources) == sorted(
        node_id(made.id, f"sources/{i}") for i in range(2)
    )
    # (and are the same when the document is written again: something that reads it keeps what it found)
    await change_statement(m, f.A.id, 0, label="said again")
    await run_pending_derivations()
    (again,) = (await derived(m)).values()
    assert again.id == made.id and again.statements[0].id == made.statements[0].id


@no_type_check
async def test_nothing_is_written_when_nothing_has_changed(clear_database):
    m = models()
    n, f = await family(m, "ABC")
    await run_pending_derivations()
    every = {
        **await derived(m),
        **{("kin", *k): v for k, v in (await derived(m, "kinship")).items()},
    }
    assert len(every) == 6
    before = counts()
    # (the sources saved again as they are, every rule built again, the pending work done twice)
    for factoid in f.values():
        await change_statement(m, factoid.id, 0)
    await run_pending_derivations()
    for name in DerivedRegistry.order:
        await worker.rebuild(DerivedRegistry.all_checked()[name])
        await worker.drain()
    await run_pending_derivations()
    done = since(before)
    assert set(done) == {"same"} and done["same"] >= 6
    for document in every.values():
        state = await head(document.id)
        assert state.updates == 0 and state.deletions == 0
        again = await m.DerivedFactoid.get(document.id)
        assert again.statements[0].id == document.statements[0].id


# ---------------------------------------------------------------------------
# Gone, and back
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_document_goes_with_its_justification_and_comes_back_with_it(
    clear_database,
):
    m = models(with_kinship=False)
    n, f = await family(m)
    await run_pending_derivations()
    (made,) = (await derived(m)).values()
    await m.Factoid.delete(f.B.id)
    await run_pending_derivations()
    assert await derived(m) == {}
    assert await m.DerivedFactoid.get(made.id) is None
    state = await head(made.id)
    assert state.deleted and state.deletions == 1
    assert await justifications("siblings") == []
    # (the source is back: the same justification, so the same document, undeleted and not written again)
    await m.Factoid.undelete(f.B.id)
    await run_pending_derivations()
    (back,) = (await derived(m)).values()
    assert back.id == made.id
    state = await head(made.id)
    assert not state.deleted and state.updates == 0
    assert back.statements[0].id == made.statements[0].id


@no_type_check
async def test_a_statement_taken_out_removes_only_what_rested_on_it(clear_database):
    m = models(with_kinship=False)
    n, f = await family(m, "ABC")
    await run_pending_derivations()
    before = await derived(m)
    await m.Factoid.Update(id=f.C.id, label="C of P", statements=[]).save()
    await run_pending_derivations()
    after = await derived(m)
    assert sorted(after) == [("A", "B")]
    assert after["A", "B"].id == before["A", "B"].id
    assert (await head(before["A", "B"].id)).updates == 0
    assert (await head(before["A", "C"].id)).deleted


# ---------------------------------------------------------------------------
# Changed in place
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_changed_value_changes_the_document_in_place(clear_database):
    m = models(with_kinship=False)
    n, f = await family(m)
    extra = await people(m, "Z")
    await run_pending_derivations()
    (made,) = (await derived(m)).values()
    (was,) = await justifications("siblings")
    # (the same statement, now of another child: the nodes of the patterns are the same, the values are not)
    await change_statement(m, f.B.id, 0, child=ref(extra.Z))
    await run_pending_derivations()
    found = await derived(m)
    assert sorted(found) == [("A", "Z")]
    changed = found["A", "Z"]
    assert changed.id == made.id
    (now,) = await justifications("siblings")
    assert now["key"] != was["key"] and now["document"] == was["document"]
    assert now["nodes"] == was["nodes"]
    state = await head(made.id)
    assert state.updates == 1 and state.deletions == 0
    # (and back again: the first key, which takes the document back)
    await change_statement(m, f.B.id, 0, child=ref(n.B))
    await run_pending_derivations()
    (back,) = (await derived(m)).values()
    assert back.id == made.id and (await head(made.id)).updates == 2
    (again,) = await justifications("siblings")
    assert again["key"] == was["key"]


@no_type_check
async def test_a_merge_of_entities_changes_the_document_in_place(clear_database):
    m = models(with_kinship=False)
    n, f = await family(m)
    other = await people(m, "Z")
    await run_pending_derivations()
    (made,) = (await derived(m)).values()
    await m.Person.merge(absorb=n.B.id, into=other.Z.id)
    await run_pending_derivations()
    found = await derived(m)
    assert sorted(found) == [("A", "Z")]
    assert found["A", "Z"].id == made.id
    # (the merge itself moved the relation, which is a version of every document it touched; then the worker wrote
    # what its rule gives now)
    assert (await head(made.id)).updates == 2
    assert len(await justifications("siblings")) == 1


@no_type_check
async def test_only_one_for_one_takes_a_document_over(clear_database):
    """Two justifications share the nodes of their patterns (a statement with two children would; here, two
    statements changed in one write): nothing says which became which, so those gone go and those new are made"""
    m = models(with_kinship=False)
    n = await people(m, "ABCDP")
    factoid = await m.Factoid.Create(
        label="Both", statements=[child_of(n.A, n.P), child_of(n.B, n.P)]
    ).save()
    await run_pending_derivations()
    (made,) = (await derived(m)).values()
    # (one for one, in one document: taken over)
    await change_statement(m, factoid.id, 1, child=ref(n.C))
    await run_pending_derivations()
    (changed,) = (await derived(m)).values()
    assert changed.id == made.id

    # (a key that is found again while another has its document: it is given another id)
    db = database()
    (now,) = await justifications("siblings")
    from pangloss_derived import store

    found = store.Found()
    rule_ = DerivedRegistry.documents["siblings"]

    @db.read_transaction
    async def find(tx):
        ids = await store.ids_of_class(tx, "ChildOf")
        await store.run_seeded(tx, rule_, rule_.seeds[0].node, ids, found)

    await find()
    (current,) = found.documents.values()
    import dataclasses

    first_key = store.digest(
        "siblings", current.nodes, sorted([str(n.A.id), str(n.B.id)])
    )
    ghost = dataclasses.replace(current, key=first_key)
    found.documents[first_key] = ghost
    await written.store_found(db, found)
    by_key = {j["key"]: j["document"] for j in await justifications("siblings")}
    assert by_key[current.key] == str(made.id)
    assert by_key[first_key] != str(made.id)
    assert by_key[first_key] == written.document_id(first_key, "DerivedFactoid", 1)


@no_type_check
async def test_a_changed_template_changes_every_document_in_place(clear_database):
    m = models(with_kinship=False)
    n, f = await family(m)
    await run_pending_derivations()
    (made,) = (await derived(m)).values()
    was = DerivedRegistry.documents["siblings"].hash

    m = models(with_kinship=False, label="Brothers or sisters", kind="by rule")
    assert DerivedRegistry.documents["siblings"].hash != was
    status = await pending_status()
    assert status["rules"]["siblings"]["hash"] == was
    done = await run_pending_derivations()
    assert done["rules"] == {"siblings": "built"}
    (changed,) = (await derived(m)).values()
    assert changed.id == made.id and changed.label == "Brothers or sisters"
    assert changed.statements[0].kind == "by rule"
    assert changed.statements[0].id == made.statements[0].id
    assert (await head(made.id)).updates == 1


@no_type_check
async def test_a_removed_rule_takes_its_documents_with_it(clear_database):
    m = models()
    n, f = await family(m)
    await run_pending_derivations()
    (made,) = (await derived(m)).values()
    (kin,) = (await derived(m, "kinship")).values()

    m = models(with_siblings=False)
    status = await pending_status()
    assert status["written"] == {"siblings": 1, "kinship": 1}
    done = await run_pending_derivations()
    assert done["rules"] == {"siblings": "removed"}
    assert (await head(made.id)).deleted
    # (and what a rule derived from them)
    assert (await head(kin.id)).deleted
    assert (
        await m.DerivedFactoid.list() and (await m.DerivedFactoid.list()).results == []
    )
    assert await justifications("siblings") == [] == await justifications("kinship")
    assert (await pending_status())["written"] == {}


# ---------------------------------------------------------------------------
# Published as what it rests on is
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_document_is_published_when_all_it_rests_on_is(clear_database):
    m = models()
    n, f = await family(m)
    operations = storage_of().operations
    assert await operations.set_published_in_db(m.Factoid, f.B.id, False) is True
    # (the change left the work, as a write does)
    assert await pending_of("derive") != []
    await run_pending_derivations()
    (made,) = (await derived(m)).values()
    (kin,) = (await derived(m, "kinship")).values()
    assert (await head(made.id)).published is False
    # (and what rests on what is not published is not either)
    assert (await head(kin.id)).published is False

    with as_a_reader():
        assert (await m.DerivedFactoid.list()).results == []
        assert await m.DerivedFactoid.get(made.id) is None
    unpublished = await m.DerivedFactoid.list(published=False)
    assert {d.id for d in unpublished.results} == {made.id, kin.id}

    assert await operations.set_published_in_db(m.Factoid, f.B.id, True) is True
    assert await operations.set_published_in_db(m.Factoid, f.B.id, True) is False
    await run_pending_derivations()
    for document in (made, kin):
        state = await head(document.id)
        # (published, with no new version: what it says has not changed)
        assert state.published is True and state.updates == 0
    with as_a_reader():
        assert len((await m.DerivedFactoid.list()).results) == 2

    await operations.set_published_in_db(m.Factoid, f.A.id, False)
    await run_pending_derivations()
    assert (await head(made.id)).published is False
    assert (await head(kin.id)).published is False
    assert (await head(made.id)).updates == 0


# ---------------------------------------------------------------------------
# Chains
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_rule_reads_what_another_derived_and_its_documents_rest_on_those(
    clear_database,
):
    m = models()
    n, f = await family(m)
    said = await m.Factoid.Create(
        label="Said",
        statements=[{"type": "Sibling", "label": "s", "people": [ref(n.A), ref(n.P)]}],
    ).save()
    assert DerivedRegistry.readers["siblings"] == ["kinship"]
    await run_pending_derivations()
    (sibling,) = (await derived(m)).values()
    kin = await derived(m, "kinship")
    assert sorted(kin) == [("A", "B"), ("A", "P")]
    # (the one from what a person wrote rests on that; the one from a derived factoid, on the derived factoid)
    (source,) = kin["A", "P"].sources
    assert (source.target_id, source.target_type) == (said.id, "Factoid")
    (source,) = kin["A", "B"].sources
    assert (source.target_id, source.target_type) == (sibling.id, "DerivedFactoid")
    assert kin["A", "B"].statements[0].type == "Kin"
    (justification,) = [
        j for j in await justifications("kinship") if j["sources"] == [str(sibling.id)]
    ]
    assert justification["nodes"] == [str(sibling.statements[0].id)] * 2

    # (retraction goes step by step: the factoid, the derived sibling, the derived kin)
    await m.Factoid.delete(f.A.id)
    await run_pending_derivations()
    assert await derived(m) == {}
    assert sorted(await derived(m, "kinship")) == [("A", "P")]
    assert (await head(kin["A", "B"].id)).deleted
    # (and back, each the document it was)
    await m.Factoid.undelete(f.A.id)
    await run_pending_derivations()
    assert [d.id for d in (await derived(m)).values()] == [sibling.id]
    assert (await derived(m, "kinship"))["A", "B"].id == kin["A", "B"].id
    assert (await head(kin["A", "B"].id)).updates == 0


@no_type_check
async def test_what_a_document_was_derived_through_is_inherited(clear_database):
    m = models(maybe=True)
    n = await people(m, "ABP")
    await m.Factoid.Create(
        label="Denied",
        statements=[
            child_of(n.A, n.P),
            {"type": "Negative", "contents": [child_of(n.B, n.P)]},
        ],
    ).save()
    await run_pending_derivations()
    assert await derived(m) == {}
    (maybe,) = (await derived(m, "maybe_siblings")).values()
    (listed,) = [d for d in (await m.DerivedFactoid.list()).results if d.id == maybe.id]
    assert listed.derived_context == ["Negative"]
    # (the rule that reads it passes through no denial itself: its document has the label all the same)
    (kin,) = (await derived(m, "kinship")).values()
    (listed,) = [d for d in (await m.DerivedFactoid.list()).results if d.id == kin.id]
    assert listed.derived_context == ["Negative"]
    assert kin.sources[0].target_id == maybe.id
    (justification,) = await justifications("kinship")
    assert justification["context_labels"] == []


@no_type_check
async def test_a_first_build_follows_the_order_of_the_rules(clear_database):
    """Data loaded with nothing pending (as a bulk load leaves it): the rules are built in order, the documents of
    one written before the next is built, so each document is made once and none deleted"""
    m = models()
    n, f = await family(m, "ABC")
    db = database()

    @db.write_transaction
    async def forget(tx):
        await (await tx.run("MATCH (p:PGPending) DETACH DELETE p")).consume()

    await forget()
    assert DerivedRegistry.order.index("siblings") < DerivedRegistry.order.index(
        "kinship"
    )
    before = counts()
    done = await run_pending_derivations()
    assert done["rules"] == {"siblings": "built", "kinship": "built"}
    done = since(before)
    assert done["made"] == 6 and "deleted" not in done and "changed" not in done
    assert len(await derived(m)) == 3 == len(await derived(m, "kinship"))


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------


@no_type_check
async def test_what_no_longer_holds_is_deleted_before_anything_is_made(clear_database):
    m = models(with_kinship=False)
    n, f = await family(m, "AB")
    await run_pending_derivations()
    (made,) = (await derived(m)).values()
    # (one source goes, and another family is written: found in one batch, written one document at a time)
    await m.Factoid.delete(f.B.id)
    other = await people(m, "XYQ")
    for child in "XY":
        await m.Factoid.Create(
            label=child, statements=[child_of(other[child], other.Q)]
        ).save()
    await worker.take_lease()
    try:
        assert await worker.process_batch() > 0
        assert await pending_of(written.RETRACTIONS) == [str(made.id)]
        assert len(await pending_of(written.DOCUMENTS)) == 1
        before = counts()
        assert await worker.write_documents(1) == 1
        assert since(before) == {"deleted": 1}
        assert await pending_of(written.RETRACTIONS) == []
        assert await worker.write_documents(1) == 1
        assert since(before) == {"deleted": 1, "made": 1}
        assert await worker.write_documents(1) == 0
    finally:
        await worker.give_up_lease()


@no_type_check
async def test_a_source_deleted_before_the_document_is_written_leaves_it_out(
    clear_database,
):
    m = models(with_kinship=False)
    n, f = await family(m)
    await run_pending_derivations()
    extra = await people(m, "C")
    new = await m.Factoid.Create(
        label="C of P", statements=[child_of(extra.C, n.P)]
    ).save()
    await worker.take_lease()
    try:
        await worker.process_batch()
        waiting = await pending_of(written.DOCUMENTS)
        assert len(waiting) == 2
        await m.Factoid.delete(new.id)
        before = counts()
        await worker.write_documents(10)
        assert since(before) == {"left_out": 2}
        # (the delete left its own work, which settles it)
        await worker.drain()
    finally:
        await worker.give_up_lease()
    assert sorted(await derived(m)) == [("A", "B")]
    assert len(await justifications("siblings")) == 1


@no_type_check
async def test_a_written_document_that_would_give_too_many_gives_none(clear_database):
    m = models(max_per_seed=2, with_kinship=False)
    n = await people(m, "ABCDP")
    await m.Factoid.Create(
        label="Many", statements=[child_of(n[c], n.P) for c in "ABCD"]
    ).save()
    await run_pending_derivations()
    # (each statement is in three pairs, more than the two the class allows from one node: those of a statement that
    # gave too many are not written, and the rule's state says so)
    assert len(await derived(m)) < 6
    status = await pending_status()
    assert status["rules"]["siblings"]["overflows"] >= 1


@no_type_check
async def test_a_document_its_class_refuses_is_counted_and_not_tried_for_ever(
    clear_database, caplog
):
    m = models(with_kinship=False, max_people=1)
    n, f = await family(m)
    before = counts()
    await run_pending_derivations()
    assert since(before) == {"failed": 1}
    assert await derived(m) == {}
    assert (
        "is not one its class takes" in caplog.text
        or "could not be written" in caplog.text
    )
    assert await pending_of(written.DOCUMENTS) == []
    # (the justification is kept: when the class takes it, a rebuild writes it)
    assert len(await justifications("siblings")) == 1
    m = models(with_kinship=False)
    await worker.take_lease()
    try:
        await worker.rebuild(DerivedRegistry.documents["siblings"])
        await worker.drain()
    finally:
        await worker.give_up_lease()
    assert sorted(await derived(m)) == [("A", "B")]


@no_type_check
async def test_the_worker_s_own_write_leaves_work_only_if_a_rule_reads_it(
    clear_database,
):
    m = models(with_kinship=False)
    n, f = await family(m)
    assert not DerivedRegistry.readers.get("siblings")
    await worker.take_lease()
    try:
        await worker.sync_rules()
        await worker.process_batch()
        await worker.write_documents(10)
        assert await pending_of("derive") == []
    finally:
        await worker.give_up_lease()

    m = models()
    extra = await people(m, "C")
    await m.Factoid.Create(label="C", statements=[child_of(extra.C, n.P)]).save()
    await worker.take_lease()
    try:
        await worker.process_batch()
        await worker.write_documents(10)
        # (`kinship` reads what `siblings` writes: each document written is work for it)
        assert len(await pending_of("derive")) >= 2
        await worker.drain()
    finally:
        await worker.give_up_lease()


# ---------------------------------------------------------------------------
# Still nobody's but the worker's
# ---------------------------------------------------------------------------


@no_type_check
async def test_what_the_worker_wrote_is_still_not_changed_by_hand(clear_database):
    m = models(with_kinship=False)
    n, f = await family(m)
    await run_pending_derivations()
    (made,) = (await derived(m)).values()
    with pytest.raises(PanglossDerivedDocumentError):
        await m.DerivedFactoid.delete(made.id)
    with pytest.raises(PanglossDerivedDocumentError):
        await m.DerivedFactoid.Update(
            id=made.id, label="Mine", sources=[], statements=[]
        ).save()
    # (and its sources are free: changed and deleted with nothing asked)
    await change_statement(m, f.A.id, 0, label="changed")
    await m.Factoid.delete(f.B.id)
    await run_pending_derivations()
    assert await derived(m) == {}


# ---------------------------------------------------------------------------
# An entity that only derived documents name
# ---------------------------------------------------------------------------


@no_type_check
async def test_what_a_derived_document_names_is_not_referred_to_by_it(clear_database):
    m = models(with_kinship=False)
    n, f = await family(m)
    await run_pending_derivations()
    assert len(await derived(m)) == 1
    operations = storage_of().operations
    # (A is named by one factoid and one derived factoid: one use)
    counted = (await m.Person.list(use_counts=True)).use_counts
    assert counted[str(n.A.id)] == 1 and counted[str(n.P.id)] == 2
    assert len((await m.Person.list(used_only=True)).results) == 3
    # (the factoids gone, and the worker not yet run: the derived factoid still names A, and A can be deleted)
    await m.Factoid.delete(f.A.id)
    check = await operations.check_deletable(m.Person, n.A.id)
    assert check.deletable
    await m.Person.delete(n.A.id)
    await run_pending_derivations()
    assert await derived(m) == {}


# ---------------------------------------------------------------------------
# Citing one
# ---------------------------------------------------------------------------


@no_type_check
async def test_a_citation_of_a_derived_document_is_of_what_it_rests_on(clear_database):
    m = models()
    n, f = await family(m)
    await run_pending_derivations()
    (sibling,) = (await derived(m)).values()
    (kin,) = (await derived(m, "kinship")).values()
    child_of_a = (await m.Factoid.get(f.A.id)).statements[0]
    child_of_b = (await m.Factoid.get(f.B.id)).statements[0]

    note = await m.Note.Create(
        label="Note",
        evidence=[
            # (the document, a statement inside it, and one that rests on it in turn)
            {"type": "DerivedFactoid", "id": sibling.id},
            {"type": "Sibling", "id": sibling.statements[0].id},
            {"type": "Kin", "id": kin.statements[0].id},
        ],
    ).save()
    read_back = await m.Note.get(note.id)
    assert [e.type for e in read_back.evidence] == ["PGCitedBasis"] * 3
    for basis, via, rule_name, label in zip(
        read_back.evidence,
        (sibling, sibling, kin),
        ("siblings", "siblings", "kinship"),
        ("Siblings", "Siblings", "Kin"),
        strict=True,
    ):
        assert basis.via_id == via.id and basis.via_type == "DerivedFactoid"
        assert basis.via_rule == rule_name and basis.via_label == label
        # (what people wrote, whatever was chosen: through the derived sibling to the two statements)
        assert sorted(str(c.target_id) for c in basis.basis) == sorted(
            [str(child_of_a.id), str(child_of_b.id)]
        )
        assert {c.target_type for c in basis.basis} == {"ChildOf"}
        assert basis.derivation_state == ""
    # (the derived documents are not themselves cited: the worker is free)
    assert (
        await query(
            "MATCH (c:PGCitation) WHERE c.target_head_id IN $ids RETURN c.id AS id",
            ids=[str(sibling.id), str(kin.id)],
        )
        == []
    )

    # (the derivation is lost: marked, on the bases made through each document that went)
    from pangloss_models.citations import acknowledging

    with acknowledging("removals"):
        await m.Factoid.delete(f.B.id)
    await run_pending_derivations()
    assert await derived(m) == {}
    lost = await m.Note.get(note.id)
    assert [e.derivation_state for e in lost.evidence] == ["lost"] * 3
    # (and back: cleared)
    await m.Factoid.undelete(f.B.id)
    await run_pending_derivations()
    back = await m.Note.get(note.id)
    assert [e.derivation_state for e in back.evidence] == [""] * 3


@no_type_check
async def test_a_citation_through_a_document_that_changed_is_marked(clear_database):
    m = models(with_kinship=False)
    n, f = await family(m)
    extra = await people(m, "Z")
    await run_pending_derivations()
    (sibling,) = (await derived(m)).values()
    note = await m.Note.Create(
        label="Note", evidence=[{"type": "DerivedFactoid", "id": sibling.id}]
    ).save()
    from pangloss_models.citations import acknowledging

    with acknowledging(True):
        await change_statement(m, f.B.id, 0, child=ref(extra.Z))
    await run_pending_derivations()
    (changed,) = (await derived(m)).values()
    assert changed.id == sibling.id
    (basis,) = (await m.Note.get(note.id)).evidence
    assert basis.derivation_state == "changed"


@no_type_check
async def test_a_derived_document_that_does_not_hold_is_not_cited(clear_database):
    m = models(with_kinship=False)
    n, f = await family(m)
    await run_pending_derivations()
    (sibling,) = (await derived(m)).values()
    await m.Factoid.delete(f.B.id)
    await run_pending_derivations()
    with pytest.raises(PanglossReferenceError):
        await m.Note.Create(
            label="Note", evidence=[{"type": "DerivedFactoid", "id": sibling.id}]
        ).save()
    with pytest.raises(PanglossReferenceError):
        await m.Note.Create(
            label="Note", evidence=[{"type": "DerivedFactoid", "id": uuid.uuid4()}]
        ).save()


# ---------------------------------------------------------------------------
# In the background, and what is told of it
# ---------------------------------------------------------------------------


@no_type_check
async def test_the_background_worker_writes_documents_on_its_own(clear_database):
    import asyncio
    import time

    from pangloss_models import hooks

    from pangloss_derived.worker import Settings, Worker

    m = models()
    n = await people(m, "ABP")
    background = Worker(Settings(idle=60, documents=1))
    hooks.after_write.append(background.listen)
    hooks.work_marked.append(background.marked)
    task = asyncio.create_task(background.run())

    async def wait_for(condition, what):
        began = time.monotonic()
        while not await condition():
            assert time.monotonic() - began < 10, what
            await asyncio.sleep(0.05)

    try:
        await asyncio.sleep(0.3)  # (it has started: its rules are built)
        created = {}
        for child in "AB":
            created[child] = await m.Factoid.Create(
                label=child, statements=[child_of(n[child], n.P)]
            ).save()

        async def both():
            return len(await derived(m)) == 1 and len(await derived(m, "kinship")) == 1

        # (a write wakes it; the document it writes is a write, which wakes it for the rule that reads it)
        await wait_for(both, "the worker did not write the documents")
        (made,) = (await derived(m)).values()

        async def unpublished():
            return (await head(made.id)).published is False

        # (so does a change of whether a source is published, which is not a write)
        await storage_of().operations.set_published_in_db(
            m.Factoid, created["A"].id, False
        )
        await wait_for(unpublished, "the worker did not follow the source")

        async def gone():
            return (await head(made.id)).deleted

        async def both_gone():
            # (step by step: the derived sibling, then, in a later batch, the kin that rested on it)
            return background.stats.documents.deleted == 2

        await m.Factoid.delete(created["B"].id)
        await wait_for(gone, "the worker did not delete the document")
        await wait_for(both_gone, "the worker did not delete what rested on it")
        assert background.stats.documents.made == 2
        assert await derived(m) == {} == await derived(m, "kinship")
    finally:
        task.cancel()
        hooks.after_write.remove(background.listen)
        hooks.work_marked.remove(background.marked)
        try:
            await task
        except asyncio.CancelledError:
            pass


@no_type_check
async def test_the_status_route_says_what_waits_and_what_was_written(clear_database):
    import httpx2 as httpx
    from pangloss_api import create_app

    m = models(with_kinship=False)
    n, f = await family(m, "ABC")
    await worker.take_lease()
    try:
        await worker.sync_rules()
        extra = await people(m, "D")
        await m.Factoid.Create(label="D", statements=[child_of(extra.D, n.P)]).save()
        await worker.process_batch()
    finally:
        await worker.give_up_lease()
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        status = (await client.get("/api/derived/status")).json()
        assert status["documents"]["written"] == {"siblings": 6}
        # (the three of the new child, to make: no source of the three that are there was written)
        assert status["documents"]["pending"]["pending"] == 3
        assert status["documents"]["retractions"]["pending"] == 0
        assert status["worker"]["documents"]["made"] >= 3
        await run_pending_derivations()
        status = (await client.get("/api/derived/status")).json()
        assert status["documents"]["pending"]["pending"] == 0
        listed = (await client.get("/api/DerivedFactoid?pageSize=50")).json()
        assert listed["count"] == 6
        assert {d["derivedBy"] for d in listed["results"]} == {"siblings"}
        one = (
            await client.get(f"/api/DerivedFactoid/{listed['results'][0]['id']}")
        ).json()
        assert one["sources"][0]["type"] == "PGUnprotectedCitation"
        assert one["sources"][0]["targetType"] == "Factoid"
