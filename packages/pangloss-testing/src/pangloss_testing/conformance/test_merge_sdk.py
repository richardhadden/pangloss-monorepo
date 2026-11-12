"""Merging entities with the SDK, against the real API: what its functions give is what the database module gives,
and what they raise is what it raises"""

import dataclasses
from typing import no_type_check

import pytest
from pangloss_api import create_app
from pangloss_core import settings as core_settings
from pangloss_core import storage_of
from pangloss_models import (
    PanglossMergedError,
    PanglossMergeError,
    PanglossMergeNotAllowedError,
    PanglossMergeTooLargeError,
    PanglossVersionConflictError,
)
from pangloss_sdk.databases.api import exposed_functions as sdk
from pangloss_sdk.exceptions import (
    PanglossMergedIntoOtherClass,
    PanglossPermissionError,
)

from .merge_support import declare, make, merged_into, person, ref
from .test_sdk_contract import sdk_for, through_the_api  # noqa: F401

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def anyone_merges(monkeypatch):
    monkeypatch.setattr(core_settings.SETTINGS, "MERGE_DIRECTLY", "any")


@no_type_check
async def test_a_merge_through_the_sdk_gives_what_the_database_module_gives(
    db_driver,
    through_the_api,  # noqa: F811
    anyone_merges,
):
    m = declare()
    await through_the_api(create_app())
    a = await person(m, "John Smith", born=1800)
    b = await person(m, "Jon Smyth", died=1870)
    c = await person(m, "J. Smith")
    mention = await make(m.Mention, "Of B", of=ref(b), others=[ref(a), ref(b)])

    # the preview is the same either way
    directly = await m.Person.merge_preview(absorb=b.id, into=a.id)
    through = await sdk.preview_merge(m.Person, b.id, a.id)
    assert through == directly
    assert through.possible and through.values["died"] == 1870
    assert [h.id for h in through.collapsed] == [mention.id]

    result = await sdk.merge_entities(
        m.Person, b.id, a.id, version_into=1, version_absorb=1
    )
    assert result.merge.state == "done" and result.merge.by == "sdkuser"
    assert [h.id for h in result.collapsed] == [mention.id]
    assert merged_into(db_driver, b.id) == str(a.id)
    assert result.merge == await storage_of().operations.get_merge(result.merge.id)
    assert await sdk.merges_of_entity(m.Person, a.id) == await m.Person.merges(a.id)
    assert await sdk.get_merge(result.merge.id) == result.merge

    # the fields may be given as an `Update`, or as what one takes
    edit = await m.Person.get_for_edit(a.id)
    update = m.Person.Update(
        **{**edit.model_dump(exclude={"meta"}), "label": "John Smith the elder"}
    )
    second = await sdk.merge_entities(m.Person, c.id, a.id, values=update)
    assert (await m.Person.get(a.id)).label == "John Smith the elder"

    dry = await sdk.unmerge_entities(m.Person, second.merge.id, dry_run=True)
    assert dry.merge.state == "undone" and merged_into(db_driver, c.id) == str(a.id)
    undone = await sdk.unmerge_entities(m.Person, second.merge.id)
    assert merged_into(db_driver, c.id) is None
    # (another merge into the survivor stands: its fields as they were are a draft, with the keys of Python)
    assert not undone.fields_restored
    assert undone.draft["label"] == "John Smith" and undone.draft_type == "Person"
    assert undone.draft["aliases"] == ["Jon Smyth"]
    first = await sdk.unmerge_entities(m.Person, result.merge.id)
    assert dataclasses.asdict(first)["restored"] == 2
    assert (await m.Mention.get(mention.id)).of.id == b.id


