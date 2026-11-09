import { expect, test } from "vitest";
import type { FieldDefinition, ModelDefinition, ModelDefinitions } from "../types";
import { shortenLabel } from "./lookup";
import { acceptedTypes, editableFields, reflowHelp } from "./typeInfo";

const base = { description: null, dbField: false, readOnly: false, required: true, nullable: false };
const model = (name: string, parent: string | null = null, over: Partial<ModelDefinition> = {}) =>
  ({ name, kind: "Entity", abstract: false, parent, concreteTypes: [name], fields: [], interfaceMeta: null, ...over }) as ModelDefinition;
const definitions: ModelDefinitions = {
  models: { Agent: model("Agent"), Person: model("Person", "Agent"), Place: model("Place") },
  enums: {},
};
const relation = (options: unknown[]) =>
  ({ ...base, name: "r", key: "r", kind: "relation", many: false, reverseName: "x", options, validators: [], subclasses: [] }) as FieldDefinition;
const literal = (type: unknown) =>
  ({ ...base, name: "l", key: "l", kind: "literal", type, validators: [] }) as FieldDefinition;

test("a relation accepts the types of its options, without what is inside a wrapper", () => {
  const field = relation([
    { kind: "entity", type: "Place", edgeModel: null },
    {
      kind: "reifiedRelation",
      type: "Certainty",
      edgeModel: null,
      params: { T: { typeVar: "T", options: [{ kind: "entity", type: "Place", edgeModel: null }] } },
    },
  ]);
  expect(acceptedTypes(definitions, field)).toEqual([
    { kind: "model", name: "Place" },
    { kind: "model", name: "Certainty" },
  ]);
});

test("a type below another that is accepted is not listed", () => {
  const field = relation([
    { kind: "entity", type: "Agent", edgeModel: null },
    { kind: "entity", type: "Person", edgeModel: null },
  ]);
  expect(acceptedTypes(definitions, field)).toEqual([{ kind: "model", name: "Agent" }]);
});

test("a literal is what kind of value it is, and a list what its items are", () => {
  expect(acceptedTypes(definitions, literal({ type: "str", format: "url" }))).toEqual([{ kind: "scalar", scalar: "str" }]);
  expect(acceptedTypes(definitions, literal({ type: "enum", enum: "Colour" }))).toEqual([{ kind: "enum", name: "Colour" }]);
  expect(acceptedTypes(definitions, literal({ type: "literal", values: ["a", 1] }))).toEqual([
    { kind: "value", value: "a" },
    { kind: "value", value: "1" },
  ]);
  expect(
    acceptedTypes(definitions, { ...base, name: "l", key: "l", kind: "list", item: { type: "int" }, validators: [], itemValidators: [] }),
  ).toEqual([{ kind: "scalar", scalar: "int" }]);
});

test("an embedded field accepts its model, or the topmost of its types", () => {
  const embedded = (over: object) => ({ ...base, name: "e", key: "e", kind: "embedded", model: null, types: [], ...over }) as FieldDefinition;
  expect(acceptedTypes(definitions, embedded({ model: "Agent", types: ["Person"] }))).toEqual([{ kind: "model", name: "Agent" }]);
  expect(acceptedTypes(definitions, embedded({ types: ["Agent", "Person", "Place"] }))).toEqual([
    { kind: "model", name: "Agent" },
    { kind: "model", name: "Place" },
  ]);
});

test("the line breaks of a docstring are spaces, and a blank line is a new paragraph", () => {
  expect(reflowHelp("One line\n    and its rest.\n\n    Another\n    one.\n")).toBe("One line and its rest.\n\nAnother one.");
});

test("the fields listed are those a form shows", () => {
  const fields = [
    { ...base, name: "a", key: "a", kind: "unknown" },
    { ...base, name: "b", key: "b", kind: "unknown", dbField: true },
    { ...base, name: "c", key: "c", kind: "unknown", readOnly: true },
    { ...base, name: "d", key: "d", kind: "unknown" },
  ] as FieldDefinition[];
  const shown = editableFields(
    model("X", null, { fields, interfaceMeta: { hideOnForms: ["d"] } as ModelDefinition["interfaceMeta"] }),
  );
  expect(shown.map((field) => field.name)).toEqual(["a"]);
});

test("a label is shortened at a word for the title of a window", () => {
  expect(shortenLabel("Short")).toBe("Short");
  expect(shortenLabel("The letter from Maximilian to Marie of Burgundy about the wedding")).toBe("The letter from Maximilian to Marie of…");
  expect(shortenLabel("x".repeat(50))).toBe(`${"x".repeat(40)}…`);
  expect(shortenLabel("two\n  lines")).toBe("two lines");
});
