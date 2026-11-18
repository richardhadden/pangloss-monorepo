"""Why a version of an entity cannot be put back while a merge it is part of stands (`restore.merged_problems`), with
no database: the merges are given by the class"""

import asyncio
import datetime
from uuid import uuid7

from pangloss_history.restore import merged_problems
from pangloss_models import Document, Entity, PanglossServerOnly
from pangloss_models.merging import MergeRecord

ME, OTHER, SURVIVOR = uuid7(), uuid7(), uuid7()
WHEN = datetime.datetime(2026, 3, 4, 5, 6, tzinfo=datetime.UTC)


def person_with(*merges):
    class Person(Entity):
        pass

    async def given(cls, id):
        assert id == ME
        return list(merges)

    # (what the storage would give: `Entity.merges`)
    setattr(Person, "merges", classmethod(given))  # noqa: B010  (assigned, ty refuses it as an override)
    return Person


def merge(**fields):
    return MergeRecord(
        **{"id": uuid7(), "survivor": ME, "absorbed": OTHER, "state": "done", **fields}
    )


def problems(model, version):
    return asyncio.run(merged_problems(model, ME, version))


def test_a_version_of_an_entity_absorbed_by_a_merge_that_stands_cannot_be_put_back():
    absorbed = merge(survivor=SURVIVOR, absorbed=ME, survivor_type="Person", when=WHEN)
    assert problems(person_with(absorbed), 1) == [
        {
            "kind": "merged",
            "message": f"This Person was merged into Person {SURVIVOR} on 2026-03-04: undo the merge, and then a "
            "version of it can be put back",
            "merge": str(absorbed.id),
        }
    ]


def test_a_version_from_before_the_entity_absorbed_another_cannot_be_put_back_and_one_after_can():
    absorbing = merge(survivor_version=5, absorbed_label="Jon")
    later = merge(survivor_version=2, absorbed_label=None, when=WHEN)
    model = person_with(absorbing, later)
    assert problems(model, 4) == [
        {
            "kind": "merged",
            "message": "Version 4 is from before this Person absorbed Jon (its version 5): undo the merge, and then "
            "a version from before it can be put back",
            "merge": str(absorbing.id),
        }
    ]
    assert problems(model, 1)[1]["message"] == (
        f"Version 1 is from before this Person absorbed {OTHER} on 2026-03-04 (its version 2): undo the merge, "
        "and then a version from before it can be put back"
    )
    # (the version the merge made, and those after it, may be put back)
    assert problems(model, 5) == []


def test_merges_that_do_not_stand_and_what_is_not_an_entity_have_nothing_to_say():
    undone = merge(state="undone", absorbed=ME, survivor=SURVIVOR)
    proposed = merge(state="proposed", survivor_version=9)
    running = merge(state="running", survivor_version=9)
    assert [
        p["merge"] for p in problems(person_with(undone, proposed, running), 1)
    ] == [str(running.id)]

    class Note(Document):
        pass

    assert problems(Note, 1) == []

    class Remote(Entity):
        pass

    def refuse(cls, id):
        raise PanglossServerOnly("not here")

    setattr(Remote, "merges", classmethod(refuse))  # noqa: B010

    assert problems(Remote, 1) == []
