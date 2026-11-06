import { expect, test } from "vitest";
import type { ModelDefinitions } from "../types";
import { comparableItem, entityReferences, refreshReferences, sameValue } from "./stash";

const definitions = {
  models: {
    Person: { name: "Person", kind: "Entity" },
    Place: { name: "Place", kind: "Entity" },
    Factoid: { name: "Factoid", kind: "Document" },
    InRole: { name: "InRole", kind: "ReifiedRelation" },
  },
  enums: {},
} as unknown as ModelDefinitions;

const factoid = {
  type: "Factoid",
  label: "Meeting",
  author: [{ type: "Person", id: "p1", label: "Alice" }],
  attendees: [
    { type: "InRole", role: "host", target: [{ type: "Person", id: "p2", label: "Bob" }] },
    { type: "InRole", role: "guest", target: [{ type: "Person", id: "p1", label: "Alice" }] },
  ],
  at: [{ type: "Place", id: "x1", label: "Ghent", edgeProperties: { certainty: 2 } }],
  // (an entity not yet chosen has no id: nothing to ask about)
  witness: [{ type: "Person" }],
};

test("values are the same when lists are the same in order and objects have the same keys, in any order", () => {
  expect(sameValue({ a: 1, b: [1, { c: "x" }] }, { b: [1, { c: "x" }], a: 1 })).toBe(true);
  expect(sameValue({ a: [1, 2] }, { a: [2, 1] })).toBe(false);
  expect(sameValue({ a: 1 }, { a: 1, b: undefined })).toBe(false);
  expect(sameValue([], {})).toBe(false);
  expect(sameValue(null, {})).toBe(false);
});

test("the entities an item refers to are found anywhere in it, each once", () => {
  expect(entityReferences(definitions, factoid)).toEqual([
    { type: "Person", id: "p1", label: "Alice" },
    { type: "Person", id: "p2", label: "Bob" },
    { type: "Place", id: "x1", label: "Ghent" },
  ]);
});

test("an entity that is gone is taken out of its list, and one renamed gets its new label; the item is not changed", () => {
  const before = structuredClone(factoid);
  const refreshed = refreshReferences(definitions, factoid, [
    { id: "p1", type: "Person", label: "Alice Smith" },
    { id: "x1", type: "Place", label: "Ghent" },
  ]);
  expect(refreshed.gone).toEqual([{ type: "Person", id: "p2", label: "Bob" }]);
  expect(refreshed.renamed).toEqual([{ type: "Person", id: "p1", label: "Alice Smith", was: "Alice" }]);
  expect(refreshed.value.author).toEqual([{ type: "Person", id: "p1", label: "Alice Smith" }]);
  expect((refreshed.value.attendees as { target: unknown[] }[]).map((role) => role.target)).toEqual([
    [],
    [{ type: "Person", id: "p1", label: "Alice Smith" }],
  ]);
  // (what is on the edge to it stays)
  expect(refreshed.value.at).toEqual([{ type: "Place", id: "x1", label: "Ghent", edgeProperties: { certainty: 2 } }]);
  expect(refreshed.value.witness).toEqual([{ type: "Person" }]);
  expect(factoid).toEqual(before);
});

test("an item compares as what would be sent, with empty lists the same as none", () => {
  const definitions = { models: { Note: { name: "Note", kind: "Document", incoming: [] } }, enums: {} } as unknown as ModelDefinitions;
  expect(sameValue(comparableItem(definitions, { type: "Note", people: [], label: "" }), comparableItem(definitions, { type: "Note" }))).toBe(true);
  expect(sameValue(comparableItem(definitions, { type: "Note", label: "A" }), comparableItem(definitions, { type: "Note" }))).toBe(false);
});
