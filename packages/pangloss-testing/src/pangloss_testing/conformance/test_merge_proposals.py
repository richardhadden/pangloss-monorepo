"""A merge that one user proposes and another verifies, and the same for undoing one (implementation_docs/entity-identity.md,
"Proposing and verifying a merge")"""

import asyncio
import contextlib
from typing import no_type_check

import pytest
from pangloss_core import storage_of
from pangloss_models import (
    PanglossMergeError,
    PanglossMergeNotAllowedError,
    PanglossVersionConflictError,
)
from pangloss_users import current_request_username, service

from .helpers import run
from .merge_support import declare, edges_to, make, merged_into, person, ref

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"


def ops():
    return storage_of().operations


@contextlib.contextmanager
def as_user(username: str):
    token = current_request_username.set(username)
    try:
        yield
    finally:
        current_request_username.reset(token)


async def two_users() -> None:
    for name in ("ann", "bob"):
        await service.create_user(name, f"{name}@example.com", PASSWORD)


@no_type_check
async def test_a_proposal_writes_nothing_but_its_record(db_driver, clear_database):
    m = declare()
    await two_users()
    a = await person(m, "John Smith", born=1800)
    b = await person(m, "Jon Smyth", died=1870)
    mention = await make(m.Mention, "Of B", of=ref(b))

    with as_user("ann"):
        proposal = await m.Person.propose_merge(
            absorb=b.id, into=a.id, note="same father in two factoids"
        )

    assert proposal.state == "proposed"
    assert (proposal.proposed_by, proposal.note) == (
        "ann",
        "same father in two factoids",
    )
    assert (proposal.survivor, proposal.absorbed) == (a.id, b.id)
    assert (proposal.survivor_label, proposal.absorbed_label) == (
        "John Smith",
        "Jon Smyth",
    )
    assert (proposal.survivor_version, proposal.absorbed_version) == (1, 1)
    assert proposal.by is None and proposal.when is None
    # the fields chosen (the defaults here) are kept with it
    assert proposal.values["died"] == 1870 and proposal.values["born"] == 1800
    assert proposal.values["aliases"] == ["Jon Smyth"]
    assert proposal.heads == 1
    # and nothing else is written: B is not marked, its references are its own
    assert merged_into(db_driver, b.id) is None
    assert edges_to(db_driver, b.id) == [("Mention", "of", 0)]
    assert (await m.Mention.get(mention.id)).of.id == b.id
    assert (await m.Person.get(b.id)).id == b.id
    assert [x.id for x in await m.Person.merges(b.id)] == [proposal.id]
    assert (await ops().get_merge(proposal.id)).values == proposal.values


@no_type_check
async def test_a_merge_that_cannot_be_made_is_not_proposed(db_driver, clear_database):
    m = declare()
    a = await person(m, "A")
    group = await make(m.Group, "A group")
    b = await person(m, "B")
    c = await person(m, "C")
    await make(m.Witnessed, "Two witnesses", witnesses=[ref(a), ref(b)])

    with pytest.raises(PanglossMergeError, match="neither is a kind of the other"):
        await m.Entity.propose_merge(absorb=group.id, into=a.id)
    # (the collapse would leave one witness where there must be two)
    with pytest.raises(PanglossMergeError, match="no longer valid"):
        await m.Person.propose_merge(absorb=b.id, into=a.id)
    assert run(db_driver, "MATCH (m:PGMerge) RETURN count(m) AS n")[0]["n"] == 0
    await m.Person.propose_merge(absorb=c.id, into=a.id)


@no_type_check
async def test_another_user_verifies_a_proposal_and_the_merge_is_carried_out(
    db_driver, clear_database
):
    m = declare()
    await two_users()
    a = await person(m, "John Smith")
    b = await person(m, "Jon Smyth")
    mention = await make(m.Mention, "Of B", of=ref(b))
    with as_user("ann"):
        proposal = await m.Person.propose_merge(absorb=b.id, into=a.id, note="one man")

    with as_user("bob"):
        result = await ops().verify_merge(proposal.id)

    # the proposal's own record is the merge's: both people are on it
    assert result.merge.id == proposal.id
    assert result.merge.state == "done"
    assert (result.merge.proposed_by, result.merge.by) == ("ann", "bob")
    assert result.merge.note == "one man"
    assert result.merge.values is None
    assert run(db_driver, "MATCH (m:PGMerge) RETURN count(m) AS n")[0]["n"] == 1
    assert merged_into(db_driver, b.id) == str(a.id)
    assert (await m.Mention.get(mention.id)).of.id == a.id
    assert (await m.Person.get(a.id)).aliases == ["Jon Smyth"]
    # and it is undone as any merge is
    undone = await m.Person.unmerge(proposal.id)
    assert undone.merge.state == "undone" and undone.restored == 1
    assert (await m.Mention.get(mention.id)).of.id == b.id


