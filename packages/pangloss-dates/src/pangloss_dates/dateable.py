"""Dateable documents and entities: a trait that gives a class a `date`, and says when it was in its `ReferenceView`.

    class Statement(Document, Dateable): ...          # date: Date (any kind)
    class Birth(Document, SingleDateable): ...        # something that happened once
    class Office(Document, PeriodDateable): ...       # something that lasted

When one is written, the date's sort days and a short text of it are copied onto its own node (`date_sort_day`,
`date_end_sort_day`, `date_text`: database fields, worked out, never the client's to write). They are in its reference
view, so a list or what refers to an entity can be ordered by date and show it with no read of the date itself; and
`date_sort_day` is indexed (`:Dateable`) to order by it in the database. The text uses no words, so it needs no
translation: `1500`, `1500-03`, `1500–1502`, `≥ 1500`, `≤ 1502`, `?`, `1500–…`, `↻ 1500–1520`, an EDTF date as written.

A class may narrow the date (`date: JulianDate`, `date: Annotated[Date, SortDefault(...)]`). The traits are heritable:
the nodes are labelled `:Dateable` (and `:SingleDateable`, `:PeriodDateable`), so a relation can point to "anything
dateable". A class that had a date before it was dateable has nothing copied until it is saved again: see
`fill_in_dateables` for a migration that does it.
"""

from typing import Annotated, Any, ClassVar

from pangloss_models import DBField, Trait, create_validator, update_validator

from pangloss_dates.models import (
    Date,
    DateRange,
    EDTFDate,
    ExactDate,
    OngoingDate,
    Period,
    Recurrence,
    UnknownDate,
)

COPIED_FIELDS = ("date_sort_day", "date_end_sort_day", "date_text")


def _kind(date) -> type:
    """The class of a date: of a model of it, or of a date read from the database as a dict (`type` and its ends)"""
    if isinstance(date, dict):
        from pangloss_models import ModelRegistry

        return ModelRegistry.all_models()[date["type"]]
    return type(date)._owner


def _part(date, name: str):
    return date.get(name) if isinstance(date, dict) else getattr(date, name)


def text_of(date) -> str:
    """The date said with no words (see the module): of a model of it, or of a dict as `fill_in_dateables` reads it"""
    kind = _kind(date)
    if issubclass(kind, ExactDate):
        month, day = _part(date, "month"), _part(date, "day")
        parts = [str(_part(date, "year"))] + [
            f"{part:02d}" for part in (month, day) if part is not None
        ]
        return "-".join(parts)
    if issubclass(kind, EDTFDate):
        return _part(date, "edtf")
    if issubclass(kind, UnknownDate):
        return "?"
    if issubclass(kind, OngoingDate):
        return "…"
    if issubclass(kind, DateRange):
        first, last = _part(date, "not_before"), _part(date, "not_after")
        if issubclass(_kind(last), UnknownDate):
            return f"≥ {text_of(first)}"
        if issubclass(_kind(first), UnknownDate):
            return f"≤ {text_of(last)}"
        return f"{text_of(first)}–{text_of(last)}"
    if issubclass(kind, (Period, Recurrence)):
        span = f"{_end_text(_part(date, 'start'))}–{_end_text(_part(date, 'end'))}"
        return f"↻ {span}" if issubclass(kind, Recurrence) else span
    raise TypeError(f"{kind.__name__} is not a kind of date text_of knows")


def _end_text(end) -> str:
    """(a range as the end of a period is bracketed, so that the dashes are not confused)"""
    text = text_of(end)
    return f"[{text}]" if issubclass(_kind(end), DateRange) else text


class Dateable(Trait):
    """Has a `date` of any kind; see the module"""

    reference_view_fields: ClassVar[tuple[str, ...]] = COPIED_FIELDS

    date: Date

    # copied from the date, and only in the database
    date_sort_day: Annotated[int | None, DBField] = None
    """The day the date sorts by (a day number: see `pangloss_dates.calendar`)"""
    date_end_sort_day: Annotated[int | None, DBField] = None
    """For a period or a recurrence the day its end sorts by; for any other date, the same as `date_sort_day`"""
    date_text: Annotated[str | None, DBField] = None
    """The date said with no words: `1500-03`, `≥ 1500`, `1500–…`"""

    @create_validator
    @update_validator
    def copy_the_date(self):
        # (on the models written to the database, which have the copies; the date's own validator has run, and
        # the field's markers, such as a `SortDefault`, have been applied to it)
        copy_the_date(self)


def copy_the_date(item: Any) -> None:
    date = item.date
    if date is None:
        # (a class below may make the date optional, `date: Date | None = None`: with none, there is nothing to copy)
        item.date_sort_day = item.date_end_sort_day = item.date_text = None
        return
    item.date_sort_day = date.sort_day
    item.date_end_sort_day = date.end_sort_day
    item.date_text = text_of(date)


class SingleDateable(Dateable):
    """Something that happened once: an exact date, a range it lies in, an EDTF date, or not known"""

    date: ExactDate | DateRange | EDTFDate | UnknownDate


class PeriodDateable(Dateable):
    """Something that lasted, from a start to an end (or nothing known of when)"""

    date: Period | UnknownDate


def is_dateable(model: type) -> bool:
    return isinstance(model, type) and issubclass(model, Dateable)


# A date and the dates in it (the ends of a range or a period, and the ends of a range that is the end of a period), as
# they are stored: the forward edges from each to the next
_STORED_DATES = """
MATCH (n:Dateable)-[r:date]->(d:Date)
WHERE NOT coalesce(r.reverse, false) AND n.date_text IS NULL
WITH n, d LIMIT $batch
OPTIONAL MATCH (d)-[e]->(x:Date) WHERE NOT coalesce(e.reverse, false)
OPTIONAL MATCH (x)-[f]->(y:Date) WHERE NOT coalesce(f.reverse, false)
RETURN n.id AS id, properties(d) AS date,
       collect(DISTINCT [type(e), properties(x)]) AS ends,
       collect(DISTINCT [type(e), type(f), properties(y)]) AS inner
"""

_SET_COPIES = """
UNWIND $rows AS row
MATCH (n:Dateable {id: row.id})
SET n.date_sort_day = row.sort_day, n.date_end_sort_day = row.end_sort_day, n.date_text = row.text
"""


def _stored_date(row: dict) -> dict:
    date = dict(row["date"])
    for name, end in row["ends"]:
        if name is not None:
            date[name] = dict(end)
    for name, inner_name, inner in row["inner"]:
        if inner_name is not None:
            date[name][inner_name] = dict(inner)
    return date


async def fill_in_dateables(tx, state=None, batch: int = 5000) -> int:
    """Copies the dates of the dateable documents that have no copy yet (written before their class was dateable):
    for a migration, as `RunPython("pangloss_dates.dateable:fill_in_dateables")` after the one that adds the `:Dateable`
    label and the fields. Returns how many were filled in."""
    done = 0
    while True:
        result = await tx.run(_STORED_DATES, batch=batch)
        rows = await result.data()
        if not rows:
            return done
        copies = []
        for row in rows:
            date = _stored_date(row)
            copies.append(
                {
                    "id": row["id"],
                    "sort_day": date.get("sort_day"),
                    "end_sort_day": date.get("end_sort_day"),
                    "text": text_of(date),
                }
            )
        await tx.run(_SET_COPIES, rows=copies)
        done += len(copies)
