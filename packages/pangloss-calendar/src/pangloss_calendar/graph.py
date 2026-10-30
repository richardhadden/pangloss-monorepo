"""The calendar graph: all the Cypher of the package, and the only module that reaches the database (through `pangloss_core.backend`, so any backend).

    (:CalendarDay {jdn, weekday, julian_year, julian_month, julian_day, gregorian_year, ...})-[:NEXT]->(:CalendarDay)
    (:CalendarMonth {calendar, year, month, first_jdn, last_jdn})-[:CONTAINS]->(:CalendarDay), -[:NEXT]->(:CalendarMonth)
    (:CalendarYear {calendar, year})-[:CONTAINS]->(:CalendarMonth)
    (:CalendarSpan {first_jdn, last_jdn})
    (:CalendarDay | :CalendarMonth | :CalendarYear | :CalendarSpan)-[:CHARACTERISED_BY {origin: 'rule' | 'manual'}]->(:DateCharacterisation)

Everything is `MERGE`, so a second run changes nothing. The structure (indexes and keys) is made by the package's
migration; the nodes by `seed` and `ensure_range`. Writes are in batches of `BATCH_DAYS` days, each its own
transaction.
"""

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pangloss_core import backend
from pangloss_core.backend import Transaction
from pangloss_dates.calendar import Calendar, from_jdn, to_jdn, weekday
from pangloss_dates.config import default_calendar

from pangloss_calendar.characterisations import Characterisation, days_between, from_row
from pangloss_calendar.days import month_span

BATCH_DAYS = 2000

CALENDARS = (Calendar.JULIAN, Calendar.GREGORIAN)


def _database():
    return backend.current().Database.default


def unpublished_visible() -> bool:
    return backend.current().unpublished_visible()


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
                    "year_first": to_jdn(year, 1, 1, calendar),
                    "year_last": to_jdn(year, 12, 31, calendar),
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
SET y.first_jdn = row.year_first, y.last_jdn = row.year_last
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
        return record["days"] if record else 0

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
            OPTIONAL MATCH (:CalendarDay)-[e:CHARACTERISED_BY]->()
            RETURN days, first, last, months, years, count(e) AS characterised
            """
        )
        return dict(await result.single())

    return await read()


# Characterisations (entities of a subclass of `DateCharacterisation`) and the edges to what they characterise

CHARACTERISATIONS = """
MATCH (n:DateCharacterisation)
WHERE NOT coalesce(n.deleted, false) AND ($use IS NULL OR n.use = $use)
OPTIONAL MATCH (n)-[:`when`]->(d:Date)
OPTIONAL MATCH (d)-[:start]->(s:Date)
RETURN n.id AS id, n.label AS label, n.type AS type, n.use AS use, n.rank AS rank,
       d.calendar AS calendar, d.earliest_strict AS earliest_strict, d.latest_strict AS latest_strict,
       d.frequency AS frequency, d.weekdays AS weekdays, d.nth AS nth, d.month AS month,
       d.month_day AS month_day, d.interval AS interval, d.excluded_days AS excluded_days,
       d.easter_offset AS easter_offset, d.feast AS feast, d.leap_shift AS leap_shift, s.earliest_strict AS anchor
