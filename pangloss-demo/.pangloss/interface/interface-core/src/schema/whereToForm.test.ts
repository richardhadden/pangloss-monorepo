import { expect, test } from "vitest";
import type { ModelDefinition, ModelDefinitions } from "../types";
import { compileSearch, extraRowsOf } from "./searchForm";
import type { NodeSearch } from "./searchForm";
import { pickedIds, whereToForm, withLabels } from "./whereToForm";

// (the definitions of searchForm.test.ts, with the `kind` its cases use, and a type with a flag)
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
    Letter: model("Letter", {
      kind: "Document",
      fields: [
        {
          name: "statements",
          kind: "relation",
          options: [
            { kind: "document", type: "Activity", edgeModel: null },
            {
              kind: "semanticSpace",
              type: "Negative",
              edgeModel: null,
              params: {
                T: {
                  typeVar: "T",
                  options: [
                    { kind: "conjunction", type: "Causes", edgeModel: null, params: {} },
                    { kind: "document", type: "Activity", edgeModel: null },
                  ],
                },
              },
            },
          ],
        },
      ],
    } as never),
    Activity: model("Activity", { kind: "Document" }),
    Day: model("Day", { kind: "Embedded" }),
    AbstractFactoid: model("AbstractFactoid", { kind: "Document" }),
    Negative: model("Negative", { kind: "SemanticSpace" }),
    Spaces: model("Spaces", { kind: "SemanticSpace", abstract: true }),
  },
  enums: {},
  searchPatterns: {
    Letter: {
      kind: "document",
      fields: {
        year: { operators: "compare", value: { type: "int" } },
        kind: { operators: "choice", value: { type: "str" } },
        sender: { operators: "relation", targets: ["Person"] },
        statements: { operators: "relation", targets: ["Activity"] },
        when: { operators: "relation", targets: ["Day"] },
      },
      orderBy: ["year"],
    },
    Person: { kind: "entity", fields: { knows: { operators: "relation", targets: ["Person"] } }, orderBy: [] },
    Activity: { kind: "document", fields: {}, orderBy: [] },
    Day: { kind: "embedded", fields: { day: { operators: "compare", value: { type: "int" } } }, orderBy: [] },
    AbstractFactoid: { kind: "document", fields: {}, orderBy: [], flags: ["$derived_document"] },
  },
} as unknown as ModelDefinitions;

const year = (value: number): NodeSearch => ({ type: "Letter", fields: { year: { op: "eq", value } } });

