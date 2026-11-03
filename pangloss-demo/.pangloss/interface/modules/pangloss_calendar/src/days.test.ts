import { expect, test } from "vitest";
import {
  dayHref,
  monthFromParams,
  nameFromParams,
  nameOf,
  nextMonth,
  parseRef,
  previousMonth,
  refOf,
  sayDate,
  sayMonth,
  weekHeadings,
} from "./days";

const english = (_key: string, text: string, params: Record<string, string | number> = {}) =>
  text.replace(/\{(\w+)\}/g, (whole, name: string) => (name in params ? String(params[name]) : whole));

test("a day as the API writes it is read, and written back the same", () => {
  expect(parseRef("J1500-03-02")).toEqual({ calendar: "julian", year: 1500, month: 3, day: 2 });
  expect(parseRef("G1500-03-12")).toEqual({ calendar: "gregorian", year: 1500, month: 3, day: 12 });
  expect(parseRef("J-100-01-01")).toEqual({ calendar: "julian", year: -100, month: 1, day: 1 });
  expect(parseRef("1500-03-02")).toBeUndefined();
  expect(refOf({ calendar: "julian", year: 1500, month: 3, day: 2 })).toBe("J1500-03-02");
  expect(refOf({ calendar: "gregorian", year: -100, month: 12, day: 31 })).toBe("G-100-12-31");
});

test("a day the API sent is named in either calendar", () => {
  const day = { jdn: 2268994, julian: "J1500-03-02", gregorian: "G1500-03-12", weekday: 1, weekday_name: "monday" };
  expect(nameOf(day, "julian").day).toBe(2);
  expect(nameOf(day, "gregorian").day).toBe(12);
  expect(dayHref(nameOf(day, "gregorian"))).toBe("/calendar/gregorian/1500/3/12");
});

test("the parts of an address are a month or a day only when they make sense", () => {
  expect(monthFromParams({ calendar: "julian", year: "1500", month: "3" })).toEqual({ calendar: "julian", year: 1500, month: 3 });
  expect(monthFromParams({ calendar: "julian", year: "-45", month: "12" })?.year).toBe(-45);
  expect(monthFromParams({ calendar: "hebrew", year: "1500", month: "3" })).toBeUndefined();
  expect(monthFromParams({ calendar: "julian", year: "1500", month: "13" })).toBeUndefined();
  expect(monthFromParams({ calendar: "julian", year: "abc", month: "1" })).toBeUndefined();
  expect(nameFromParams({ calendar: "gregorian", year: "1500", month: "3", day: "12" })).toEqual({
    calendar: "gregorian",
    year: 1500,
    month: 3,
    day: 12,
  });
  expect(nameFromParams({ calendar: "gregorian", year: "1500", month: "3", day: "32" })).toBeUndefined();
  expect(nameFromParams({ calendar: "gregorian", year: "1500", month: "3", day: "x" })).toBeUndefined();
});

test("the months step over the year", () => {
  expect(previousMonth(1500, 1)).toEqual([1499, 12]);
  expect(nextMonth(1500, 12)).toEqual([1501, 1]);
  expect(nextMonth(1500, 3)).toEqual([1500, 4]);
});

test("days and months are said in the language, and the week starts on Monday", () => {
  expect(sayDate({ calendar: "julian", year: 1500, month: 3, day: 2 }, "en", english)).toBe("2 March 1500");
  expect(sayMonth(1500, 3, "en", english)).toBe("March 1500");
  expect(sayMonth(1500, 3, "de", english)).toBe("März 1500");
  expect(weekHeadings("en")).toEqual(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]);
});
