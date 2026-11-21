"""What leaves work for the vectors' worker (implementation_docs/similarity-build-plan.md, step 5.1), on the backend
under test: each write of the list leaves exactly one mark of the kind `vectors` (`PGPending`) for each head it
should, and none for the others: a create, an update (whose mark keeps the entity it dropped and the documents nested
in it before), a delete, an undelete, a publish, a merge and its undo, and the criteria worker's writing of
candidates (`set_computed`). Nothing is marked when the app is not installed; and what the mark costs a save."""

from typing import no_type_check

import pytest
from pangloss_cypher import pending
from pangloss_testing.live import run
from pangloss_users import current_request_username

pytestmark = pytest.mark.asyncio(loop_scope="session")

KIND = "vectors"

# (the apps `pangloss_testing.similar_models` is declared with, and this one)
SIMILAR_APPS = [
    "pangloss_derived",
    "pangloss_library",
    "pangloss_criteria",
    "pangloss_vectors",
]


@pytest.fixture
def similar(settings, monkeypatch, clear_database):
    """`similar_models` declared, with its apps installed (and `pangloss_review` with `reviewed`)"""
    for app in ("pangloss_criteria", "pangloss_derived", "pangloss_library"):
        pytest.importorskip(app)
    from pangloss_testing.similar_models import declare

    def declared(reviewed: bool = False):
        apps = SIMILAR_APPS + (["pangloss_review"] if reviewed else [])
        monkeypatch.setattr(settings, "INSTALLED_APPS", apps)
        return declare(reviewed=reviewed)

    return declared


def marks(db_driver) -> dict[str, int]:
    """The heads marked for the vectors' worker, with how many marks each has"""
    found: dict[str, int] = {}
    for row in run(
        db_driver,
        "MATCH (p:PGPending {kind: $kind}) RETURN p.head_id AS head",
        kind=KIND,
    ):
        found[row["head"]] = found.get(row["head"], 0) + 1
    return found


def before_refs(db_driver, head_id) -> set[str]:
    rows = run(
        db_driver,
        "MATCH (p:PGPending {key: $key}) RETURN p.before_refs AS refs",
        key=pending.key_of(KIND, str(head_id)),
    )
    assert len(rows) == 1
    return set(rows[0]["refs"] or [])


def forget(db_driver) -> None:
    """The marks of the vectors' worker taken off (those of the other workers left)"""
    run(db_driver, "MATCH (p:PGPending {kind: $kind}) DETACH DELETE p", kind=KIND)


def once_each(*ids) -> dict[str, int]:
    return {str(i): 1 for i in ids}


def ref(item, kind: str = "Person") -> dict:
    return {"type": kind, "id": str(item.id)}


def transfer(by, to) -> dict:
    return {
        "type": "Transfer",
        "label": "A gift",
        "given_by": ref(by),
        "given_to": ref(to),
    }


@no_type_check
async def people(m, *names):
    return [await m.Person.Create(label=name).save() for name in names]


@no_type_check
async def test_a_create_marks_the_head_written(similar, db_driver):
    m = similar()
    ada, ben = await people(m, "Ada", "Ben")
    assert marks(db_driver) == once_each(ada.id, ben.id)
    forget(db_driver)
    made = await m.Factoid.Create(label="gift", statements=[transfer(ada, ben)]).save()
    assert marks(db_driver) == once_each(made.id)


