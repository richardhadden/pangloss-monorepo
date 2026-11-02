import { expect, test } from "vitest";
import type { ModelDefinition, ModelDefinitions } from "../types";
import {
  combineWhere,
  compileSearch,
  decodeSearchForm,
  encodeSearchForm,
  incomingSourcesOf,
  operatorsOf,
  searchFieldsOf,
} from "./searchForm";
import type { NodeSearch } from "./searchForm";

const model = (name: string, extra: Partial<ModelDefinition> = {}) =>
  ({ name, kind: "Entity", fields: [], incoming: [], ...extra }) as unknown as ModelDefinition;

const smith = { type: "Person", id: "p1", label: "Smith" };
const jones = { type: "Person", id: "p2", label: "Jones" };

const definitions = {
  models: {
    Person: model("Person", {
      incoming: [
        {
          name: "sent",
          key: "sent",
          sources: [
            { model: "Letter", field: "sender", viaReified: false },
            { model: "Letter", field: "sender", viaReified: true },
            { model: "Day", field: "who", viaReified: false },
          ],
        },
        { name: "knows_r", key: "knowsR", sources: [{ model: "Person", field: "knows", viaReified: false }] },
      ],
    }),
    Letter: model("Letter", { kind: "Document" }),
  },
  enums: {},
  searchPatterns: {
    Letter: {
      kind: "document",
      fields: {
        year: { operators: "compare", value: { type: "int" } },
        sender: { operators: "relation", targets: ["Person"] },
        statements: { operators: "relation", targets: ["Activity"] },
        when: { operators: "relation", targets: ["Day"] },
      },
      orderBy: [],
    },
    Person: { kind: "entity", fields: { knows: { operators: "relation", targets: ["Person"] } }, orderBy: [] },
    Activity: { kind: "document", fields: {}, orderBy: [] },
    Day: { kind: "embedded", fields: { day: { operators: "compare", value: { type: "int" } } }, orderBy: [] },
  },
} as unknown as ModelDefinitions;

test("a type's fields are its label, then those of its pattern; an embedded object has no label", () => {
  expect(searchFieldsOf(definitions, "Letter").map((field) => field.name)).toEqual([
    "label",
    "year",
    "sender",
    "statements",
    "when",
  ]);
  expect(searchFieldsOf(definitions, "Day").map((field) => field.name)).toEqual(["day"]);
  expect(searchFieldsOf(definitions, "Nothing")).toEqual([]);
});

test("a relation to entities can pick them; one to documents or embedded objects is described", () => {
  const [, , sender, statements, when] = searchFieldsOf(definitions, "Letter");
  expect(operatorsOf(definitions, sender!)).toEqual(["any", "all", "match", "exists", "missing"]);
  expect(operatorsOf(definitions, statements!)).toEqual(["match", "exists", "missing"]);
  expect(operatorsOf(definitions, when!)).toEqual(["match", "exists", "missing"]);
});

test("what can refer to an entity: each type and relation once, not from an embedded object", () => {
  expect(incomingSourcesOf(definitions, "Person")).toEqual([
    { model: "Letter", field: "sender" },
    { model: "Person", field: "knows" },
  ]);
});

test("a form with no complete condition is no search", () => {
  expect(compileSearch(undefined)).toBeUndefined();
  expect(compileSearch({ type: "Letter" })).toBeUndefined();
  const unfinished: NodeSearch = {
    type: "Letter",
    fields: {
      label: { op: "contains", value: "  " },
      year: { op: "between", value: ["", ""] },
      sender: { op: "any", entities: [] },
      statements: { op: "match" },
    },
    mentions: { op: "any", entities: [] },
    incoming: [],
  };
  expect(compileSearch(unfinished, "rome")).toBeUndefined();
});

test("each operator is the condition of the API", () => {
  const form: NodeSearch = {
    type: "Letter",
    fields: {
      label: { op: "starts_with", value: "To" },
      year: { op: "gt", value: 1500 },
      kind: { op: "in", value: ["a", "b"] },
      sender: { op: "any", entities: [smith, jones] },
      statements: { op: "exists" },
      when: { op: "missing" },
    },
  };
  expect(compileSearch(form)).toEqual({
    label: { starts_with: "To" },
    year: { gt: 1500 },
    kind: { in: ["a", "b"] },
    sender: { is_any: ["p1", "p2"] },
    statements: { exists: true },
    when: { exists: false },
  });
});

