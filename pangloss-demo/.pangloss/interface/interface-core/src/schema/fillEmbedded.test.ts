import { expect, test } from "vitest";
import type { EmbeddedField, ModelDefinition, ModelDefinitions, RelationOption } from "../types";
import { fillEmbedded, reachesEmbedded } from "./formValue";

const model = (name: string, kind: ModelDefinition["kind"], fields: object[] = [], concreteTypes: string[] = [name]) =>
  ({ name, kind, abstract: false, concreteTypes, typeParameters: [], fields, interfaceMeta: null }) as unknown as ModelDefinition;
const date = (key: string, types = ["ExactDate", "Period"]) => ({ name: key, key, kind: "embedded", model: "Date", types });
const relation = (key: string, options: RelationOption[], many = true) => ({ name: key, key, kind: "relation", many, options });
const document = (type: string): RelationOption => ({ kind: "document", type, edgeModel: null });
const entity = (type: string): RelationOption => ({ kind: "entity", type, edgeModel: null });
const negative = (options: RelationOption[]) =>
  ({ kind: "semanticSpace", type: "Negative", edgeModel: null, params: { T: { typeVar: "T", options } } }) as RelationOption;

const definitions = {
  models: {
    Factoid: model("Factoid", "Document", [
      { name: "year", key: "year", kind: "literal", type: { type: "int" } },
      relation("statements", [document("Statement"), negative([document("Statement")])]),
      relation("source", [entity("Source")], false),
    ]),
    Statement: model("Statement", "Document", [], ["Activity"]),
    Activity: model("Activity", "Document", [date("date"), relation("involves", [entity("Person")])]),
    Negative: model("Negative", "SemanticSpace", [relation("contents", [{ kind: "typeVar", name: "T", edgeModel: null }])]),
    Person: model("Person", "Entity", [date("born")]),
    Period: model("Period", "Embedded", [date("start"), date("end")]),
    Note: model("Note", "Document", [relation("about", [entity("Person")])]),
  },
  enums: {},
} as unknown as ModelDefinitions;

const DAY = { type: "ExactDate", year: 1500, month: 3, day: 2 };
const pick = (field: EmbeddedField) => (field.types.includes("ExactDate") ? DAY : undefined);

test("a date is given to each item that can have one, through relations and semantic spaces, not to an entity", () => {
  const item = {
    type: "Factoid",
    statements: [
      { type: "Activity", involves: [{ type: "Person", id: "p1" }] },
      { type: "Negative", contents: [{ type: "Activity" }] },
      { type: "Activity", date: { type: "Period" } },
    ],
  };
  const filled = fillEmbedded(definitions, item, pick);
  expect(filled).toEqual({
    type: "Factoid",
    statements: [
      { type: "Activity", date: DAY, involves: [{ type: "Person", id: "p1" }] },
      { type: "Negative", contents: [{ type: "Activity", date: DAY }] },
      // (one that is there is kept, and the start and end of a period are not gone into)
      { type: "Activity", date: { type: "Period" } },
    ],
  });
  // (what was given is not changed)
  expect(item.statements[0]).toEqual({ type: "Activity", involves: [{ type: "Person", id: "p1" }] });
  // (an entity being made is filled: a feast made on a day)
  expect(fillEmbedded(definitions, { type: "Person" }, pick)).toEqual({ type: "Person", born: DAY });
});

test("a document reaches a date through what it can hold, but not through an entity", () => {
  const accepts = (field: EmbeddedField) => field.types.includes("ExactDate");
  expect(reachesEmbedded(definitions, "Factoid", accepts)).toBe(true);
  expect(reachesEmbedded(definitions, "Note", accepts)).toBe(false);
  expect(reachesEmbedded(definitions, "Factoid", () => false)).toBe(false);
});
