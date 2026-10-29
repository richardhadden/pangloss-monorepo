# Calendar

`pangloss-calendar` shows what is dated on a day, in a month or in a year, in the Julian or the Gregorian calendar, with the feasts
that you give it. It needs [`pangloss-dates`](../dates/README.md) (your models' dates are what it finds). The design and the numbers
are in [docs/calendar-implementation.md](../../docs/calendar-implementation.md).

## Set up

1. Add `"pangloss_calendar"` to `INSTALLED_APPS`, after `pangloss_dates`.
2. Settings:

   | Setting | |
   |---|---|
   | `CALENDAR_FIRST_YEAR`, `CALENDAR_LAST_YEAR` | The span to make days for. No default: `seed` refuses to run without them |
   | `CALENDAR_DEFAULT` | `"julian"` or `"gregorian"`: the calendar a view is read in (default: `DATES_DEFAULT_CALENDAR`) |
   | `CALENDAR_USE` | Only the feasts of this liturgical use (default: all) |
   | `CALENDAR_NARROW_DAYS` | A date that states a range of this many days or fewer is drawn on each of its days in a month; a wider one is listed apart (default 7) |
   | `CALENDAR_FIELDS` | `["Letter.sent", ...]`: look only in these date fields (default: every date field of every Document and Entity) |
   | `CALENDAR_AUTO_EXTEND` | Make the days of the graph that are asked for and are not there (default off; the answers do not need them) |

3. `pangloss migrate` (the keys and indexes), then `pangloss calendar seed` (days, with their months and years in both calendars).
   Running it again is harmless.

## Feasts

None are provided: you write them. A TOML file, one `[[observance]]` for each:

```toml
[[observance]]
key = "sarum:st-benedict"        # unique; the prefix is the use
use = "sarum"
name = { en = "Benedict", la = "Benedicti abbatis" }
rank = "major"
fixed = { month = 3, day = 21 }  # a fixed feast ...

[[observance]]
key = "sarum:pentecost"
use = "sarum"
easter_offset = 49               # ... or days from Easter (-80 to 250)
```

A fixed feast on 24 to 28 February may say `leap_shift = true`: it falls a day later in a leap year (the old Roman leap day was made by
repeating the 24th). Feasts are worked out in the calendar asked for, so a Julian project gets Julian 21 March and the Julian Easter.

`pangloss calendar load-observances feasts.toml` makes or corrects them by `key` (running it again after a correction leaves one of
each) and links them to the days that exist, for the calendar in `CALENDAR_DEFAULT` (`--calendar` for others). `pangloss calendar status`
says how much there is.

A repeated event can fall on a feast: in `pangloss-dates`, a `Recurrence` takes `feast = "sarum:st-benedict"` or `easter_offset = 49`
(yearly) in place of a month.

## Reading it

Read only, under `/api/calendar` (see [the API](../../docs/api.md)): `day/J1500-03-02` (or `G1500-03-12`, or a day number: the same
day), `month/julian/1500/3`, `year/julian/1500`, `easter/julian/1500`, `observances`. A date is **stated** on a day if the date says so,
**possible** if only its allowance for doubt reaches it. Nothing deleted, and nothing unpublished for a reader who may not see it, is shown.