// (every form searchForm.test.ts compiles, with the words of the text box where it gives them; and more that put
// conditions in `$all` in ways the order of the form has to keep)
const cases: [string, NodeSearch, string?][] = [
  [
    "unfinished: no search",
    {
      type: "Letter",
      fields: {
        label: { op: "contains", value: "  " },
        year: { op: "between", value: ["", ""] },
        sender: { op: "any", entities: [] },
        statements: { op: "match" },
      },
      mentions: { op: "any", entities: [] },
      incoming: [],
    },
    "rome",
  ],
  [
    "each operator",
    {
      type: "Letter",
      fields: {
        label: { op: "starts_with", value: "To" },
        year: { op: "gt", value: 1500 },
        kind: { op: "in", value: ["a", "b"] },
        sender: { op: "any", entities: [smith, jones] },
        statements: { op: "exists" },
        when: { op: "missing" },
      },
    },
  ],
  ["between", { type: "Letter", fields: { year: { op: "between", value: [1500, 1600] } } }],
  ["between, from", { type: "Letter", fields: { year: { op: "between", value: [1500, ""] } } }],
  ["between, to", { type: "Letter", fields: { year: { op: "between", value: [null, 1600] } } }],
  ["all of several", { type: "Letter", fields: { sender: { op: "all", entities: [smith, jones] } } }],
  [
    "not",
    {
      type: "Letter",
      fields: {
        year: { op: "eq", value: 1500, not: true },
        sender: { op: "all", entities: [smith, jones], not: true },
      },
    },
  ],
  [
    "nested",
    {
      type: "Letter",
      fields: {
        statements: { op: "match", node: { type: "Activity" } },
        when: { op: "match", node: { type: "Day", fields: { day: { op: "lt", value: 3 } } } },
      },
    },
  ],
  ["mentions, any", { type: "Letter", mentions: { op: "any", entities: [smith, jones] } }],
  ["mentions, all, not", { type: "Letter", mentions: { op: "all", entities: [smith, jones], not: true } }],
  [
    "incoming",
    {
      type: "Person",
      incoming: [
        { field: "sender", node: { type: "Letter", fields: { year: { op: "lt", value: 1600 } } } },
        { node: { type: "Person" } },
        { field: "knows", not: true, node: { type: "Person" } },
      ],
    },
  ],
  ["the words of the text box", { type: "Letter", fields: { label: { op: "contains", value: "to" } } }, " rome  paris "],
  [
    "two conditions on one field",
    { type: "Letter", fields: { year: { op: "gte", value: 1500, and: [{ op: "eq", value: 1550, not: true }, { op: "lt", value: "" }] } } },
  ],
  ["any of", { type: "Letter", anyOf: [[year(1500), year(1600), { type: "Letter" }]] }],
  ["any of, one alternative", { type: "Letter", anyOf: [[year(1500), { type: "Letter" }]] }],
  ["any of, none", { type: "Letter", anyOf: [[{ type: "Letter" }]] }],
  [
    "somewhere",
    {
      type: "Letter",
      somewhere: [{ node: { type: "Activity" } }, { not: true, node: { type: "Day", fields: { day: { op: "eq", value: 1 } } } }],
    },
  ],
  [
    "through, and spaces",
    {
      type: "Letter",
      fields: {
        statements: { op: "match", through: ["Negative"], node: { type: "Activity", spaces: ["Negative"] } },
        sender: { op: "any", through: ["Negative"], entities: [] },
      },
    },
  ],
  ["a flag", { type: "AbstractFactoid", flags: { $derived_document: false } }],
  ["a flag, and words", { type: "AbstractFactoid", flags: { $derived_document: true } }, "rome"],
  // (more: what `$all` gets, in an order that the form's order has to give again)
  [
    "fields whose conditions go into $all in turn",
    {
      type: "Letter",
      fields: {
        label: { op: "contains", value: "x" },
        year: { op: "gte", value: 1, and: [{ op: "lt", value: 9 }] },
        kind: { op: "in", value: ["a"], not: true, and: [{ op: "exists", not: true }] },
        sender: { op: "all", entities: [smith, jones] },
      },
    },
  ],
  [
    "a field with no first condition, then one with both",
    {
      type: "Letter",
      fields: {
        year: { op: "eq", value: 1, not: true },
        sender: { op: "any", entities: [smith], not: true },
        kind: { op: "in", value: ["a"], and: [{ op: "exists", not: true }] },
      },
    },
  ],
  [
    "a field, and an alternative on it, apart",
    { type: "Letter", fields: { year: { op: "gte", value: 1500 } }, mentions: { op: "any", entities: [smith], not: true }, anyOf: [[year(1600), { type: "Letter" }]] },
  ],
  [
    "groups of alternatives, one of several keys",
    {
      type: "Letter",
      fields: { year: { op: "gt", value: 1 } },
      anyOf: [
        [{ type: "Letter", fields: { year: { op: "lt", value: 9 }, kind: { op: "in", value: ["a"] } } }, { type: "Letter" }],
        [year(3), year(4)],
        [year(5), year(6)],
      ],
    },
  ],
  [
    "everything a document can have, negated where it can be",
    {
      type: "Letter",
      fields: { year: { op: "eq", value: 1, not: true } },
      mentions: { op: "all", entities: [smith, jones] },
      somewhere: [
        { node: { type: "Activity" } },
        { not: true, node: { type: "Activity" } },
        { not: true, node: { type: "Day" } },
      ],
    },
  ],
  [
    "an entity referred to in several ways, and alternatives that refer to it",
    {
      type: "Person",
      fields: { knows: { op: "match", node: { type: "Person", fields: { label: { op: "eq", value: "Smith" } } } } },
      incoming: [{ field: "sender", not: true, node: { type: "Letter" } }, { field: "knows", node: { type: "Person" } }],
      anyOf: [[{ type: "Person", incoming: [{ field: "sender", node: year(1500) }] }, { type: "Person" }]],
    },
  ],
];

test.each(cases)("what the form makes, read back, makes the same: %s", (_, form, q) => {
  const where = compileSearch(form, q ?? "");
  const read = whereToForm(definitions, form.type, where ?? {});
  expect(read).not.toBeNull();
  expect(compileSearch(read!)).toEqual(where);
});

// (as a stored pattern comes back from the API: its keys sorted at every depth, as the server keeps its text)
const sorted = (value: unknown): unknown =>
  Array.isArray(value)
    ? value.map(sorted)
    : typeof value === "object" && value !== null
      ? Object.fromEntries(Object.keys(value).sort().map((key) => [key, sorted((value as Record<string, unknown>)[key])]))
      : value;

test.each(cases)("and as it is stored, with its keys sorted: %s", (_, form, q) => {
  const where = compileSearch(form, q ?? "");
  const read = whereToForm(definitions, form.type, sorted(where ?? {}) as Record<string, unknown>);
  expect(read).not.toBeNull();
  expect(compileSearch(read!)).toEqual(where);
});