test("a between with one end is that end, inclusive", () => {
  const on = (value: unknown) => compileSearch({ type: "Letter", fields: { year: { op: "between", value } } });
  expect(on([1500, 1600])).toEqual({ year: { between: [1500, 1600] } });
  expect(on([1500, ""])).toEqual({ year: { gte: 1500 } });
  expect(on([null, 1600])).toEqual({ year: { lte: 1600 } });
});

test("all of several entities is a condition for each, in an $all", () => {
  expect(compileSearch({ type: "Letter", fields: { sender: { op: "all", entities: [smith, jones] } } })).toEqual({
    sender: { is: "p1" },
    $all: [{ sender: { is: "p2" } }],
  });
});

test("not negates the whole condition of the field", () => {
  expect(
    compileSearch({
      type: "Letter",
      fields: {
        year: { op: "eq", value: 1500, not: true },
        sender: { op: "all", entities: [smith, jones], not: true },
      },
    }),
  ).toEqual({
    $not: { year: { eq: 1500 } },
    $all: [{ $not: { sender: { is: "p1" }, $all: [{ sender: { is: "p2" } }] } }],
  });
});

test("a nested form is a pattern for what the field points at, and a type alone is one of that type", () => {
  expect(
    compileSearch({
      type: "Letter",
      fields: {
        statements: { op: "match", node: { type: "Activity" } },
        when: { op: "match", node: { type: "Day", fields: { day: { op: "lt", value: 3 } } } },
      },
    }),
  ).toEqual({
    statements: { type: "Activity" },
    when: { type: "Day", where: { day: { lt: 3 } } },
  });
});

test("mentions are of the whole document; any of them, or all", () => {
  expect(compileSearch({ type: "Letter", mentions: { op: "any", entities: [smith, jones] } })).toEqual({
    $mentions: { is_any: ["p1", "p2"] },
  });
  expect(compileSearch({ type: "Letter", mentions: { op: "all", entities: [smith, jones], not: true } })).toEqual({
    $not: { $mentions: { is: "p1" }, $all: [{ $mentions: { is: "p2" } }] },
  });
});

test("what refers to an entity: each pattern must be met; a negated one, by nothing", () => {
  expect(
    compileSearch({
      type: "Person",
      incoming: [
        { field: "sender", node: { type: "Letter", fields: { year: { op: "lt", value: 1600 } } } },
        { node: { type: "Person" } },
        { field: "knows", not: true, node: { type: "Person" } },
      ],
    }),
  ).toEqual({
    $incoming: [
      { type: "Letter", field: "sender", where: { year: { lt: 1600 } } },
      { type: "Person" },
    ],
    $not: { $incoming: [{ type: "Person", field: "knows" }] },
  });
});

test("the words of the text box narrow the form's search, each a condition on the label", () => {
  expect(
    compileSearch({ type: "Letter", fields: { label: { op: "contains", value: "to" } } }, " rome  paris "),
  ).toEqual({
    label: { contains: "to" },
    $all: [{ label: { contains: "rome" } }, { label: { contains: "paris" } }],
  });
});

test("conditions on different keys are one where; the same key again goes into $all", () => {
  expect(combineWhere([{ a: 1 }, { b: 2 }, { a: 3 }, { $all: [{ c: 4 }] }])).toEqual({
    a: 1,
    b: 2,
    $all: [{ c: 4 }, { a: 3 }],
  });
});

test("the form goes into the address and back; an empty one, or one of another type, is none", () => {
  const form: NodeSearch = { type: "Letter", fields: { year: { op: "eq", value: 1500 } } };
  const text = encodeSearchForm(form);
  expect(decodeSearchForm(text, "Letter")).toEqual(form);
  expect(decodeSearchForm(text, "Person")).toBeUndefined();
  expect(encodeSearchForm({ type: "Letter", fields: {}, incoming: [] })).toBeUndefined();
  expect(decodeSearchForm("{not json", "Letter")).toBeUndefined();
  expect(decodeSearchForm("[1]", "Letter")).toBeUndefined();
});
