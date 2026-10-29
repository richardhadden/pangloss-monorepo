"""The day of Easter, in the Julian or the Gregorian calendar.

`easter(year, calendar)` is the day number of Easter Sunday **as the calendar asked for reckons it**: the Julian
method (the Julian calendar and the old table of the moon) gives the Easter of the Orthodox churches and of the
West before 1583; the Gregorian method gives the Western one now. Each is returned as a day number, so the
Julian Easter of 2000 (17 April Julian) is the day that the Gregorian calendar calls 30 April. There is no cutover:
for a project that moves from one to the other, ask in the calendar of the question.

Both are the algorithms of Meeus, "Astronomical Algorithms" (1991), chapter 8.
"""

from pangloss_dates.calendar import Calendar, to_jdn


def easter(year: int, calendar: Calendar) -> int:
    if calendar == Calendar.JULIAN:
        d = (19 * (year % 19) + 15) % 30
        e = (2 * (year % 4) + 4 * (year % 7) - d + 34) % 7
        month, day = divmod(d + e + 114, 31)
    else:
        a = year % 19
        b, c = divmod(year, 100)
        d, e = divmod(b, 4)
        g = (b - (b + 8) // 25 + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i, k = divmod(c, 4)
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month, day = divmod(h + l - 7 * m + 114, 31)
    return to_jdn(year, month, day + 1, calendar)
