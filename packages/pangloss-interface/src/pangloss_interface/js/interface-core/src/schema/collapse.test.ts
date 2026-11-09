import { expect, test, vi } from "vitest";
import type {
  CollapseRule,
  FieldDefinition,
  InterfaceMeta,
  ModelDefinition,
  ModelDefinitions,
} from "../types";
import { collapsedView, labelledContents } from "./collapse";

const field = (key: string, kind: FieldDefinition["kind"] = "literal") =>
  ({
    name: key,
    key,
    kind,
    description: null,
    dbField: true,
    readOnly: false,
    required: false,
    nullable: false,
  }) as FieldDefinition;

const meta = (collapse: InterfaceMeta["collapse"]): InterfaceMeta => ({
  colour: null,
  listPage: null,
  itemPage: null,
  viewCard: null,
  editCard: null,
  collapse,
});

const model = (
  name: string,
  kind: ModelDefinition["kind"],
  fields: FieldDefinition[] = [],
  collapse: InterfaceMeta["collapse"] = null,
): ModelDefinition => ({
  name,
  kind,
  abstract: false,
  description: null,
  parent: null,
  concreteTypes: [],
  typeParameters: [],
  createWithId: false,
  createDirectly: true,
  acceptUrlAsId: false,
  requireLabel: true,
  useInSemanticSpaceLabel: true,
  interfaceMeta: collapse === null ? null : meta(collapse),
  fields,
  incoming: [],
});

const definitions: ModelDefinitions = {
  models: {
    Person: model("Person", "Entity"),
    Activity: model("Activity", "Document", [field("note")]),
    Alternative: model("Alternative", "Conjunction", [field("alternatives", "relation")], true),
    Both: model("Both", "Conjunction", [field("left", "relation"), field("right", "relation")], true),
    Identification: model(
      "Identification",
      "ReifiedRelation",
      [field("identifiedBy"), field("target", "relation")],
      true,
    ),
    Involves: model("Involves", "ReifiedRelation", [field("target", "relation")]),
    Dated: model(
      "Dated",
      "ReifiedRelation",
      [field("date", "embedded"), field("target", "relation")],
      true,
    ),
    InRole: model(
      "InRole",
      "ReifiedRelation",
      [field("role"), field("sure"), field("note"), field("date", "embedded"), field("target", "relation")],
      { blocking: ["sure"], hidden: ["note", "date"], when: { role: ["author", "scribe"] } },
    ),
    Ruled: model(
      "Ruled",
      "ReifiedRelation",
      [field("date", "embedded"), field("target", "relation")],
      { module: "app", name: "always" },
    ),
  },
  enums: {},
};

const person = { id: "p1", type: "Person", label: "Smith", edgeProperties: { probability: 0.9 } };
const other = { id: "p2", type: "Person", label: "Jones" };
const alternative = (...people: object[]) => ({ id: "a1", type: "Alternative", alternatives: people });
const identification = (target: object, identifiedBy = "") => ({
  id: "i1",
  type: "Identification",
  identifiedBy,
  target: [target],
});

const none = () => undefined;

test("a model without collapse is never collapsed", () => {
  expect(collapsedView({ type: "Involves", target: [person] }, definitions, none)).toBeUndefined();
});

test("a conjunction with one entity collapses to it", () => {
  expect(collapsedView(alternative(person), definitions, none)).toEqual({ held: person, extras: [] });
});

test("a conjunction with two, or none, does not", () => {
  expect(collapsedView(alternative(person, other), definitions, none)).toBeUndefined();
  expect(collapsedView(alternative(), definitions, none)).toBeUndefined();
});

test("a conjunction with more than one relation field never collapses", () => {
  expect(collapsedView({ type: "Both", left: [person], right: [] }, definitions, none)).toBeUndefined();
});

test("a reified relation collapses only when what it holds ends as a chip", () => {
  const collapsed = collapsedView(identification(alternative(person)), definitions, none);
  expect(collapsed?.held).toEqual(alternative(person));
  expect(collapsedView(identification(alternative(person, other)), definitions, none)).toBeUndefined();
  // (a document is a block, not a chip)
  expect(collapsedView(identification({ id: "x", type: "Activity", note: "n" }), definitions, none)).toBeUndefined();
});

test("a target given as a single object, not a list, counts as one", () => {
  expect(collapsedView({ type: "Identification", target: person }, definitions, none)?.held).toEqual(person);
});

