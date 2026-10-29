"""The calendar graph: all the Cypher of the package, and the only module that knows Memgraph.

    (:CalendarDay {jdn, weekday, julian_year, julian_month, julian_day, gregorian_year, ...})-[:NEXT]->(:CalendarDay)
    (:CalendarMonth {calendar, year, month, first_jdn, last_jdn})-[:CONTAINS]->(:CalendarDay), -[:NEXT]->(:CalendarMonth)
    (:CalendarYear {calendar, year})-[:CONTAINS]->(:CalendarMonth)
    (:CalendarObservance {key, use, names, rank, fixed_month, fixed_day, easter_offset, leap_shift})
        -[:FALLS_ON {calendar, year}]->(:CalendarDay)

Everything is `MERGE`, so a second run changes nothing. The structure (indexes and keys) is made by the package's
migration; the nodes by `seed` and `ensure_range`. Writes are in batches of `BATCH_DAYS` days, each its own
transaction.
"""

import json
from typing import Any

from pangloss_dates.calendar import Calendar, from_jdn, to_jdn, weekday
from pangloss_memgraph.databases.memgraph.database import Database, Transaction

from pangloss_calendar.days import month_span
from pangloss_calendar.observances import Observance, falls_on

BATCH_DAYS = 2000

CALENDARS = (Calendar.JULIAN, Calendar.GREGORIAN)


def _database() -> Database:
    return Database.default


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def day_rows(first: int, last: int) -> list[dict[str, Any]]:
    """The properties of each day from `first` to `last`, with the month of each in both calendars (pure)"""
    rows = []
    for jdn in range(first, last + 1):
        julian = from_jdn(jdn, Calendar.JULIAN)
        gregorian = from_jdn(jdn, Calendar.GREGORIAN)
        rows.append(
            {
                "jdn": jdn,
                "weekday": int(weekday(jdn)),
                "julian_year": julian.year,
                "julian_month": julian.month,
                "julian_day": julian.day,
                "gregorian_year": gregorian.year,
                "gregorian_month": gregorian.month,
                "gregorian_day": gregorian.day,
            }
        )
    return rows


def month_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The months (of both calendars) that the days belong to, each once, with its first and last day (pure)"""
    months: dict[tuple[str, int, int], dict[str, Any]] = {}
    for row in rows:
        for calendar in CALENDARS:
            year, month = row[f"{calendar.value}_year"], row[f"{calendar.value}_month"]
            key = (calendar.value, year, month)
            if key not in months:
                first, last = month_span(calendar, year, month)
                after = _next_month(year, month)
                before = (year - 1, 12) if month == 1 else (year, month - 1)
                months[key] = {
                    "calendar": calendar.value,
                    "year": year,
                    "month": month,
                    "first_jdn": first,
                    "last_jdn": last,
                    "next_year": after[0],
                    "next_month": after[1],
                    "previous_year": before[0],
                    "previous_month": before[1],
                }
    return list(months.values())


MERGE_DAYS = """
UNWIND $days AS row
MERGE (d:CalendarDay {jdn: row.jdn})
SET d.weekday = row.weekday,
    d.julian_year = row.julian_year, d.julian_month = row.julian_month, d.julian_day = row.julian_day,
    d.gregorian_year = row.gregorian_year, d.gregorian_month = row.gregorian_month,
    d.gregorian_day = row.gregorian_day