@no_type_check
async def test_the_one_who_proposed_a_merge_cannot_verify_it(db_driver, clear_database):
    m = declare()
    await two_users()
    a, b = await person(m, "A"), await person(m, "B")
    with as_user("ann"):
        proposal = await m.Person.propose_merge(absorb=b.id, into=a.id)
        with pytest.raises(PanglossMergeNotAllowedError, match="someone other"):
            await ops().verify_merge(proposal.id)
    assert merged_into(db_driver, b.id) is None
    assert (await ops().get_merge(proposal.id)).state == "proposed"


@no_type_check
async def test_the_verifier_may_change_the_fields_chosen(db_driver, clear_database):
    m = declare()
    await two_users()
    a = await person(m, "John Smith", born=1800)
    b = await person(m, "Jon Smyth", born=1801)
    with as_user("ann"):
        proposal = await m.Person.propose_merge(absorb=b.id, into=a.id)
    assert proposal.values["born"] == 1800

    with as_user("bob"):
        await ops().verify_merge(
            proposal.id,
            values={**proposal.values, "born": 1801, "label": "Jon Smyth"},
            version_into=1,
            version_absorb=1,
        )
    after = await m.Person.get(a.id)
    assert (after.label, after.born) == ("Jon Smyth", 1801)


@no_type_check
async def test_a_proposal_whose_entity_changed_since_is_not_carried_out_as_it_was(
    db_driver, clear_database
):
    m = declare()
    await two_users()
    a = await person(m, "John Smith", born=1800)
    b = await person(m, "Jon Smyth")
    with as_user("ann"):
        proposal = await m.Person.propose_merge(absorb=b.id, into=a.id)
    # A is corrected after the proposal: the fields proposed would undo the correction
    edit = await m.Person.get_for_edit(a.id)
    await m.Person.Update(**{**edit.model_dump(exclude={"meta"}), "born": 1799}).save()

    with as_user("bob"):
        with pytest.raises(PanglossVersionConflictError):
            await ops().verify_merge(proposal.id)
        assert merged_into(db_driver, b.id) is None
        assert (await ops().get_merge(proposal.id)).state == "proposed"
        # looked at again, with the fields as they are now, it is carried out
        preview = await m.Person.merge_preview(absorb=b.id, into=a.id)
        result = await ops().verify_merge(
            proposal.id, values=preview.values, version_into=2, version_absorb=1
        )
    assert result.merge.state == "done"
    assert (await m.Person.get(a.id)).born == 1799


@no_type_check
async def test_a_merge_is_checked_again_when_it_is_verified(db_driver, clear_database):
    m = declare()
    await two_users()
    a, b, c = await person(m, "A"), await person(m, "B"), await person(m, "C")
    with as_user("ann"):
        proposal = await m.Person.propose_merge(absorb=b.id, into=a.id)
    # made since: a document that must name two, and would name one
    await make(m.Witnessed, "Two witnesses", witnesses=[ref(a), ref(b)])

    with as_user("bob"):
        with pytest.raises(PanglossMergeError, match="no longer valid"):
            await ops().verify_merge(proposal.id)
    assert merged_into(db_driver, b.id) is None
    record = await ops().get_merge(proposal.id)
    # (it stays open: the document can be changed, and the proposal verified then)
    assert record.state == "proposed" and record.by is None
    assert c.id


@no_type_check
async def test_a_rejected_proposal_is_kept_and_cannot_be_verified(
    db_driver, clear_database
):
    m = declare()
    await two_users()
    a, b = await person(m, "A"), await person(m, "B")
    with as_user("ann"):
        proposal = await m.Person.propose_merge(absorb=b.id, into=a.id)
    with as_user("bob"):
        rejected = await ops().reject_merge(proposal.id, "different fathers")
        assert (rejected.state, rejected.rejected_by, rejected.reason) == (
            "rejected",
            "bob",
            "different fathers",
        )
        assert rejected.rejected_when is not None
        with pytest.raises(PanglossMergeError, match="rejected, not proposed"):
            await ops().verify_merge(proposal.id)
        with pytest.raises(PanglossMergeError, match="rejected, not proposed"):
            await ops().reject_merge(proposal.id)
    assert merged_into(db_driver, b.id) is None
    # (the fields that were proposed are still there to read)
    assert (await ops().get_merge(proposal.id)).values is not None