@no_type_check
async def test_an_update_marks_the_head_and_keeps_the_entity_it_dropped_and_its_nested_documents_of_before(
    similar, db_driver
):
    m = similar()
    ada, ben, cy = await people(m, "Ada", "Ben", "Cy")
    made = await m.Factoid.Create(label="gift", statements=[transfer(ada, ben)]).save()
    old = (await m.Factoid.get(made.id)).statements[0].id
    forget(db_driver)
    await m.Factoid.Update(
        id=made.id, label="gift", statements=[transfer(ada, cy)]
    ).save()
    assert marks(db_driver) == once_each(made.id)
    kept = before_refs(db_driver, made.id)
    assert {str(ben.id), str(old)} <= kept
    # (and written twice before it is claimed: still one mark, which keeps both befores)
    new = (await m.Factoid.get(made.id)).statements[0].id
    await m.Factoid.Update(
        id=made.id, label="gift", statements=[transfer(ben, ada)]
    ).save()
    assert marks(db_driver) == once_each(made.id)
    assert {str(ben.id), str(cy.id), str(old), str(new)} <= before_refs(
        db_driver, made.id
    )


@no_type_check
async def test_a_delete_and_an_undelete_mark_the_head(similar, db_driver):
    m = similar()
    ada, ben = await people(m, "Ada", "Ben")
    made = await m.Factoid.Create(label="gift", statements=[transfer(ada, ben)]).save()
    forget(db_driver)
    await m.Factoid.delete(made.id)
    assert marks(db_driver) == once_each(made.id)
    forget(db_driver)
    await m.Factoid.undelete(made.id)
    assert marks(db_driver) == once_each(made.id)


@no_type_check
async def test_a_publish_and_an_unpublish_mark_the_document(similar, db_driver):
    pytest.importorskip("pangloss_review")
    from pangloss_review.service import set_status
    from pangloss_review.status import ReviewStatus

    m = similar(reviewed=True)
    ada, ben = await people(m, "Ada", "Ben")
    made = await m.Factoid.Create(label="gift", statements=[transfer(ada, ben)]).save()
    forget(db_driver)
    user = current_request_username.get()
    await set_status(made.id, ReviewStatus.PUBLISHED, user)
    assert marks(db_driver) == once_each(made.id)
    forget(db_driver)
    await set_status(made.id, ReviewStatus.UNCHECKED, user)
    assert marks(db_driver) == once_each(made.id)


@no_type_check
async def test_a_merge_and_its_undo_mark_the_survivor_the_absorbed_and_the_documents_moved(
    similar, db_driver
):
    from pangloss_cypher.merge import settle_second_passes

    m = similar()
    ada, dee, eve = await people(m, "Ada", "Dee", "Eve")
    to_eve = await m.Factoid.Create(
        label="to Eve", statements=[transfer(ada, eve)]
    ).save()
    to_dee = await m.Factoid.Create(
        label="to Dee", statements=[transfer(ada, dee)]
    ).save()
    forget(db_driver)
    merged = await m.Person.merge(absorb=eve.id, into=dee.id)
    await settle_second_passes()
    # (what named Dee is not changed by the merge: only what named Eve moved)
    assert marks(db_driver) == once_each(dee.id, eve.id, to_eve.id)
    assert str(to_dee.id) not in marks(db_driver)
    forget(db_driver)
    await m.Person.unmerge(merged.merge.id)
    await settle_second_passes()
    assert marks(db_driver) == once_each(dee.id, eve.id, to_eve.id)


