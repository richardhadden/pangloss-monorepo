/**
 * Bars across a week of the month grid, for dates that cover several days: each is laid in a lane (a row of
 * the grid under the day numbers), the first lane it fits in, so that bars that do not overlap share one.
 */

export interface Ranged<T> {
  item: T;
  /** The first and last day (day numbers) the bar is for, already cut to the month */
  first: number;
  last: number;
  /** Where the date really starts and ends (it may reach outside the month) */
  trueFirst: number;
  trueLast: number;
}

export interface Bar<T> {
  item: T;
  /** Columns of the week, 0 (Monday) to 6 */
  start: number;
  end: number;
  lane: number;
  /** Whether the date starts in this week (else it is carried over from before, and its bar is open at the left) */
  startsHere: boolean;
  /** Whether it ends in this week (else the bar is open at the right) */
  endsHere: boolean;
}

/**
 * The bars of the ranges that meet the week starting on `weekFirst` (a Monday's day number), sorted by their
 * start and, for the same start, the longest first, each in the first free lane
 */
export function weekBars<T>(ranges: readonly Ranged<T>[], weekFirst: number): Bar<T>[] {
  const weekLast = weekFirst + 6;
  const here = ranges
    .filter((range) => range.first <= weekLast && range.last >= weekFirst)
    .map((range) => ({
      range,
      start: Math.max(range.first, weekFirst) - weekFirst,
      end: Math.min(range.last, weekLast) - weekFirst,
    }))
    .sort((a, b) => a.start - b.start || b.end - a.end);
  const laneEnds: number[] = [];
  return here.map(({ range, start, end }) => {
    let lane = laneEnds.findIndex((last) => last < start);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(end);
    } else {
      laneEnds[lane] = end;
    }
    return {
      item: range.item,
      start,
      end,
      lane,
      startsHere: range.trueFirst >= weekFirst,
      endsHere: range.trueLast <= weekLast,
    };
  });
}

/** The day number of the Monday a row of the grid starts on (the row has at least one day of the month) */
export function weekStart(week: readonly (number | null)[]): number {
  const index = week.findIndex((jdn) => jdn !== null);
  return (week[index] as number) - index;
}