test("its other filled plain fields come with it; empty ones are left out", () => {
  expect(collapsedView(identification(person), definitions, none)?.extras).toEqual([]);
  const extras = collapsedView(identification(person, "Smith"), definitions, none)?.extras;
  expect(extras?.map((extra) => [extra.field.key, extra.value])).toEqual([["identifiedBy", "Smith"]]);
});

test("a filled field that is not plain stops the built-in rule", () => {
  expect(collapsedView({ type: "Dated", target: [person] }, definitions, none)?.held).toEqual(person);
  expect(
    collapsedView({ type: "Dated", date: { type: "Date", when: "800" }, target: [person] }, definitions, none),
  ).toBeUndefined();
});

test("a named rule decides whether, given the item and its model; one held item is still needed", () => {
  const always: CollapseRule = vi.fn(() => true);
  const find = (reference: { module: string; name: string }) =>
    reference.module === "app" && reference.name === "always" ? always : undefined;
  const item = { type: "Ruled", date: { type: "Date", when: "800" }, target: [{ id: "x", type: "Activity" }] };
  const collapsed = collapsedView(item, definitions, find);
  expect(collapsed?.held).toEqual({ id: "x", type: "Activity" });
  expect(collapsed?.extras.map((extra) => extra.field.key)).toEqual(["date"]);
  expect(always).toHaveBeenCalledWith(item, definitions.models.Ruled);
  expect(collapsedView({ ...item, target: [] }, definitions, find)).toBeUndefined();
  expect(collapsedView(item, definitions, () => () => false)).toBeUndefined();
});

test("a named rule that no module has is not used", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  expect(collapsedView({ type: "Ruled", target: [person] }, definitions, none)).toBeUndefined();
  expect(warn).toHaveBeenCalled();
  warn.mockRestore();
});

const inRole = (fields: Record<string, unknown>) => ({ type: "InRole", target: [person], role: "author", ...fields });

test("conditions: a field in `when` must hold one of its values", () => {
  expect(collapsedView(inRole({}), definitions, none)?.held).toEqual(person);
  expect(collapsedView(inRole({ role: "scribe" }), definitions, none)).toBeDefined();
  expect(collapsedView(inRole({ role: "patron" }), definitions, none)).toBeUndefined();
  // (an empty field holds none of them)
  expect(collapsedView(inRole({ role: "" }), definitions, none)).toBeUndefined();
});

test("conditions: a blocking field that is filled shows it whole", () => {
  expect(collapsedView(inRole({ sure: "" }), definitions, none)).toBeDefined();
  expect(collapsedView(inRole({ sure: "no" }), definitions, none)).toBeUndefined();
});

test("conditions: hidden fields are not shown beside it, and a hidden field that is not plain does not stop it", () => {
  const collapsed = collapsedView(
    inRole({ note: "a long note", date: { type: "Date", when: "800" } }),
    definitions,
    none,
  );
  expect(collapsed?.extras.map((extra) => extra.field.key)).toEqual(["role"]);
});

test("conditions: the structure still has to fold (one held item that ends as a chip)", () => {
  expect(collapsedView(inRole({ target: [person, other] }), definitions, none)).toBeUndefined();
  expect(collapsedView(inRole({ target: [{ id: "x", type: "Activity" }] }), definitions, none)).toBeUndefined();
});

test("what a block holds: through wrappers with no label, leaving out what has none yet", () => {
  const definitions = {
    models: {
      Person: model("Person", "Entity"),
      Statement: model("Statement", "Document"),
      Causes: model("Causes", "Conjunction", [field("cause", "relation"), field("result", "relation")]),
      Maybe: model("Maybe", "ReifiedRelation", [field("target", "relation"), field("by", "relation")]),
    },
  } as unknown as ModelDefinitions;
  const value = {
    type: "Causes",
    cause: { type: "Statement", label: "A fire" },
    result: [
      { type: "Maybe", target: [{ type: "Person", id: "p", label: "Smith" }], by: [{ type: "Person", id: "q", label: "Not shown" }] },
      { type: "Statement", label: "" },
      { type: "Person" },
    ],
  };
  expect(labelledContents(value, definitions)).toEqual([
    { type: "Statement", label: "A fire", fields: [{ model: "Causes", name: "cause" }] },
    { type: "Person", label: "Smith", fields: [{ model: "Causes", name: "result" }] },
  ]);
  // (one field of contents: nothing to tell apart)
  expect(labelledContents({ type: "Maybe", target: [{ type: "Person", id: "p", label: "Smith" }, { type: "Person", id: "r", label: "Jones" }] }, definitions)).toEqual([
    { type: "Person", label: "Smith", fields: [] },
    { type: "Person", label: "Jones", fields: [] },
  ]);
});