@no_type_check
async def test_what_a_merge_raises_is_raised_through_the_sdk(
    db_driver,
    through_the_api,  # noqa: F811
    monkeypatch,
):
    m = declare()
    await through_the_api(create_app())
    a, b = await person(m, "A"), await person(m, "B")
    for index in range(3):
        await make(m.Mention, f"Of B {index}", of=ref(b))

    # not for this user, in a project where admins merge
    with pytest.raises(PanglossPermissionError, match="propose"):
        await sdk.merge_entities(m.Person, b.id, a.id)
    monkeypatch.setattr(core_settings.SETTINGS, "MERGE_DIRECTLY", "any")
    with pytest.raises(PanglossMergeError, match="into itself"):
        await sdk.merge_entities(m.Person, a.id, a.id)
    with pytest.raises(PanglossVersionConflictError) as conflict:
        await sdk.merge_entities(m.Person, b.id, a.id, version_into=5)
    assert conflict.value.current_version == 1
    monkeypatch.setattr(core_settings.SETTINGS, "MERGE_LIMIT", 2)
    with pytest.raises(PanglossMergeTooLargeError) as too_large:
        await sdk.merge_entities(m.Person, b.id, a.id)
    assert (too_large.value.heads, too_large.value.limit) == (3, 2)
    monkeypatch.setattr(core_settings.SETTINGS, "MERGE_LIMIT", 1000)

    await sdk.merge_entities(m.Person, b.id, a.id)
    # a write to what was merged names the survivor
    edit = await m.Person.get_for_edit(a.id)
    update = m.Person.Update(**{**edit.model_dump(exclude={"meta"}), "id": b.id})
    with pytest.raises(PanglossMergedError) as merged:
        await sdk.update_head_node(update, expected_version=1)
    assert str(merged.value.merged_into) == str(a.id)


@no_type_check
async def test_proposing_and_verifying_through_the_sdk(
    db_driver,
    through_the_api,  # noqa: F811
):
    m = declare()
    app = create_app()
    await through_the_api(app)
    a, b = await person(m, "A"), await person(m, "B")

    proposal = await sdk.propose_merge(m.Person, b.id, a.id, note="one man")
    assert (proposal.state, proposal.proposed_by, proposal.note) == (
        "proposed",
        "sdkuser",
        "one man",
    )
    assert proposal == await storage_of().operations.get_merge(proposal.id)
    waiting, count = await sdk.list_merges(states=["proposed"], undo_proposed=True)
    assert [x.id for x in waiting] == [proposal.id] and count == 1
    with pytest.raises(PanglossMergeNotAllowedError):
        await sdk.verify_merge(proposal.id)
    assert merged_into(db_driver, b.id) is None

    # another user verifies it
    other = await sdk_for(app, "second")
    try:
        result = await sdk.verify_merge(proposal.id)
        assert (result.merge.proposed_by, result.merge.by) == ("sdkuser", "second")
        asked = await sdk.propose_unmerge(result.merge.id, "two men")
        assert asked.undo_proposed_by == "second"
        with pytest.raises(PanglossMergeNotAllowedError):
            await sdk.unmerge_entities(m.Person, result.merge.id)
        kept = await sdk.reject_unmerge(result.merge.id, "one man")
        assert kept.undo_rejected_reason == "one man"
    finally:
        await other.close()
    assert merged_into(db_driver, b.id) == str(a.id)


@no_type_check
async def test_reading_an_entity_merged_into_one_of_another_class_through_the_sdk(
    db_driver,
    through_the_api,  # noqa: F811
):
    m = declare()
    await through_the_api(create_app())
    a = await person(m, "A")
    poet = await make(m.Poet, "A poet", works=["Odes"])
    other = await make(m.Poet, "Another poet")
    await m.Person.merge(absorb=poet.id, into=a.id, as_class=m.Person)
    await m.Person.merge(absorb=other.id, into=a.id, as_class=m.Person)

    # by a class the survivor is of: the survivor, marked
    found = await sdk.get_entity(m.Person, poet.id)
    assert found.id == a.id and found.meta.merged_from == [poet.id]
    # by the class it was, which the survivor is not: said, with the reference to the survivor (decision 27)
    with pytest.raises(PanglossMergedIntoOtherClass) as elsewhere:
        await sdk.get_entity(m.Poet, poet.id)
    assert elsewhere.value.reference == {
        "id": str(a.id),
        "type": "Person",
        "label": "A",
    }
