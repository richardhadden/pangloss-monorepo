# pangloss-dates

Optional. Dates for historical data, as `Embedded` types: exact, EDTF, range, ongoing, period and recurrence, in Julian and
Gregorian families, each reduced to four stored bounds and a sort day so that they can be searched and ordered. `on_day` finds
what falls on a day, repeated events included. Uses `python-edtf` as a parser only; the day arithmetic is its own.

Guide: [guide/dates](../../guide/dates/README.md). Reference: [docs/dates-implementation.md](../../docs/dates-implementation.md)
(built; the original design is [docs/dates.md](../../docs/dates.md)).