@no_type_check
async def test_the_criteria_worker_writing_candidates_marks_the_head_of_the_description(
    similar, db_driver
):
    from pangloss_criteria import run_pending

    m = similar()
    (ada,) = await people(m, "Ada")
    guild = await m.Group.Create(label="The guild").save()
    fay, gus = await people(m, "Fay", "Gus")
    members = await m.Factoid.Create(
        label="members",
        statements=[
            {
                "type": "MemberOf",
                "label": f"{person.label} of the guild",
                "member": ref(person),
                "group": ref(guild, "Group"),
            }
            for person in (fay, gus)
        ],
    ).save()
    gift = await m.Factoid.Create(
        label="member gift",
        statements=[
            {
                "type": "Transfer",
                "label": "A member gave to Ada",
                "given_by": {
                    "type": "MatchesCriteria",
                    "wording": "a member of the guild",
                    "criteria": {
                        "type": "Person",
                        "where": {
                            "$incoming": [
                                {
                                    "type": "MemberOf",
                                    "field": "member",
                                    "where": {"group": {"is": str(guild.id)}},
                                }
                            ]
                        },
                    },
                },
                "given_to": ref(ada),
            }
        ],
    ).save()
    assert str(members.id) in marks(db_driver)
    forget(db_driver)
    # (the criteria worker evaluates the description in the gift, and writes what it finds with `set_computed`, which
    # marks every kind but its own)
    await run_pending()
    candidates = run(
        db_driver,
        "MATCH (:Factoid {id: $id})-[:statements]->()-[:given_by]->(d)-[e:target]->(p) "
        "WHERE NOT coalesce(e.reverse, false) RETURN p.id AS id",
        id=str(gift.id),
    )
    assert {row["id"] for row in candidates} == {str(fay.id), str(gus.id)}
    assert marks(db_driver) == once_each(gift.id)


@no_type_check
async def test_nothing_is_marked_when_the_app_is_not_installed(
    settings, monkeypatch, db_driver, clear_database
):
    from pangloss_models import Document, Entity, initialise

    monkeypatch.setattr(settings, "INSTALLED_APPS", [])

    class Person(Entity):
        pass

    class Note(Document):
        about: Person

    initialise()
    ada = await Person.Create(label="Ada").save()
    note = await Note.Create(label="A note", about=ref(ada)).save()
    await Note.Update(id=note.id, label="Another", about=ref(ada)).save()
    await Note.delete(note.id)
    assert marks(db_driver) == {}


@no_type_check
async def test_a_class_with_include_false_is_not_marked(
    settings, db_driver, clear_database
):
    from pangloss_models import Document, Entity, initialise
    from pangloss_vectors import VectorsMeta

    class Person(Entity):
        pass

    class Note(Document):
        _vectors_meta = VectorsMeta(include=False)
        about: Person

    initialise()
    ada = await Person.Create(label="Ada").save()
    await Note.Create(label="A note", about=ref(ada)).save()
    assert marks(db_driver) == once_each(ada.id)


# ---------------------------------------------------------------------------
# What the mark costs a write, counted as `conformance/test_query_costs.py` counts
# ---------------------------------------------------------------------------


@no_type_check
async def test_what_the_mark_costs_a_write(settings, monkeypatch, clear_database):
    """With the app installed a create and a delete run one statement more (the mark), and an update three (the old
    tree read, by two queries, and the mark that keeps it); each still in one transaction"""
    from pangloss_testing.conformance.test_query_costs import (
        models,
        recorded,
        statement_of,
    )

    async def costs() -> dict[str, tuple[int, int]]:
        Person, Place, Citation, Statement, Note = models()
        ada = await Person.Create(label="Ada").save()
        places = [await Place.Create(label=f"Place {n}").save() for n in range(3)]
        with recorded() as create:
            big = await statement_of(Statement, ada, places, 20)
        with recorded() as update:
            await Statement.Update(
                id=big.id,
                label="Ada spoke again",
                text="Ada spoke again",
                about={"type": "Person", "id": ada.id},
                at=[{"type": "Place", "id": p.id} for p in places],
                citations=[{"label": "p. 1", "page": 1}],
            ).save(expected_version=1)
        with recorded() as delete:
            await Statement.delete(big.id)
        return {
            name: (r.transactions, len(r.statements))
            for name, r in (("create", create), ("update", update), ("delete", delete))
        }

    monkeypatch.setattr(settings, "INSTALLED_APPS", [])
    without = await costs()
    monkeypatch.setattr(settings, "INSTALLED_APPS", ["pangloss_vectors"])
    with_it = await costs()
    assert {name: (t, n - without[name][1]) for name, (t, n) in with_it.items()} == {
        "create": (1, 1),
        "update": (1, 3),
        "delete": (1, 1),
    }, (without, with_it)