ORDER BY n.label, n.id
"""


async def read_characterisations(use: str | None = None) -> list[Characterisation]:
    """Every characterisation (not deleted), with its rule if it has one"""
    database = _database()

    @database.read_transaction
    async def read(tx: Transaction) -> list[dict[str, Any]]:
        result = await tx.run(CHARACTERISATIONS, use=use)
        return [dict(record) async for record in result]

    default = default_calendar()
    return [from_row(row, default) for row in await read()]


MANUAL_BETWEEN = """
CALL {
  MATCH (t:CalendarDay)-[:CHARACTERISED_BY {origin: 'manual'}]->(c)
  WHERE t.jdn >= $first AND t.jdn <= $last
  RETURN c, t.jdn AS lo, t.jdn AS hi, 'day' AS via
  UNION
  MATCH (t:CalendarMonth)-[:CHARACTERISED_BY {origin: 'manual'}]->(c)
  WHERE t.first_jdn <= $last AND t.last_jdn >= $first
  RETURN c, t.first_jdn AS lo, t.last_jdn AS hi, 'month' AS via
  UNION
  MATCH (t:CalendarYear)-[:CHARACTERISED_BY {origin: 'manual'}]->(c)
  WHERE t.first_jdn <= $last AND t.last_jdn >= $first
  RETURN c, t.first_jdn AS lo, t.last_jdn AS hi, 'year' AS via
  UNION
  MATCH (t:CalendarSpan)-[:CHARACTERISED_BY {origin: 'manual'}]->(c)
  WHERE t.first_jdn <= $last AND t.last_jdn >= $first
  RETURN c, t.first_jdn AS lo, t.last_jdn AS hi, 'span' AS via
}
WITH c, lo, hi, via
WHERE NOT coalesce(c.deleted, false) AND ($use IS NULL OR c.use = $use)
RETURN c.id AS id, c.label AS label, c.type AS type, c.use AS use, c.rank AS rank, lo, hi, via
ORDER BY c.label, c.id, lo
"""


async def manual_between(
    first: int, last: int, use: str | None = None
) -> list[dict[str, Any]]:
    """The characterisations attached by hand to a day, month, year or span that meets the days `first` to `last`,
    with the range of what each is attached to (`lo`, `hi`) and which kind it is (`via`)"""
    database = _database()

    @database.read_transaction
    async def read(tx: Transaction) -> list[dict[str, Any]]:
        result = await tx.run(MANUAL_BETWEEN, first=first, last=last, use=use)
        return [{**record, "id": UUID(record["id"])} async for record in result]

    return await read()


@dataclass(frozen=True)
class Target:
    """What a characterisation is attached to: `day` (`first`), `month` or `year` (of a `calendar`), or a `span` of days"""

    kind: str
    first: int | None = None
    last: int | None = None
    calendar: Calendar | None = None
    year: int | None = None
    month: int | None = None

    def days(self) -> tuple[int, int]:
        """The first and last day number it covers"""
        if self.kind in ("day", "span"):
            assert self.first is not None
            return self.first, self.last if self.last is not None else self.first
        assert self.calendar is not None and self.year is not None
        if self.kind == "month":
            assert self.month is not None
            return month_span(self.calendar, self.year, self.month)
        return to_jdn(self.year, 1, 1, self.calendar), to_jdn(
            self.year, 12, 31, self.calendar
        )


_MATCH_TARGET = {
    "day": "MATCH (t:CalendarDay {jdn: $first})",
    "month": "MATCH (t:CalendarMonth {calendar: $calendar, year: $year, month: $month})",
    "year": "MATCH (t:CalendarYear {calendar: $calendar, year: $year})",
    "span": "MERGE (t:CalendarSpan {first_jdn: $first, last_jdn: $last})",
}


def _target_parameters(target: Target) -> dict[str, Any]:
    first, last = target.days()
    return {
        "first": first,
        "last": last,
        "calendar": target.calendar.value if target.calendar else None,
        "year": target.year,
        "month": target.month,
    }


async def attach(characterisation: UUID, target: Target) -> bool:
    """Attach the characterisation by hand. The days of a day, month or year are made if they are not there (the
    caller has said they are within reach). Returns False if there is no such characterisation."""
    if target.kind != "span":
        first, last = target.days()
        await ensure_range(first, last)
    database = _database()

    @database.write_transaction
    async def write(tx: Transaction) -> bool:
        result = await tx.run(
            f"""
            MATCH (c:DateCharacterisation {{id: $id}}) WHERE NOT coalesce(c.deleted, false)
            {_MATCH_TARGET[target.kind]}
            MERGE (t)-[e:CHARACTERISED_BY {{origin: 'manual'}}]->(c)
            RETURN count(e) AS made
            """,
            id=str(characterisation),
            **_target_parameters(target),
        )
        record = await result.single()
        return bool(record and record["made"])

    return await write()


async def detach(characterisation: UUID, target: Target) -> int:
    """Take away the hand-made attachment (not the ones made from a rule). Returns how many were removed"""
    database = _database()
    match = _MATCH_TARGET[target.kind].replace(
        "MERGE (t:CalendarSpan", "MATCH (t:CalendarSpan"
    )

    @database.write_transaction
    async def write(tx: Transaction) -> int:
        result = await tx.run(
            f"""
            {match}
            MATCH (t)-[e:CHARACTERISED_BY {{origin: 'manual'}}]->(c:DateCharacterisation {{id: $id}})
            DELETE e
            RETURN count(e) AS removed
            """,
            id=str(characterisation),
            **_target_parameters(target),
        )
        record = await result.single()
        return record["removed"] if record else 0

    return await write()


CLEAR_RULE_EDGES = (
    "MATCH (:CalendarDay)-[e:CHARACTERISED_BY {origin: 'rule'}]->() DELETE e"
)

LINK_RULE_EDGES = """
UNWIND $pairs AS pair
MATCH (d:CalendarDay {jdn: pair.jdn})
MATCH (c:DateCharacterisation {id: pair.id})
MERGE (d)-[:CHARACTERISED_BY {origin: 'rule'}]->(c)
"""


@dataclass
class LinkReport:
    edges: int = 0
    characterisations: int = 0
    clipped: int = 0
    """Rules whose lifetime goes beyond the reach: only the days inside it are linked"""
    outside: int = 0
    """Rules whose lifetime is wholly beyond the reach: nothing is linked"""
    extended: int = 0
    """Days made outside the span but within the margin"""


async def link_rules(first: int, last: int, span: tuple[int, int]) -> LinkReport:
    """(Re)make the edges from days to the characterisations whose rule falls on them, for the days from `first` to
    `last` (the reach; days in it outside the `span` are made, which extends the calendar). Hand-made edges are
    not touched. Days beyond `last` and before `first` are never made."""
    report = LinkReport()
    pairs: list[dict[str, Any]] = []
    counted: set[UUID] = set()
    for c in await read_characterisations():
        if not c.has_days:
            continue
        counted.add(c.id)
        if (
            c.last is not None
            and c.last < first
            or c.first is not None
            and c.first > last
        ):
            report.outside += 1
            continue
        if (c.first is not None and c.first < first) or (
            c.last is not None and c.last > last
        ):
            report.clipped += 1
        pairs.extend({"jdn": d, "id": str(c.id)} for d in days_between(c, first, last))
    if pairs:
        low, high = min(p["jdn"] for p in pairs), max(p["jdn"] for p in pairs)
        if low < span[0] or high > span[1]:
            for lo, hi in (
                (low, min(high, span[0] - 1)),
                (max(low, span[1] + 1), high),
            ):
                if lo <= hi:
                    report.extended += await ensure_range(lo, hi)
    database = _database()

    @database.write_transaction
    async def write(tx: Transaction) -> None:
        await (await tx.run(CLEAR_RULE_EDGES)).consume()
        for start in range(0, len(pairs), BATCH_DAYS):
            await (
                await tx.run(LINK_RULE_EDGES, pairs=pairs[start : start + BATCH_DAYS])
            ).consume()

    await write()
    report.edges = len({(p["jdn"], p["id"]) for p in pairs})
    report.characterisations = len(counted)
    return report


CHARACTERISATION_DAYS = """
MATCH (d:CalendarDay)-[:CHARACTERISED_BY {origin: 'rule'}]->(:DateCharacterisation {id: $id})
WHERE d.jdn >= $first AND d.jdn <= $last
RETURN d.jdn AS jdn ORDER BY d.jdn
"""


# Dates found from the dates, not from the documents (the plan's "date-first" query)

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

DATED_BETWEEN = """
MATCH (d:Date)
WHERE d.earliest_fuzzy <= $last AND d.latest_fuzzy >= $first
  AND ($strict = false OR (d.earliest_strict <= $last AND d.latest_strict >= $first))
  AND ($keys IS NULL OR d.pattern_keys IS NULL OR any(k IN d.pattern_keys WHERE k IN $keys))
