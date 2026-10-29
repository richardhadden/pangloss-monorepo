"""The calendar graph in Memgraph: structure by migration, days by seed, feasts by load"""

import pytest
from neo4j.exceptions import ClientError, ConstraintError
from pangloss_calendar import graph
from pangloss_calendar.days import parse_day
from pangloss_calendar.observances import parse
from pangloss_dates.calendar import Calendar, from_jdn, to_jdn
from pangloss_memgraph.databases.memgraph.database import Database
from pangloss_memgraph.databases.memgraph.migrations import apply_changes
from pangloss_models.migrations.files import EMPTY_SNAPSHOT, load

from .helpers import run

pytestmark = pytest.mark.asyncio(loop_scope="session")

J = Calendar.JULIAN
G = Calendar.GREGORIAN

FEASTS = """
[[observance]]
key = "sarum:st-benedict"
use = "sarum"
fixed = { month = 3, day = 21 }

[[observance]]
key = "sarum:pentecost"
use = "sarum"
easter_offset = 49
"""


@pytest.fixture
def clear_calendar(db_driver):
    run(
        db_driver,
        "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'Calendar') DETACH DELETE n",
    )
    yield
    run(
        db_driver,
        "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'Calendar') DETACH DELETE n",
    )


async def structure():
    """The migration of the package, applied (a second time it changes nothing)"""
    migration = load("pangloss_calendar", "0001_initial")
    await apply_changes(Database.default, EMPTY_SNAPSHOT, list(migration.changes))


def count(db_driver, label):
    return run(db_driver, f"MATCH (n:{label}) RETURN count(n) AS c")[0]["c"]


async def test_seeding_twice_makes_the_same_graph(db_driver, clear_calendar):
    await structure()
    first, last = to_jdn(1500, 1, 1, J), to_jdn(1500, 12, 31, J)
    assert (
        await graph.seed(1500, 1500, J) == 366
    )  # (1500 is a leap year in the Julian calendar)
    counts = {
        label: count(db_driver, label)
        for label in ("CalendarDay", "CalendarMonth", "CalendarYear")
    }
    assert counts["CalendarDay"] == 366
    assert (
        counts["CalendarMonth"] == 12 + 13
    )  # (12 Julian, and the Gregorian months that the days touch)
    assert counts["CalendarYear"] == 3  # (Julian 1500, Gregorian 1500 and 1501)
    edges = run(db_driver, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
    assert await graph.seed(1500, 1500, J) == 0
    assert {label: count(db_driver, label) for label in counts} == counts
    assert run(db_driver, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"] == edges
    assert await graph.ensure_range(first, last) == 0


async def test_a_day_has_both_names_and_a_month_in_each_calendar(
    db_driver, clear_calendar
):
    await structure()
    await graph.seed(1500, 1500, J)
    jdn = parse_day("J1500-02-29")
    day = run(db_driver, "MATCH (d:CalendarDay {jdn: $jdn}) RETURN d", jdn=jdn)[0]["d"]
    assert (day["julian_year"], day["julian_month"], day["julian_day"]) == (1500, 2, 29)
    assert (day["gregorian_year"], day["gregorian_month"], day["gregorian_day"]) == (
        1500,
        3,
        10,
    )
    months = run(
        db_driver,
        "MATCH (m:CalendarMonth)-[:CONTAINS]->(:CalendarDay {jdn: $jdn}) RETURN m.calendar AS c, m.month AS m ORDER BY c",
        jdn=jdn,
    )
    assert months == [{"c": "gregorian", "m": 3}, {"c": "julian", "m": 2}]
    nxt = run(
        db_driver,
        "MATCH (:CalendarDay {jdn: $jdn})-[:NEXT]->(n) RETURN n.jdn AS j",
        jdn=jdn,
    )
    assert nxt == [{"j": jdn + 1}]
    julian_months = run(
        db_driver,
        "MATCH (a:CalendarMonth {calendar: 'julian', year: 1500, month: 2})-[:NEXT]->(b) RETURN b.month AS m",
    )
    assert julian_months == [{"m": 3}]
    previous = run(
        db_driver,
        "MATCH (a)-[:NEXT]->(:CalendarMonth {calendar: 'julian', year: 1500, month: 2}) RETURN a.month AS m",
    )
    assert previous == [{"m": 1}]


async def test_days_outside_the_seed_are_made_whole_months_on_demand(
    db_driver, clear_calendar
):
    await structure()
    await graph.seed(1500, 1500, J)
    outside = parse_day("J1502-06-15")
    first, last = (to_jdn(1502, 6, 1, J), to_jdn(1502, 6, 30, J))
    assert await graph.ensure_range(first, last) == 30
    assert (
        run(
            db_driver, "MATCH (d:CalendarDay {jdn: $j}) RETURN count(d) AS c", j=outside
        )[0]["c"]
        == 1
    )
    assert (
        run(
            db_driver,
            "MATCH (:CalendarMonth {calendar: 'julian', year: 1502, month: 6})-[:CONTAINS]->(d) RETURN count(d) AS c",
        )[0]["c"]
        == 30
    )


async def test_a_second_day_with_the_same_number_is_refused(db_driver, clear_calendar):
    await structure()
    await graph.seed(1500, 1500, J)
    with pytest.raises((ConstraintError, ClientError)):
        run(db_driver, "CREATE (:CalendarDay {jdn: $j})", j=parse_day("J1500-03-02"))


async def test_observances_are_linked_to_their_days_and_a_correction_leaves_one_node(
    db_driver, clear_calendar
):
    await structure()
    await graph.seed(1500, 1501, J)
    observances = parse(FEASTS)
    edges = await graph.load_observances(observances, [J])
    assert edges == 4  # two feasts, two years
    benedict = run(
        db_driver,
        "MATCH (:CalendarObservance {key: 'sarum:st-benedict'})-[f:FALLS_ON]->(d) RETURN f.year AS y, d.julian_month AS m, d.julian_day AS d ORDER BY y",
    )
    assert benedict == [{"y": 1500, "m": 3, "d": 21}, {"y": 1501, "m": 3, "d": 21}]
    # corrected: the 22nd
    corrected = parse(FEASTS.replace("day = 21", "day = 22"))
    await graph.load_observances(corrected, [J])
    assert count(db_driver, "CalendarObservance") == 2
    after = run(
        db_driver,
        "MATCH (:CalendarObservance {key: 'sarum:st-benedict'})-[:FALLS_ON]->(d) RETURN d.julian_day AS d",
    )
    assert after == [{"d": 22}, {"d": 22}]
    back = await graph.read_observances()
    assert [o.key for o in back] == ["sarum:pentecost", "sarum:st-benedict"]
    assert back[1].fixed == (3, 22) and back[0].easter_offset == 49


async def test_seeding_after_the_feasts_links_them_for_the_new_days(
    db_driver, clear_calendar
):
    await structure()
    await graph.seed(1500, 1500, J)
    await graph.load_observances(parse(FEASTS), [J])
    await graph.seed(1501, 1501, J)
    assert await graph.link_observances([J]) == 4
    assert from_jdn(parse_day("J1501-03-21"), J).year == 1501


async def test_status_says_what_there_is(db_driver, clear_calendar):
    await structure()
    assert (await graph.status())["days"] == 0
    await graph.seed(1500, 1500, J)
    found = await graph.status()
    assert found["days"] == 366 and found["first"] == to_jdn(1500, 1, 1, J)
