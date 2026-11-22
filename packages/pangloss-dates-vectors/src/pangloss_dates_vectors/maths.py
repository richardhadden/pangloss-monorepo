"""The whole of the computing of the time part, with no database in it: the bounds of a date to a vector.

    earliest_fuzzy  earliest_strict      latest_strict  latest_fuzzy          (day numbers, `pangloss_dates.bounds`)
          │               │                    │              │
          ▼               ▼                    ▼              ▼
          ·           ────────────────────────────            ·     1    how far the date could be each day:
          ·       ╱                                ╲          ·          wholly between the strict bounds,
    ──────────╱                                        ╲──────────  0    falling to nothing at the fuzzy ones
                                 │
                                 ▼   blurred by a bump of `width` years, and read at a centre every `width` years
                 ▁ ▂ ▄ ▆ █ █ █ █ █ █ █ ▆ ▄ ▂ ▁                           the vector, then at length one

- **A date** is what its four bounds say: how far it could be each day, 1 between the strict bounds, falling in a
  line to 0 at the fuzzy ones (a date that is exactly what it says is a box). That is blurred by a bump of the
  width (a logistic curve, whose spread is the width), so that a day and its year are near, and two years ten
  years apart at a width of 2 are not. A vague date is a wide low hill, an exact one a narrow one: they are near
  when one is inside the other, and nearer the more of the vague one the exact one covers.
- **The ring** (`Ring`): the centres are a fixed number of places (`dimension`), `width` years apart, and the
  years go round them: the year after the last place is the first again. So a vector has the same dimension
  whatever years a project's dates are in, no date is outside it, and nothing has to be said of the range. Two
  dates `dimension × width` years apart (256 years, as it is given) have the same vector: within that many years
  the ring changes nothing, and beyond it time alone no longer tells them apart. (Measured, step 9.2: beside the
  graph part, which does tell them apart, folding the years into as few as 32 places cost nothing.)
  A date **longer than the ring** (a period of three centuries; a range whose start is not known, which runs
  from `DATES_EARLIEST_YEAR`) is at every place alike: it says nothing of when, and is a little like every date
  (0.17 with a year, as it is given). A project with such periods that should count gives the ring more places.
- **Several dates** of one item are added, each at length one first, so that a long period does not drown a day.

The cosine of two such vectors falls with the gap between the dates measured in widths, and is the same wherever
they are (to about a hundredth: the centres are a width apart). It finds candidates; it is not a comparison of
two dates.

How the blur is computed. The date is a line in pieces, with corners at its four bounds. A corner is a bend
(`relu`) or, where a strict and a fuzzy bound are the same, a step. A bend blurred by a logistic curve is
`softplus`, a step blurred is the logistic function itself: so a date at a centre is four of them, exactly, with no
sum over days. It is worked out at the centres from well before the date to well after it (where it is nothing
but rounding), and each is added at its place on the ring. implementation_docs/similarity-build-plan.md, step 9.2.
"""

import dataclasses
import math
from collections.abc import Iterable, Sequence

import numpy as np

# The day number (`pangloss_dates.calendar.to_jdn`) of 1 January of the year 1 (Gregorian, counted back), and the
# days of a year: a day is that many years along. (The Julian calendar's days are day numbers too, so a Julian
# date is placed by the day it was, a few days from its Gregorian name: nothing against a bump of years.)
DAY_OF_YEAR_ONE = 1721426
DAYS_IN_A_YEAR = 365.2425

# The spread (standard deviation) of a logistic curve of scale 1
_SPREAD = math.pi / math.sqrt(3)
# How many scales from a date its blur is still worked out (beyond it, less than 1e-15 of its height)
_REACH = 36.0
# How many numbers are worked out at once (dates × centres): the dates are taken in groups under it
_AT_ONCE = 4_000_000

type Bounds = tuple[int, int, int, int]
"""`earliest_fuzzy`, `earliest_strict`, `latest_strict`, `latest_fuzzy`, as day numbers"""


def year_of(day):
    """Where the start of a day is along the years (1500.0 is the start of 1 January 1500)"""
    return 1 + (day - DAY_OF_YEAR_ONE) / DAYS_IN_A_YEAR


@dataclasses.dataclass(frozen=True)
class Ring:
    """The places of a vector: `dimension` centres, `width` years apart, which the years go round"""

    dimension: int = 128
    width: float = 2.0

    def __post_init__(self) -> None:
        if not self.width > 0:
            raise ValueError(
                f"The width of a bump is more than 0 years, not {self.width}"
            )
        if self.dimension < 2:
            raise ValueError(f"A vector has at least 2 places, not {self.dimension}")

    @property
    def years(self) -> float:
        """The years once round: two dates this far apart have the same vector"""
        return self.dimension * self.width

    @property
    def scale(self) -> float:
        """The scale of the logistic curve whose spread is the width"""
        return self.width / _SPREAD


