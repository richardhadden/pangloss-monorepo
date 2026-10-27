"""The date types stored in Memgraph: written, read back, found by range and ordered"""

import importlib
from typing import no_type_check

import pytest
from pangloss_dates.calendar import Calendar, to_jdn
from pangloss_memgraph.databases.memgraph.initialise_database import (
    initialise_database,
)
from pangloss_models import initialise
from pangloss_models.model_bases.document import Document
from pangloss_models.search import Match

pytestmark = pytest.mark.asyncio(loop_scope="session")

J = Calendar.JULIAN


def day(y, m, d):
    return to_jdn(y, m, d, J)


def models():
    from pangloss_dates import julian, models

    for module in (models, julian):
        importlib.reload(module)

    class Factoid(Document):
        when: julian.JulianDate

    initialise()
    return Factoid


def exact(year, month=None, day=None, **more):
    return {"type": "JulianExactDate", "year": year, "month": month, "day": day, **more}


@no_type_check
async def test_every_kind_is_stored_and_read_back_with_its_bounds(clear_database):
    Factoid = models()
    await initialise_database()
    made = {
        "exact": exact(1500, 3, 2),
        "range": {
            "type": "JulianDateRange",
            "earliest": exact(1500),
            "latest": exact(1502, 3),
        },
        "edtf": {"type": "JulianEDTFDate", "edtf": "1500-02~"},
        "period": {
            "type": "JulianPeriod",
            "start": exact(1500, 3, 2),
            "end": {"type": "JulianOngoingDate"},
        },
        "recurrence": {
            "type": "JulianRecurrence",
            "frequency": "weekly",
            "weekdays": [0],
            "excluded_days": [],
            "start": exact(1505, 3, 2),
            "end": {"type": "JulianOngoingDate"},
        },
    }
    saved = {}
    for name, when in made.items():
        saved[name] = await Factoid.Create(label=name, when=when).save()
    for name, item in saved.items():
        got = await Factoid.get(item.id)
        assert got.when.type == made[name]["type"]
        assert got.when.calendar == "julian"
        assert (
            got.when.earliest_fuzzy
            <= got.when.earliest_strict
            <= got.when.latest_strict
            <= got.when.latest_fuzzy
        )
    assert (await Factoid.get(saved["exact"].id)).when.sort_day == day(1500, 3, 2)
    assert (await Factoid.get(saved["edtf"].id)).when.earliest_fuzzy < day(1500, 2, 1)
    assert (await Factoid.get(saved["period"].id)).when.latest_strict == day(
        1600, 12, 31
    )
    assert (await Factoid.get(saved["range"].id)).when.earliest.year == 1500


@no_type_check
async def test_documents_are_found_by_the_bounds_of_their_date(clear_database):
    Factoid = models()
    await initialise_database()
    for label, year in [("a", 1490), ("b", 1500), ("c", 1510), ("d", 1520)]:
        await Factoid.Create(label=label, when=exact(year, 6, 1)).save()

    async def find(**conditions):
        found = await Factoid.search(Match(where={"when": {"where": conditions}}))
        return sorted(item.label for item in found.results)

    assert await find(sort_day={"between": [day(1495, 1, 1), day(1515, 1, 1)]}) == [
        "b",
        "c",
    ]
    assert await find(earliest_strict={"gte": day(1510, 1, 1)}) == ["c", "d"]
    assert await find(latest_fuzzy={"lt": day(1495, 1, 1)}) == ["a"]