@no_type_check
async def test_proposals_about_an_entity_that_is_merged_are_stale(
    db_driver, clear_database
):
    m = declare()
    await two_users()
    a, b, c, d = [await person(m, name) for name in "ABCD"]
    with as_user("ann"):
        b_into_a = await m.Person.propose_merge(absorb=b.id, into=a.id)
        b_into_c = await m.Person.propose_merge(absorb=b.id, into=c.id)
        d_into_b = await m.Person.propose_merge(absorb=d.id, into=b.id)
        d_into_a = await m.Person.propose_merge(absorb=d.id, into=a.id)

    with as_user("bob"):
        await ops().verify_merge(b_into_a.id)
        states = {
            name: await ops().get_merge(merge.id)
            for name, merge in (
                ("b_into_c", b_into_c),
                ("d_into_b", d_into_b),
                ("d_into_a", d_into_a),
            )
        }
        # those that involve B, which is merged now, say why they cannot be made; the one about A stands
        assert states["b_into_c"].state == "stale"
        assert states["d_into_b"].state == "stale"
        assert "B was merged into another entity" in states["b_into_c"].reason
        assert states["d_into_a"].state == "proposed"
        with pytest.raises(PanglossMergeError, match="stale"):
            await ops().verify_merge(b_into_c.id)
        # (A has changed, by absorbing B: the fields proposed for it are looked at again)
        with pytest.raises(PanglossVersionConflictError):
            await ops().verify_merge(d_into_a.id)
        preview = await m.Person.merge_preview(absorb=d.id, into=a.id)
        await ops().verify_merge(
            d_into_a.id, values=preview.values, version_into=2, version_absorb=1
        )
    assert merged_into(db_driver, d.id) == str(a.id)
    assert (await m.Person.get(a.id)).aliases == ["B", "D"]


@no_type_check
async def test_a_merge_made_directly_overtakes_the_proposals_about_what_it_absorbed(
    db_driver, clear_database
):
    m = declare()
    await two_users()
    a, b, c = [await person(m, name) for name in "ABC"]
    with as_user("ann"):
        proposal = await m.Person.propose_merge(absorb=b.id, into=c.id)
    await m.Person.merge(absorb=b.id, into=a.id)
    assert (await ops().get_merge(proposal.id)).state == "stale"
    # a preview of a merge, which is rolled back, overtakes nothing
    with as_user("ann"):
        other = await m.Person.propose_merge(absorb=c.id, into=a.id)
    await m.Person.merge_preview(absorb=c.id, into=a.id)
    assert (await ops().get_merge(other.id)).state == "proposed"


@no_type_check
async def test_a_proposal_from_before_a_migration_is_stale(db_driver, clear_database):
    m = declare()
    await two_users()
    a, b = await person(m, "A"), await person(m, "B")
    with as_user("ann"):
        proposal = await m.Person.propose_merge(absorb=b.id, into=a.id)
    run(
        db_driver,
        "CREATE (:PGMigration {app: 'people', name: '0002_changed', status: 'applied'})",
    )
    with as_user("bob"):
        with pytest.raises(PanglossMergeError, match="migrated since it was proposed"):
            await ops().verify_merge(proposal.id)
    record = await ops().get_merge(proposal.id)
    assert record.state == "stale" and "migrated" in record.reason
    assert merged_into(db_driver, b.id) is None


@no_type_check
async def test_of_two_who_verify_a_proposal_at_once_one_carries_it_out(
    db_driver, clear_database
):
    m = declare()
    await two_users()
    await service.create_user("cat", "cat@example.com", PASSWORD)
    a, b = await person(m, "A"), await person(m, "B")
    for index in range(5):
        await make(m.Mention, f"Of B {index}", of=ref(b))
    with as_user("ann"):
        proposal = await m.Person.propose_merge(absorb=b.id, into=a.id)

    async def verify(who: str):
        with as_user(who):
            return await ops().verify_merge(proposal.id)

    results = await asyncio.gather(verify("bob"), verify("cat"), return_exceptions=True)
    done = [r for r in results if not isinstance(r, Exception)]
    refused = [r for r in results if isinstance(r, Exception)]
    assert len(done) == 1 and len(refused) == 1, results
    assert isinstance(refused[0], PanglossMergeError)
    assert run(db_driver, "MATCH (m:PGMerge) RETURN count(m) AS n")[0]["n"] == 1
    record = await ops().get_merge(proposal.id)
    assert record.state == "done" and record.by in ("bob", "cat")
    assert record.moved == 5
    assert (
        run(
            db_driver,
            "MATCH (move:PGMergeMove {pg_merge: $id}) RETURN count(move) AS n",
            id=str(proposal.id),
        )[0]["n"]
        == 5
    )