test("read back, a form is as it was, but for the labels of what is picked", () => {
  const form: NodeSearch = {
    type: "Letter",
    fields: {
      year: { op: "gte", value: 1500, and: [{ op: "lt", value: 1600 }] },
      sender: { op: "any", entities: [smith], through: ["Negative"] },
      statements: { op: "match", node: { type: "Activity", spaces: ["Negative"] } },
    },
    mentions: { op: "all", entities: [jones] },
  };
  expect(whereToForm(definitions, "Letter", compileSearch(form))).toEqual({
    ...form,
    fields: { ...form.fields, sender: { op: "any", entities: [{ type: "Person", id: "p1", label: "" }], through: ["Negative"] } },
    // (anything can be mentioned: the type is not known)
    mentions: { op: "all", entities: [{ type: "", id: "p2", label: "" }] },
  });
  expect(whereToForm(definitions, "AbstractFactoid", { $derived_document: true })).toEqual({
    type: "AbstractFactoid",
    flags: { $derived_document: true },
  });
  // (nothing: a form with nothing in it)
  expect(whereToForm(definitions, "Letter", {})).toEqual({ type: "Letter" });
});

test("what the form cannot show is no form at all", () => {
  const none = (where: Record<string, unknown>, type = "Letter") => expect(whereToForm(definitions, type, where)).toBeNull();
  // (a type that cannot be searched)
  expect(whereToForm(definitions, "Nothing", {})).toBeNull();
  // (an operator the form does not make, or that the field does not have)
  none({ year: { regex: "1.*" } });
  none({ year: { contains: "15" } });
  none({ sender: { eq: "p1" } });
  none({ year: { eq: { nested: true } } });
  // (a field the type does not have; a key the form does not make)
  none({ colour: { eq: "red" } });
  none({ $foo: [] });
  none({ $any: { label: { eq: "x" } } });
  // (a step of `through` with conditions; a condition on the edge)
  none({ statements: { type: "Activity", through: [{ type: "Negative", where: { label: { eq: "x" } } }] } });
  none({ sender: { is: "p1", edge: { type: "Certainty", where: { level: { gte: 2 } } } } });
  none({ sender: { type: "Person", edge: { type: "Certainty" } } });
  // (`through` on a field that is no relation; on what refers to an entity)
  none({ year: { eq: 1, through: ["Negative"] } });
  none({ $incoming: [{ type: "Letter", field: "sender", through: ["Negative"] }] }, "Person");
  // (a nested type that is not one of what the relation points at; something that does not refer to it)
  none({ statements: { type: "Day" } });
  none({ $incoming: [{ type: "Activity" }] }, "Person");
  // (somewhere, by a type that cannot be searched; spaces at the root, or one that is not a space)
  none({ $somewhere: [{ type: "Negative" }] });
  none({ $spaces: ["Negative"] });
  none({ statements: { type: "Activity", where: { $spaces: ["Hypothetical"] } } });
  // (a flag the type does not have, or not yes or no; a variable of a rule; a $not of two things)
  none({ $derived_document: true });
  none({ $derived_document: "yes" }, "AbstractFactoid");
  none({ sender: { is: { $var: "a" } } });
  none({ $not: { year: { eq: 1 }, sender: { is: "p1" } } });
  // (something the form can show, beside something it cannot, is not shown in part)
  none({ year: { eq: 1500 }, $all: [{ colour: { eq: "red" } }] });
  none({ $any_of: [{ year: { eq: 1 } }, { colour: { eq: 1 } }] });
  none({ when: { type: "Day", where: { day: { eq: 1 }, month: { eq: 2 } } } });
});

test("the ids of the entities a form picks, at any depth, each once; then their labels and types", () => {
  const form = whereToForm(
    definitions,
    "Letter",
    compileSearch({
      type: "Letter",
      fields: { sender: { op: "all", entities: [smith, jones], and: [{ op: "any", entities: [smith] }] } },
      mentions: { op: "any", entities: [{ type: "Place", id: "x1", label: "Rome" }] },
      anyOf: [[{ type: "Letter", mentions: { op: "any", entities: [jones] } }, { type: "Letter" }]],
    }),
  )!;
  expect(pickedIds(form).sort()).toEqual(["p1", "p2", "x1"]);
  const labelled = withLabels(form, [
    { id: "p1", type: "Person", label: "Smith" },
    { id: "x1", type: "Place", label: "Rome" },
  ]);
  expect(labelled.mentions?.entities).toEqual([{ type: "Place", id: "x1", label: "Rome" }]);
  // (p2 is not found: it keeps no label, which says the pattern names a deleted entity)
  const senders = [labelled.fields!.sender!, ...(labelled.fields!.sender!.and ?? [])].flatMap((search) => search.entities ?? []);
  expect(senders).toContainEqual({ type: "Person", id: "p1", label: "Smith" });
  expect(senders).toContainEqual({ type: "Person", id: "p2", label: "" });
  // (the form it was given is as it was)
  expect(form.mentions?.entities).toEqual([{ type: "", id: "x1", label: "" }]);
});

test("a form that is not of a list offers no order", () => {
  expect(extraRowsOf(definitions, "Letter", { root: true })).toContain("order");
  expect(extraRowsOf(definitions, "Letter", { root: true, order: false })).not.toContain("order");
});
