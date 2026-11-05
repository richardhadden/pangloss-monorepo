import { expect, test } from "vitest";
import type { ModelDefinition, ModelDefinitions } from "../types";
import { arrangeByDate, inYears, isDateable, yearOfDay, yearSpan } from "./dating";
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

test("the years of the slider: a period is in them if any of it is", () => {
  const office = entry("Office", "o", { dateSortDay: 2268924, dateEndSortDay: 2268924 + 3652, dateText: "1500–1510" });
  const birth = entry("Birth", "b", { dateSortDay: 2268924 + 365 * 20 + 30, dateText: "1520" });
  expect(yearSpan([office, birth])).toEqual([1500, 1520]);
  expect(yearSpan([])).toBeUndefined();
  expect(inYears(office, 1505, 1530)).toBe(true);
  expect(inYears(office, 1511, 1530)).toBe(false);
  expect(inYears(birth, 1500, 1519)).toBe(false);
});