"""

MERGE_MONTHS = """
UNWIND $months AS row
MERGE (y:CalendarYear {calendar: row.calendar, year: row.year})
MERGE (m:CalendarMonth {calendar: row.calendar, year: row.year, month: row.month})
SET m.first_jdn = row.first_jdn, m.last_jdn = row.last_jdn
MERGE (y)-[:CONTAINS]->(m)
"""

CONTAIN_DAYS = """
UNWIND $days AS row
MATCH (d:CalendarDay {jdn: row.jdn})
MATCH (j:CalendarMonth {calendar: "julian", year: row.julian_year, month: row.julian_month})
MATCH (g:CalendarMonth {calendar: "gregorian", year: row.gregorian_year, month: row.gregorian_month})
MERGE (j)-[:CONTAINS]->(d)
MERGE (g)-[:CONTAINS]->(d)
"""

LINK_DAYS = """
UNWIND range($first - 1, $last) AS jdn
MATCH (a:CalendarDay {jdn: jdn})
MATCH (b:CalendarDay {jdn: jdn + 1})
MERGE (a)-[:NEXT]->(b)
"""

LINK_MONTHS = """
UNWIND $months AS row
MATCH (a:CalendarMonth {calendar: row.calendar, year: row.year, month: row.month})
MATCH (b:CalendarMonth {calendar: row.calendar, year: row.next_year, month: row.next_month})
MERGE (a)-[:NEXT]->(b)
"""

LINK_PREVIOUS_MONTHS = """
UNWIND $months AS row
MATCH (b:CalendarMonth {calendar: row.calendar, year: row.year, month: row.month})
MATCH (a:CalendarMonth {calendar: row.calendar, year: row.previous_year, month: row.previous_month})
MERGE (a)-[:NEXT]->(b)
"""


async def _write_days(tx: Transaction, rows: list[dict[str, Any]]) -> None:
    months = month_rows(rows)
    for query, parameters in (
        (MERGE_DAYS, {"days": rows}),
        (MERGE_MONTHS, {"months": months}),
        (CONTAIN_DAYS, {"days": rows}),
        (LINK_DAYS, {"first": rows[0]["jdn"], "last": rows[-1]["jdn"]}),
        (LINK_MONTHS, {"months": months}),
        (LINK_PREVIOUS_MONTHS, {"months": months}),
    ):
        await (await tx.run(query, parameters)).consume()


COUNT_DAYS = """
MATCH (d:CalendarDay) WHERE d.jdn >= $first AND d.jdn <= $last
RETURN count(d) AS days
"""


async def ensure_range(first: int, last: int) -> int:
    """Make the days from `first` to `last` (day numbers), with their months and years in both calendars, if they are
    not there. Returns how many days were missing (0 if all were there, nothing written)."""
    database = _database()

    @database.read_transaction
    async def count(tx: Transaction) -> int:
        record = await (await tx.run(COUNT_DAYS, first=first, last=last)).single()
        return record["days"]

    @database.write_transaction
    async def write(tx: Transaction, rows: list[dict[str, Any]]) -> None:
        await _write_days(tx, rows)

    missing = (last - first + 1) - await count()
    if missing == 0:
        return 0
    for start in range(first, last + 1, BATCH_DAYS):
        await write(day_rows(start, min(start + BATCH_DAYS - 1, last)))
    return missing


async def seed(first_year: int, last_year: int, calendar: Calendar) -> int:
    """Make every day from 1 January of `first_year` to 31 December of `last_year` of the calendar"""
    return await ensure_range(
        to_jdn(first_year, 1, 1, calendar), to_jdn(last_year, 12, 31, calendar)
    )


async def status() -> dict[str, Any]:
    """How much of the graph there is"""
    database = _database()

    @database.read_transaction
    async def read(tx: Transaction) -> dict[str, Any]:
        result = await tx.run(
            """
            OPTIONAL MATCH (d:CalendarDay)
            WITH count(d) AS days, min(d.jdn) AS first, max(d.jdn) AS last
            OPTIONAL MATCH (m:CalendarMonth) WITH days, first, last, count(m) AS months
            OPTIONAL MATCH (y:CalendarYear) WITH days, first, last, months, count(y) AS years
            OPTIONAL MATCH (o:CalendarObservance)
            RETURN days, first, last, months, years, count(o) AS observances
            """
        )
        return dict(await result.single())

    return await read()


# Observances

MERGE_OBSERVANCES = """
UNWIND $observances AS row
MERGE (o:CalendarObservance {key: row.key})
SET o.use = row.use, o.names = row.names, o.rank = row.rank, o.fixed_month = row.fixed_month,
    o.fixed_day = row.fixed_day, o.easter_offset = row.easter_offset, o.leap_shift = row.leap_shift
