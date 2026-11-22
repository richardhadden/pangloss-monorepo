"""The suite every part passes (`pangloss_testing.parts.PartSuite`, implementation_docs/similarity-build-plan.md,
step 8.4), called for the class part alone (no other part is registered unless another package's tests imported one:
`pangloss-fastrp`'s call it for the graph part with the class part beside it). The class part's slow way is its own
rebuild: what it would write now. (Its own claims are in `test_vectors_class_part_live.py` and
`test_vectors_worker_live.py`)"""

from pangloss_testing.parts import PartSuite
from pangloss_vectors.class_part import PART


async def class_rebuild(db_driver) -> dict[str, list[float]]:
    """What the class part's rebuild would write now"""
    rows: dict[str, list[float]] = {}

    async def keep(page) -> None:
        rows.update({row.of: list(row.vector) for row in page})

    await PART.rebuild(keep)
    return rows


class TestTheClassPart(PartSuite):
    parts = {"class": class_rebuild}
    tolerance = 1e-8
