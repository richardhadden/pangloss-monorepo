import { expect, test } from "vitest";
import type { EmbeddedField, ModelDefinition, ModelDefinitions, RelationOption } from "../types";
import { clipValue, fitEdge, fitsEmbedded, fitsRelation, forPaste, nodeIds, outline } from "./clipboard";

const model = (name: string, extra: Partial<ModelDefinition> = {}) =>
  ({ name, kind: "Document", parent: null, abstract: false, concreteTypes: [name], fields: [], incoming: [], ...extra }) as ModelDefinition;

const doc = (type: string): RelationOption => ({ kind: "document", type, edgeModel: null });
const person: RelationOption = { kind: "entity", type: "Person", edgeModel: "Certainty" };
const relation = (name: string, options: RelationOption[], many = true) =>
  ({ name, key: name, kind: "relation", many, options }) as never;
const negative = (inside: RelationOption[]): RelationOption => ({
  kind: "semanticSpace",
  type: "Negative",
  edgeModel: null,
  params: { T: { typeVar: "T", options: inside } },
});
const when = { name: "when", key: "when", kind: "embedded", types: ["Day"] } as unknown as EmbeddedField;

// Activity has people and a date; a Factoid's statements are Activities, plain or Negative; a Note
// holds Transfers, which a Factoid does not
const definitions = {
  models: {
    Activity: model("Activity", {
      fields: [relation("people", [person]), when],
      incoming: [{ name: "cited_in", key: "cited_in" }] as never,
    }),
    Transfer: model("Transfer"),
    Negative: model("Negative", {
      kind: "SemanticSpace",
      fields: [relation("contents", [{ kind: "typeVar", name: "T", edgeModel: null }])],
    }),
    Person: model("Person", { kind: "Entity" }),
    Day: model("Day", { kind: "Embedded" }),
    Week: model("Week", { kind: "Embedded" }),
  },
  enums: {},
} as unknown as ModelDefinitions;

const statements = [doc("Activity"), negative([doc("Activity")])];

const activity = {
  type: "Activity",
  id: "a1",
  label: "Meeting",
  meta: { created_by: "x" },
  cited_in: [{ type: "Note", id: "n9" }],
  people: [{ type: "Person", id: "p1", label: "Alice", meta: {}, extra: 1, edgeProperties: { level: 2 } }],
  when: { type: "Day", id: "d1", day: 3 },
};

test("what is kept leaves out what the API only reads, at every level; an entity is a reference", () => {
  expect(clipValue(definitions, activity)).toEqual({
    type: "Activity",
    id: "a1",
    label: "Meeting",
    people: [{ type: "Person", id: "p1", label: "Alice", edgeProperties: { level: 2 } }],
    when: { type: "Day", id: "d1", day: 3 },
  });
});

test("a thing fits where its type is offered, and all inside it is allowed there too", () => {
  const kept = clipValue(definitions, activity);
  expect(fitsRelation(definitions, kept, statements, {})).toBe(true);
  expect(fitsRelation(definitions, { type: "Transfer" }, statements, {})).toBe(false);
  // (a space fits by what is inside it: an Activity is allowed in the factoid's Negative, a Transfer not)
  expect(fitsRelation(definitions, { type: "Negative", contents: [kept] }, statements, {})).toBe(true);
  expect(fitsRelation(definitions, { type: "Negative", contents: [{ type: "Transfer" }] }, statements, {})).toBe(false);
  // (an Activity whose date is a Week does not fit, nor one with a Transfer among its people)
  expect(fitsRelation(definitions, { ...kept, when: { type: "Week" } }, statements, {})).toBe(false);
  expect(fitsRelation(definitions, { ...kept, people: [{ type: "Transfer" }] }, statements, {})).toBe(false);
  // (an entity fits a relation to its type, once it is chosen)
  expect(fitsRelation(definitions, { type: "Person", id: "p1" }, [person], {})).toBe(true);
  expect(fitsRelation(definitions, { type: "Person" }, [person], {})).toBe(false);
  expect(fitsRelation(definitions, { type: "Person", id: "p1" }, statements, {})).toBe(false);
  expect(fitsEmbedded(definitions, { type: "Day" }, when)).toBe(true);
  expect(fitsEmbedded(definitions, { type: "Week" }, when)).toBe(false);
});

test("pasted into the document it came from, a node keeps an id that is not there already; elsewhere it has none", () => {
  const kept = clipValue(definitions, activity);
  expect(forPaste(definitions, kept, true, new Set())).toMatchObject({ id: "a1", when: { id: "d1" } });
  // (copied, the first is still there: the copy is new; a part that is not there any more keeps its id)
  const again = forPaste(definitions, kept, true, new Set(["a1"]));
  expect(again).not.toHaveProperty("id");
  expect(again.when).toEqual({ type: "Day", id: "d1", day: 3 });
  const elsewhere = forPaste(definitions, kept, false, new Set());
  expect(elsewhere).not.toHaveProperty("id");
  expect(elsewhere.when).toEqual({ type: "Day", day: 3 });
  // (an entity is a reference, and keeps its id wherever it goes)
  expect(elsewhere.people).toEqual([{ type: "Person", id: "p1", label: "Alice", edgeProperties: { level: 2 } }]);
});

test("the ids of a document are its nodes', not the entities'", () => {
  expect([...nodeIds(definitions, { type: "Factoid", id: "f1", statements: [clipValue(definitions, activity)] })].sort()).toEqual([
    "a1",
    "d1",
    "f1",
  ]);
});

test("an entity keeps the properties of its relation only where the relation has the same", () => {
  const alice = { type: "Person", id: "p1", edgeProperties: { level: 2 } };
  expect(fitEdge(alice, [person], {}, "Certainty")).toEqual(alice);
  expect(fitEdge(alice, [{ ...person, edgeModel: null }], {}, "Certainty")).toEqual({ type: "Person", id: "p1" });
});

test("the outline is each thing with a type, under what it is in", () => {
  expect(outline(definitions, { type: "Negative", contents: [clipValue(definitions, activity)] })).toEqual([
    { depth: 0, type: "Negative", label: undefined, field: undefined },
    { depth: 1, type: "Activity", label: "Meeting", field: "contents" },
    { depth: 2, type: "Person", label: "Alice", field: "people" },
    { depth: 2, type: "Day", label: undefined, field: "when" },
  ]);
  expect(outline(definitions, { type: "Negative", contents: [activity] }, 1)).toHaveLength(2);
});
