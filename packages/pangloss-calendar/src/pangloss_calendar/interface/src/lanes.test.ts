import { expect, test } from "vitest";
import { weekBars, weekStart } from "./lanes";

const range = (item: string, first: number, last: number, trueFirst = first, trueLast = last) => ({
  item,
  first,
  last,
  trueFirst,
  trueLast,
});

test("a week starts on the Monday before its first day of the month", () => {
  expect(weekStart([null, null, null, null, null, null, 100])).toBe(94);
  expect(weekStart([101, 102, 103, 104, 105, 106, 107])).toBe(101);
});

test("bars are cut to the week, open at the end that goes on, and share a lane when they do not overlap", () => {
  const bars = weekBars([range("a", 95, 103), range("b", 104, 106), range("c", 96, 97)], 100);
  // (a: carried over from the week before, ends here; b: starts here, open at the right; c: not in this week)
  expect(bars.map((bar) => [bar.item, bar.start, bar.end, bar.lane, bar.startsHere, bar.endsHere])).toEqual([
    ["a", 0, 3, 0, false, true],
    ["b", 4, 6, 0, true, true],
  ]);
});

test("bars that overlap get lanes of their own, the longest first", () => {
  const bars = weekBars([range("short", 101, 102), range("long", 101, 105), range("later", 103, 104)], 100);
  expect(bars.map((bar) => [bar.item, bar.lane])).toEqual([
    ["long", 0],
    ["short", 1],
    ["later", 1],
  ]);
});

test("a date cut to the month but starting before it is open at the left", () => {
  const [bar] = weekBars([range("x", 100, 102, 90, 102)], 100);
  expect(bar!.startsHere).toBe(false);
  expect(bar!.endsHere).toBe(true);
});