"""

CLEAR_FALLS_ON = """
MATCH (:CalendarObservance)-[f:FALLS_ON]->(:CalendarDay)
WHERE f.calendar IN $calendars
DELETE f
"""

LINK_FALLS_ON = """
UNWIND $falls AS row
MATCH (o:CalendarObservance {key: row.key})
MATCH (d:CalendarDay {jdn: row.jdn})
MERGE (o)-[f:FALLS_ON {calendar: row.calendar, year: row.year}]->(d)
"""

READ_OBSERVANCES = "MATCH (o:CalendarObservance) RETURN o ORDER BY o.key"


def observance_row(observance: Observance) -> dict[str, Any]:
    return {
        "key": observance.key,
        "use": observance.use,
        "names": json.dumps(observance.name, ensure_ascii=False),
        "rank": observance.rank,
        "fixed_month": observance.fixed[0] if observance.fixed else None,
        "fixed_day": observance.fixed[1] if observance.fixed else None,
        "easter_offset": observance.easter_offset,
        "leap_shift": observance.leap_shift,
    }


def observance_of(node: Any) -> Observance:
    fixed = (
        (node["fixed_month"], node["fixed_day"])
        if node.get("fixed_month") is not None
        else None
    )
    return Observance(
        key=node["key"],
        use=node["use"],
        name=json.loads(node.get("names") or "{}"),
        rank=node.get("rank"),
        fixed=fixed,
        easter_offset=node.get("easter_offset"),
        leap_shift=bool(node.get("leap_shift")),
    )


async def read_observances() -> list[Observance]:
    database = _database()

    @database.read_transaction
    async def read(tx: Transaction) -> list[Observance]:
        result = await tx.run(READ_OBSERVANCES)
        return [observance_of(record["o"]) async for record in result]

    return await read()


def falls_rows(
    observances: list[Observance], first: int, last: int, calendars: list[Calendar]
) -> list[dict[str, Any]]:
    """Where each observance falls in the years that the days `first` to `last` touch (pure)"""
    rows = []
    for calendar in calendars:
        years = range(from_jdn(first, calendar).year, from_jdn(last, calendar).year + 1)
        for observance in observances:
            for year in years:
                jdn = falls_on(observance, year, calendar)
                if jdn is not None and first <= jdn <= last:
                    rows.append(
                        {
                            "key": observance.key,
                            "calendar": calendar.value,
                            "year": year,
                            "jdn": jdn,
                        }
                    )
    return rows


async def link_observances(calendars: list[Calendar]) -> int:
    """(Re)make the `FALLS_ON` edges of the observances in the graph, for the days that exist and the calendars
    given. The edges of those calendars are deleted first, so a corrected observance leaves no stale one.
    Returns the number of edges."""
    database = _database()
    observances = await read_observances()
    state = await status()
    if not observances or state["first"] is None:
        return 0
    rows = falls_rows(observances, state["first"], state["last"], calendars)

    @database.write_transaction
    async def write(tx: Transaction) -> None:
        await (
            await tx.run(CLEAR_FALLS_ON, calendars=[c.value for c in calendars])
        ).consume()
        for start in range(0, len(rows), BATCH_DAYS):
            await (
                await tx.run(LINK_FALLS_ON, falls=rows[start : start + BATCH_DAYS])
            ).consume()

    await write()
    return len(rows)


async def load_observances(
    observances: list[Observance], calendars: list[Calendar]
) -> int:
    """Make or correct the observances (by `key`) and link them to the days. Returns the edges made"""
    database = _database()

    @database.write_transaction
    async def write(tx: Transaction) -> None:
        await (
            await tx.run(
                MERGE_OBSERVANCES,
                observances=[observance_row(o) for o in observances],
            )
        ).consume()

    await write()
    return await link_observances(calendars)