def _bend(x: np.ndarray, scale: float) -> np.ndarray:
    """A bend (0 before 0, then a line of slope 1) blurred: `softplus`"""
    return scale * np.logaddexp(0.0, x / scale)


def _step(x: np.ndarray, scale: float) -> np.ndarray:
    """A step (0 before 0, then 1) blurred: the logistic function"""
    return 0.5 * (1.0 + np.tanh(x / (2.0 * scale)))


def _rise(at: np.ndarray, start: np.ndarray, end: np.ndarray, scale: float):
    """Blurred, at each year of `at`: what is 0 before `start`, rises in a line to 1 at `end` and stays (a step
    where they are the same). `start` and `end` are columns (one row for each date)"""
    span = end - start
    sloped = span > 1e-9
    safe = np.where(sloped, span, 1.0)
    ramp = (_bend(at - start, scale) - _bend(at - end, scale)) / safe
    return np.where(sloped, ramp, _step(at - start, scale))


def _corners(bounds: Sequence[Bounds] | np.ndarray) -> np.ndarray:
    """The four corners of each date, in years (a row for each date). A date's last day is in it: it ends where
    the next day starts"""
    days = np.asarray(bounds, dtype=np.float64).reshape(-1, 4)
    if days.size and not (np.diff(days, axis=1) >= 0).all():
        raise ValueError(
            "The bounds of a date are in order: earliest_fuzzy <= earliest_strict <= latest_strict <= latest_fuzzy"
        )
    return year_of(days + np.array([0.0, 0.0, 1.0, 1.0]))


def blurred(bounds: Sequence[Bounds] | np.ndarray, ring: Ring) -> np.ndarray:
    """For each date (a row of four day numbers), what it is at each place of the ring, **not** at length one: a
    row for each date, a column for each place"""
    corners = _corners(bounds)
    made = np.zeros((len(corners), ring.dimension), dtype=np.float64)
    if not len(corners):
        return made
    reach = _REACH * ring.scale
    # (the centres each date is worked out at: from the first before its blur begins, as many as reach its end)
    first = np.floor((corners[:, 0] - reach) / ring.width).astype(np.int64)
    count = np.ceil((corners[:, 3] + reach) / ring.width).astype(np.int64) - first + 1
    # (dates of a like span together, so that a few long periods do not make every date as wide to work out)
    order = np.argsort(count, kind="stable")
    start = 0
    while start < len(order):
        widest = int(count[order[start]])
        size = max(1, _AT_ONCE // widest)
        rows = order[start : start + size]
        widest = int(count[rows[-1]])
        steps = np.arange(widest, dtype=np.int64)[None, :]
        centres = first[rows, None] + steps
        at = centres * ring.width
        a, b, c, d = (corners[rows, n : n + 1] for n in range(4))
        values = _rise(at, a, b, ring.scale) - _rise(at, c, d, ring.scale)
        # (past a date's own reach there is nothing of it: rounding is not added)
        values[steps >= count[rows, None]] = 0.0
        # (the most of the date at each place, not the sum: a date longer than the ring is at every place once,
        # and no part of it counts twice)
        np.maximum.at(made, (rows[:, None], centres % ring.dimension), values)
        start += size
    return made


def vectors(bounds: Sequence[Bounds] | np.ndarray, ring: Ring) -> np.ndarray:
    """The vector of each date, at length one: a row for each"""
    made = blurred(bounds, ring)
    return made / np.linalg.norm(made, axis=1, keepdims=True)


def summed(rows: np.ndarray) -> np.ndarray | None:
    """The vector of an item from those of its dates (rows of `vectors`): added, at length one; None if there is
    none"""
    if not len(rows):
        return None
    total = rows.sum(axis=0)
    return total / float(np.linalg.norm(total))


def vector(dates: Iterable[Bounds], ring: Ring) -> np.ndarray | None:
    """The vector of an item with these dates, at length one: each date at length one, added. None if it has no
    date (no vector)"""
    return summed(vectors(list(dates), ring))


def of_items(
    bounds: Sequence[Bounds] | np.ndarray,
    items: Sequence[int] | np.ndarray,
    count: int,
    ring: Ring,
) -> np.ndarray:
    """The vectors of `count` items from all their dates at once: `items[n]` is the item (0 to `count - 1`) that
    the date `bounds[n]` is of, and a date of several items is given once for each. A row for each item, at length
    one, as `vector` gives it; a row of zeros for an item with no date"""
    made = np.zeros((count, ring.dimension), dtype=np.float64)
    if len(items):
        np.add.at(made, np.asarray(items, dtype=np.int64), vectors(bounds, ring))
    lengths = np.linalg.norm(made, axis=1, keepdims=True)
    return np.divide(made, lengths, out=np.zeros_like(made), where=lengths > 0)