@no_type_check
async def test_an_undo_is_proposed_by_one_user_and_accepted_by_another(
    db_driver, clear_database
):
    m = declare()
    await two_users()
    a, b = await person(m, "A"), await person(m, "B")
    mention = await make(m.Mention, "Of B", of=ref(b))
    merge = (await m.Person.merge(absorb=b.id, into=a.id)).merge

    # nobody has proposed it: one who may not undo alone is refused
    with as_user("ann"):
        with pytest.raises(PanglossMergeNotAllowedError, match="Nobody has proposed"):
            await m.Person.unmerge(merge.id, accepting=True)
        proposed = await ops().propose_unmerge(merge.id, "they are two men")
        assert (proposed.state, proposed.undo_proposed_by, proposed.undo_note) == (
            "done",
            "ann",
            "they are two men",
        )
        assert proposed.undo_proposed_when is not None
        # the merge stands meanwhile
        assert merged_into(db_driver, b.id) == str(a.id)
        with pytest.raises(PanglossMergeNotAllowedError, match="someone other"):
            await m.Person.unmerge(merge.id, accepting=True)
        # (what it would do can be asked by anyone)
        assert (await m.Person.unmerge(merge.id, accepting=True, dry_run=True)).restored
    with as_user("bob"):
        undone = await m.Person.unmerge(merge.id, accepting=True)
    assert undone.merge.state == "undone"
    assert (undone.merge.undone_by, undone.merge.undo_proposed_by) == ("bob", "ann")
    assert merged_into(db_driver, b.id) is None
    assert (await m.Mention.get(mention.id)).of.id == b.id


@no_type_check
async def test_a_proposed_undo_can_be_rejected_and_the_merge_stands(
    db_driver, clear_database
):
    m = declare()
    await two_users()
    a, b = await person(m, "A"), await person(m, "B")
    merge = (await m.Person.merge(absorb=b.id, into=a.id)).merge
    with as_user("bob"):
        with pytest.raises(PanglossMergeError, match="Nobody has proposed"):
            await ops().reject_unmerge(merge.id)
    with as_user("ann"):
        await ops().propose_unmerge(merge.id)
    with as_user("bob"):
        rejected = await ops().reject_unmerge(merge.id, "they are one")
    assert rejected.state == "done" and rejected.undo_proposed_by is None
    assert (rejected.undo_rejected_by, rejected.undo_rejected_reason) == (
        "bob",
        "they are one",
    )
    assert merged_into(db_driver, b.id) == str(a.id)
    with as_user("bob"):
        with pytest.raises(PanglossMergeNotAllowedError):
            await m.Person.unmerge(merge.id, accepting=True)
    # it can be proposed again
    with as_user("ann"):
        again = await ops().propose_unmerge(merge.id)
    assert again.undo_proposed_by == "ann" and again.undo_rejected_by is None


@no_type_check
async def test_an_undo_that_cannot_be_made_is_not_proposed(db_driver, clear_database):
    m = declare()
    a, b, d = await person(m, "A"), await person(m, "B"), await person(m, "D")
    first = (await m.Person.merge(absorb=b.id, into=a.id)).merge
    second = (await m.Person.merge(absorb=a.id, into=d.id)).merge
    with pytest.raises(PanglossMergeError, match="undo that merge first"):
        await ops().propose_unmerge(first.id)
    assert (await ops().get_merge(first.id)).undo_proposed_by is None
    await m.Person.unmerge(second.id)
    await m.Person.unmerge(first.id)
    with pytest.raises(PanglossMergeError, match="undone"):
        await ops().propose_unmerge(first.id)


@no_type_check
async def test_the_merges_are_listed_by_state_the_latest_first(
    db_driver, clear_database
):
    m = declare()
    await two_users()
    people = [await person(m, name) for name in "ABCDEFGH"]
    a, b, c, d, e, f, g, h = people
    with as_user("ann"):
        open_one = await m.Person.propose_merge(absorb=b.id, into=a.id)
        rejected = await m.Person.propose_merge(absorb=d.id, into=c.id)
    with as_user("bob"):
        await ops().reject_merge(rejected.id)
    done = (await m.Person.merge(absorb=f.id, into=e.id)).merge
    undo_asked = (await m.Person.merge(absorb=h.id, into=g.id)).merge
    with as_user("ann"):
        await ops().propose_unmerge(undo_asked.id)

    everything, total = await ops().list_merges()
    assert total == 4
    assert [x.id for x in everything] == [
        undo_asked.id,
        done.id,
        rejected.id,
        open_one.id,
    ]
    waiting, total = await ops().list_merges(states=["proposed"], undo_proposed=True)
    assert [x.id for x in waiting] == [undo_asked.id, open_one.id] and total == 2
    carried_out, total = await ops().list_merges(states=["done"])
    assert [x.id for x in carried_out] == [undo_asked.id, done.id]
    page, total = await ops().list_merges(skip=1, limit=2)
    assert [x.id for x in page] == [done.id, rejected.id] and total == 4
    assert await ops().list_merges(states=["undone"]) == ([], 0)
