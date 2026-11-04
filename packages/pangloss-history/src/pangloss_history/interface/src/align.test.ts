import { expect, test } from "vitest";
import { align, changedRows, mergeOrder } from "./align";
import { DEFINITIONS } from "./fixtures";

const rome = { id: "p-rome", type: "Place", label: "Rome" };
const aachen = { id: "p-aachen", type: "Place", label: "Aachen" };
const john = { id: "john", type: "Person", label: "John" };

const v1 = {
  type: "Factoid",
  label: "Crowned",
  text: "The king is crowned",
  statements: [{ id: "s1", type: "Statement", label: "One", text: "a", about: john }],
  places: [rome],
};
const v2 = {
  type: "Factoid",
  label: "Crowned",
  text: "The emperor is crowned",
  year: 800,
  statements: [
    { id: "s1", type: "Statement", label: "One", text: "b", about: john },
    { id: "s2", type: "Statement", label: "Two", text: "c" },
  ],
  places: [rome, aachen],
};
const v3 = { type: "Factoid", label: "Crowned", text: "The emperor is crowned", statements: [], places: [aachen] };

const summary = (rows: ReturnType<typeof align>) =>
  rows.map((row) => [row.key, row.kind, row.depth, row.cells.map((cell) => cell.mark).join(" ")]);

test("the rows are the model's fields in order, and the parts matched by id with what is in them", () => {
  expect(summary(align(DEFINITIONS, "Factoid", [v1, v2, v3]))).toEqual([
    [".label", "field", 0, "same same same"],
    [".text", "field", 0, "same changed same"],
    [".year", "field", 0, "absent added removed"],
    [".statements[s1]", "head", 0, "same same removed"],
    [".statements[s1].label", "field", 1, "same same removed"],
    [".statements[s1].text", "field", 1, "same changed removed"],
    [".statements[s1].about[john]", "head", 1, "same same removed"],
    [".statements[s2]", "head", 0, "absent added removed"],
    [".statements[s2].label", "field", 1, "absent added removed"],
    [".statements[s2].text", "field", 1, "absent added removed"],
    [".places[p-rome]", "head", 0, "same same removed"],
    [".places[p-aachen]", "head", 0, "absent added same"],
  ]);
});

test("a head says the name of its field only as the first of the field's parts; an entity is a chip with nothing under it", () => {
  const rows = align(DEFINITIONS, "Factoid", [v2]);
  const places = rows.filter((row) => row.field.key === "places");
  expect(places.map((row) => [row.first, row.entity])).toEqual([
    [true, true],
    [false, true],
  ]);
  const nested = rows.find((row) => row.key === ".statements[s1].text")!;
  expect(nested.trail.map((step) => (step.kind === "field" ? step.field.key : `${step.type}:${step.label}`))).toEqual([
    "statements",
    "Statement:One",
  ]);
  expect(nested.ancestors).toEqual([".statements[s1]"]);
});

test("a part that is made another type, or given another label, is changed", () => {
  const before = { type: "Factoid", statements: [{ id: "s1", type: "Statement", label: "One" }] };
  const after = { type: "Factoid", statements: [{ id: "s1", type: "Statement", label: "Uno" }] };
  expect(align(DEFINITIONS, "Factoid", [before, after])[0]!.cells.map((cell) => cell.mark)).toEqual(["same", "changed"]);
});

test("an embedded object is a part of its own, matched by its id or its place", () => {
  const rows = align(DEFINITIONS, "Factoid", [
    { type: "Factoid", when: { type: "Date", year: 800 } },
    { type: "Factoid", when: { type: "Date", year: 801 } },
  ]);
  expect(summary(rows)).toEqual([
    [".when[#0]", "head", 0, "same same"],
    [".when[#0].year", "field", 1, "same changed"],
  ]);
});

test("the parts of all versions are in one order: each version's, and those new to it after the one they follow", () => {
  expect(mergeOrder([["a", "b", "c"], ["a", "x", "c"], ["y", "a"]])).toEqual(["y", "a", "b", "x", "c"]);
});

test("what a restore changes: the rows that differ, but not those inside a part added or removed whole", () => {
  const rows = changedRows(DEFINITIONS, "Factoid", v2, v1);
  expect(rows.map((row) => [row.key, row.cells[1]!.mark])).toEqual([
    [".text", "changed"],
    [".year", "removed"],
    [".statements[s1].text", "changed"],
    [".statements[s2]", "removed"],
    [".places[p-aachen]", "removed"],
  ]);
});

test("an unknown type has no rows", () => {
  expect(align(DEFINITIONS, "Nothing", [v1])).toEqual([]);
});
