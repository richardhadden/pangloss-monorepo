import { expect, test } from "vitest";
import type { ModelDefinition, ModelDefinitions } from "../types";
import { arrangeByDate, byYear, dateInWords, isDateable, yearOfDay, yearSpan } from "./dating";
import type { IncomingEntry } from "./dating";

const model = (name: string, traits?: string[]) =>
  ({ name, kind: "Document", fields: [], incoming: [], traits }) as unknown as ModelDefinition;
const definitions = {
  models: {
    Birth: model("Birth", ["Dateable", "SingleDateable"]),
    Office: model("Office", ["Dateable"]),
    Note: model("Note", []),
    Old: model("Old"),
  },
  enums: {},
} as unknown as ModelDefinitions;

const entry = (type: string, label: string, dated: Record<string, unknown> = {}): IncomingEntry => ({
  key: "concernsReverse",
  name: "concerns",
  item: { type, id: label, label, ...dated },
});

test("a model is dateable by its trait (an export without traits has none)", () => {
  expect(isDateable(definitions, "Birth")).toBe(true);
  expect(isDateable(definitions, "Note")).toBe(false);
  expect(isDateable(definitions, "Old")).toBe(false);
  expect(isDateable(definitions, "Nothing")).toBe(false);
  expect(isDateable(definitions, undefined)).toBe(false);
});

test("the year of a day number", () => {
  expect(yearOfDay(2451545)).toBe(2000);
  expect(yearOfDay(2268924)).toBe(1500);
  expect(yearOfDay(2268923)).toBe(1499);
  expect(yearOfDay(1705063)).toBe(-44);
});

test("what refers to an item is dated in order, not known, or not dateable", () => {
  const arranged = arrangeByDate(
    [
      entry("Note", "a note"),
      entry("Birth", "late", { dateSortDay: 2269000, dateText: "1500" }),
      entry("Birth", "unknown", { dateSortDay: 1721426, dateText: "?" }),
      entry("Office", "early, long", { dateSortDay: 2268000, dateEndSortDay: 2275000, dateText: "1497–1517" }),
      entry("Office", "early, short", { dateSortDay: 2268000, dateEndSortDay: 2268100, dateText: "1497" }),
      entry("Birth", "never copied"),
    ],
    definitions,
  );
  expect(arranged.dated.map((e) => e.item.label)).toEqual(["early, short", "early, long", "late"]);
  expect(arranged.unknown.map((e) => e.item.label)).toEqual(["unknown", "never copied"]);
  expect(arranged.undated.map((e) => e.item.label)).toEqual(["a note"]);
});

test("the span of the timeline: a period to the year of its end", () => {
  const office = entry("Office", "o", { dateSortDay: 2268924, dateEndSortDay: 2268924 + 3652, dateText: "1500–1510" });
  const birth = entry("Birth", "b", { dateSortDay: 2268924 + 365 * 20 + 30, dateText: "1520" });
  expect(yearSpan([office, birth])).toEqual([1500, 1520]);
  expect(yearSpan([])).toBeUndefined();
});

test("the dated entries under their years", () => {
  const a = entry("Birth", "a", { dateSortDay: 2268924, dateText: "1500" });
  const b = entry("Birth", "b", { dateSortDay: 2268924 + 40, dateText: "1500-02" });
  const c = entry("Birth", "c", { dateSortDay: 2268924 + 400, dateText: "1501" });
  expect(byYear([a, b, c]).map(([year, group]) => [year, group.map((e) => e.item.label)])).toEqual([
    [1500, ["a", "b"]],
    [1501, ["c"]],
  ]);
});

const fill = (text: string, params: Record<string, string | number> = {}) =>
  text.replace(/\{(\w+)\}/g, (_, name: string) => String(params[name]));
const english = { language: "en", t: (_key: string, text: string, params?: Record<string, string | number>) => fill(text, params) };

test.each([
  ["1500", "1500"],
  ["1500-03", "March 1500"],
  ["1500-03-02", "2 March 1500"],
  ["-44-03-15", "15 March -44"],
  ["≥ 1490", "not before 1490"],
  ["≤ 1502-06", "not after June 1502"],
  ["1500–1502", "1500 to 1502"],
  ["1500–…", "1500 to ongoing"],
  ["[1500–1502]–1520", "(1500 to 1502) to 1520"],
  ["↻ 1500–1520", "↻ 1500 to 1520"],
  ["?", "unknown"],
  ["1500~", "1500~"],
])("the date %s in words: %s", (text, words) => {
  expect(dateInWords(text, english)).toBe(words);
});

test("the date in words in another language: its months and its texts", () => {
  const german = {
    language: "de",
    t: (key: string, text: string, params?: Record<string, string | number>) =>
      fill(key === "date_day_month_year" ? "{day}. {month} {year}" : key === "date_range" ? "{from} bis {to}" : text, params),
  };
  expect(dateInWords("1500-03-02–1500-04", german)).toBe("2. März 1500 bis April 1500");
});