MATCH (n:`{label}`)-[:`{field}`]->(d)
OPTIONAL MATCH (h:HeadNode {{id: n.head_node_id}})
WITH n, d, coalesce(h, n) AS head
WHERE NOT coalesce(head.deleted, false) AND ($see_unpublished OR coalesce(head.published, true))
OPTIONAL MATCH (d)-[:start]->(s:Date)
RETURN n.id AS id, n.label AS label, n.type AS type, d.type AS kind, d.calendar AS calendar,
       d.earliest_fuzzy AS earliest_fuzzy, d.earliest_strict AS earliest_strict,
       d.latest_strict AS latest_strict, d.latest_fuzzy AS latest_fuzzy,
       d.frequency AS frequency, d.weekdays AS weekdays, d.nth AS nth, d.month AS month,
       d.month_day AS month_day, d.interval AS interval, d.excluded_days AS excluded_days,
       d.easter_offset AS easter_offset, d.feast AS feast, s.earliest_strict AS anchor
LIMIT $limit
"""


async def dated_between(
    label: str,
    field: str,
    first: int,
    last: int,
    *,
    strict: bool,
    keys: list[str] | None,
    limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    """The dates in `field` of the nodes of class `label` that might meet the days `first` to `last`, with the node
    each is in: by the strict bounds if `strict`, else by the fuzzy ones (a superset). A repeated event is a
    candidate if its lifetime meets the days and, when `keys` is given, it has one of them (`pattern_keys`). What
    is deleted, or unpublished for a reader who may not see it, is left out. Returns the rows and whether there
    were more than `limit`."""
    if not (IDENTIFIER.match(label) and IDENTIFIER.match(field)):
        raise ValueError(f"{label}.{field} is not a class and a field")
    database = _database()

    @database.read_transaction
    @backend.current().timeout_from_setting("SEARCH_TIMEOUT_SECONDS", 30)
    async def read(tx: Transaction) -> list[dict[str, Any]]:
        result = await tx.run(
            DATED_BETWEEN.format(label=label, field=field),
            first=first,
            last=last,
            strict=strict,
            keys=keys,
            limit=limit + 1,
            see_unpublished=unpublished_visible(),
        )
        return [dict(record) async for record in result]

    rows = await read()
    return rows[:limit], len(rows) > limit
