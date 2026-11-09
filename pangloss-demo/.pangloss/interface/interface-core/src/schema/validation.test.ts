import { expect, test } from "vitest";
import type { FieldDefinition, ModelDefinition, ModelDefinitions, RelationOption } from "../types";
import { isBlank, serverProblems, setValidationMessages, validateItem } from "./validation";

const model = (name: string, extra: Partial<ModelDefinition> = {}) =>
  ({
    name,
    kind: "Document",
    parent: null,
    abstract: false,
    concreteTypes: [name],
    description: null,
    typeParameters: [],
    createWithId: false,
    createDirectly: true,
    globalSearch: true,
    acceptUrlAsId: false,
    requireLabel: false,
    useInSemanticSpaceLabel: true,
    interfaceMeta: null,
    fields: [],
    incoming: [],
    ...extra,
  }) as ModelDefinition;

const base = { description: null, dbField: false, readOnly: false, required: false, nullable: false };
const literal = (name: string, type: object, extra: object = {}) =>
  ({ ...base, name, key: name, kind: "literal", type, validators: [], ...extra }) as FieldDefinition;
const list = (name: string, item: object, extra: object = {}) =>
  ({ ...base, name, key: name, kind: "list", item, validators: [], itemValidators: [], ...extra }) as FieldDefinition;
const relation = (name: string, options: RelationOption[], extra: object = {}) =>
  ({ ...base, name, key: name, kind: "relation", many: true, reverseName: `${name}_r`, options, validators: [], subclasses: [], ...extra }) as FieldDefinition;
const embedded = (name: string, types: string[], extra: object = {}) =>
  ({ ...base, name, key: name, kind: "embedded", model: null, types, ...extra }) as FieldDefinition;

const doc = (type: string): RelationOption => ({ kind: "document", type, edgeModel: null });
const entity = (type: string, edgeModel: string | null = null): RelationOption => ({ kind: "entity", type, edgeModel });
const required = { required: true };

// (a small world: a Factoid has statements, plain or Negative; an Activity is done by a Person, with a Certainty)
const definitions = {
  models: {
    Factoid: model("Factoid", {
      requireLabel: true,
      fields: [
        literal("year", { type: "int" }, { ...required, validators: [{ name: "Ge", ge: 1 }, { name: "Le", le: 2100 }] }),
        literal("note", { type: "str" }, { nullable: true }),
        literal("code", { type: "str" }, { validators: [{ name: "MinLen", min_length: 2 }, { name: "MaxLen", max_length: 4 }] }),
        literal("ratio", { type: "float" }, { validators: [{ name: "Gt", gt: 0 }, { name: "Lt", lt: 1 }] }),
        literal("price", { type: "decimal" }, { validators: [{ name: "Ge", ge: 0 }] }),
        literal("seen", { type: "date" }),
        literal("at", { type: "datetime" }),
        literal("ref", { type: "str", format: "uuid" }),
        literal("home", { type: "str", format: "url" }),
        literal("mail", { type: "str", format: "email" }),
        literal("hour", { type: "time" }),
        literal("lasted", { type: "duration" }),
        literal("done", { type: "bool" }),
        literal("kind", { type: "enum", enum: "Kind" }),
        literal("level", { type: "enum", enum: "Level" }),
        literal("mood", { type: "literal", values: ["happy", "sad"] }),
        literal("where", { type: "typedDict", fields: { lat: { type: "float" }, lon: { type: "float" } } }),
        literal("step", { type: "int" }, { validators: [{ name: "MultipleOf", multiple_of: 5 }] }),
        literal("slug", { type: "str" }, { validators: [{ name: "Constraints", pattern: "^[a-z]+$" }] }),
        list("tags", { type: "str" }, { validators: [{ name: "Unique" }] }),
        list("aliases", { type: "str" }, { ...required, itemValidators: [{ name: "MinLen", min_length: 2 }], validators: [{ name: "MaxLen", max_length: 2 }] }),
        relation("statements", [doc("Activity"), { kind: "semanticSpace", type: "Negative", edgeModel: null, params: { T: { typeVar: "T", options: [doc("Activity")] } } }], required),
        relation("author", [entity("Person")], { many: false }),
        embedded("when", ["Day"]),
        { ...base, name: "named", key: "named", kind: "annotatedValue", model: "WithCertainty", valueType: { type: "str" } },
        { ...base, name: "nicknames", key: "nicknames", kind: "annotatedValue", model: "WithCertainty", valueType: { type: "str" }, many: true },
        { ...base, name: "odd", key: "odd", kind: "unknown" },
      ],
    }),
    Activity: model("Activity", {
      requireLabel: true,
      fields: [
        literal("text", { type: "str" }, { ...required, validators: [{ name: "MinLen", min_length: 3 }] }),
        relation("doneBy", [entity("Person", "Certainty")], { ...required, validators: [{ name: "MinLen", min_length: 1 }] }),
        relation("parts", [doc("Activity")]),
      ],
    }),
    Negative: model("Negative", {
      kind: "SemanticSpace",
      fields: [relation("contents", [{ kind: "typeVar", name: "T", edgeModel: null }], required)],
    }),
    Person: model("Person", { kind: "Entity", requireLabel: true }),
    Certainty: model("Certainty", { kind: "EdgeModel", requireLabel: true, fields: [literal("level", { type: "int" }, required)] }),
    Day: model("Day", { kind: "Embedded", fields: [literal("year", { type: "int" }, required), literal("month", { type: "int" }, { nullable: true })] }),
    WithCertainty: model("WithCertainty", {
      kind: "AnnotatedValue",
      fields: [
        { ...base, name: "value", key: "value", kind: "typeVar", typeVar: "T", required: true },
        literal("certainty", { type: "int" }, required),
      ],
    }),
  },
  enums: {
    Kind: { name: "Kind", members: [{ name: "MEETING", value: "meeting" }, { name: "BATTLE", value: "battle" }] },
    Level: { name: "Level", members: [{ name: "LOW", value: 1 }, { name: "HIGH", value: 2 }] },
  },
} as unknown as ModelDefinitions;

/** A Factoid with what is required, and `extra` */
const factoid = (extra: Record<string, unknown> = {}) => ({
  type: "Factoid",
  label: "Fall",
  year: 476,
  aliases: [],
  statements: [],
  ...extra,
});

const problems = (item: Record<string, unknown>) =>
  validateItem(definitions, item).map((problem) => [problem.path.join("."), problem.code, problem.params]);

test("an item with what is required, and nothing wrong, has no problems; nor has a type the definitions do not have", () => {
  expect(problems(factoid())).toEqual([]);
  expect(validateItem(definitions, { type: "Nothing" })).toEqual([]);
  // (the keys of the form the API only reads are not checked)
  expect(problems(factoid({ meta: { version: 3 }, id: "f1" }))).toEqual([]);
});

test("a required field left out, or empty, is required; one that is not, or may be null, may be empty", () => {
  expect(problems({ type: "Factoid", aliases: [], statements: [] })).toEqual([
    ["label", "required", {}],
    ["year", "required", {}],
  ]);
  expect(problems(factoid({ label: "", year: "" }))).toEqual([
    ["label", "required", {}],
    ["year", "required", {}],
  ]);
  expect(problems(factoid({ note: null, code: "", ratio: "", where: {}, when: undefined }))).toEqual([]);
});

test("the scalars: a text, a whole number, a number, a decimal (typed as text), a date, a date and time, a uuid, a yes or no", () => {
  expect(problems(factoid({ year: 4.5 }))).toEqual([["year", "not_whole", {}]]);
  expect(problems(factoid({ year: "476" }))).toEqual([["year", "wrong_type", { expected: "number" }]]);
  expect(problems(factoid({ price: "12.50" }))).toEqual([]);
  expect(problems(factoid({ price: "12,50" }))).toEqual([["price", "not_number", {}]]);
  expect(problems(factoid({ seen: "2024-02-30x" }))).toEqual([["seen", "not_date", {}]]);
  expect(problems(factoid({ seen: "2024-02-03" }))).toEqual([]);
  expect(problems(factoid({ at: "2024-02-03T10:30" }))).toEqual([]);
  expect(problems(factoid({ at: "10:30" }))).toEqual([["at", "not_datetime", {}]]);
  expect(problems(factoid({ ref: "0193a4f2-8c1e-7d3a-9b2c-1e2f3a4b5c6d" }))).toEqual([]);
  expect(problems(factoid({ ref: "nope" }))).toEqual([["ref", "not_uuid", {}]]);
  expect(problems(factoid({ home: "https://example.org/a" }))).toEqual([]);
  expect(problems(factoid({ home: "nope" }))).toEqual([["home", "not_url", {}]]);
  expect(problems(factoid({ mail: "a@example.org" }))).toEqual([]);
  expect(problems(factoid({ mail: "nope" }))).toEqual([["mail", "not_email", {}]]);
  expect(problems(factoid({ hour: "10:30" }))).toEqual([]);
  expect(problems(factoid({ hour: "10:30:15" }))).toEqual([]);
  expect(problems(factoid({ hour: "2024-02-03" }))).toEqual([["hour", "not_time", {}]]);
  expect(problems(factoid({ lasted: "P1DT2H30M" }))).toEqual([]);
  expect(problems(factoid({ lasted: "90" }))).toEqual([]);
  expect(problems(factoid({ lasted: "two hours" }))).toEqual([["lasted", "not_duration", {}]]);
  expect(problems(factoid({ tags: ["a", "b"] }))).toEqual([]);
  expect(problems(factoid({ tags: ["a", "a"] }))).toEqual([["tags", "not_unique", {}]]);
  expect(problems(factoid({ done: "yes" }))).toEqual([["done", "wrong_type", { expected: "boolean" }]]);
});

test("the validators of a field: lengths of a text, bounds and steps of a number, and a pattern", () => {
  expect(problems(factoid({ code: "a" }))).toEqual([["code", "too_short", { n: 2 }]]);
  expect(problems(factoid({ code: "abcde" }))).toEqual([["code", "too_long", { n: 4 }]]);
  expect(problems(factoid({ year: 0 }))).toEqual([["year", "too_small", { n: 1 }]]);
  expect(problems(factoid({ year: 3000 }))).toEqual([["year", "too_large", { n: 2100 }]]);
  expect(problems(factoid({ ratio: 0 }))).toEqual([["ratio", "must_exceed", { n: 0 }]]);
  expect(problems(factoid({ ratio: 1 }))).toEqual([["ratio", "must_be_under", { n: 1 }]]);
  expect(problems(factoid({ price: "-1" }))).toEqual([["price", "too_small", { n: 0 }]]);
  expect(problems(factoid({ step: 7 }))).toEqual([["step", "not_multiple", { n: 5 }]]);
  expect(problems(factoid({ slug: "Abc" }))).toEqual([["slug", "invalid", {}]]);
  expect(problems(factoid({ slug: "abc" }))).toEqual([]);
});

test("a choice is one of the members of the enum (or of the literal), as its value or as the text a pill writes", () => {
  expect(problems(factoid({ kind: "meeting", level: "2", mood: "sad" }))).toEqual([]);
  expect(problems(factoid({ level: 2 }))).toEqual([]);
  expect(problems(factoid({ kind: "party", mood: "glad" }))).toEqual([
    ["kind", "not_choice", {}],
    ["mood", "not_choice", {}],
  ]);
});

test("a typed dict has each of its keys", () => {
  expect(problems(factoid({ where: { lat: 1.5 } }))).toEqual([["where.lon", "required", {}]]);
  expect(problems(factoid({ where: { lat: 1.5, lon: "x" } }))).toEqual([["where.lon", "wrong_type", { expected: "number" }]]);
});

test("a list: its items checked where they are, empty ones not checked nor counted (they are not sent)", () => {
  expect(problems(factoid({ aliases: ["Ro", "x", "Rome"] }))).toEqual([["aliases.1", "too_short", { n: 2 }]]);
  expect(problems(factoid({ aliases: ["", "Ro", "", "Rome"] }))).toEqual([]);
  expect(problems(factoid({ aliases: ["Ro", "Rom", "Rome"] }))).toEqual([["aliases", "too_many", { n: 2 }]]);
  // (a required list may be empty, but it is sent)
  expect(problems({ type: "Factoid", label: "F", year: 1, statements: [] })).toEqual([["aliases", "required", {}]]);
});

test("a relation holds what its options say, each checked as its model, at its own path", () => {
  const activity = { type: "Activity", label: "Met", text: "met", doneBy: [{ type: "Person", id: "p1", edgeProperties: { level: 1 } }] };
  expect(problems(factoid({ statements: [activity] }))).toEqual([]);
  expect(problems(factoid({ statements: [activity, { type: "Activity", text: "x", doneBy: [] }] }))).toEqual([
    ["statements.1.label", "required", {}],
    ["statements.1.text", "too_short", { n: 3 }],
    ["statements.1.doneBy", "too_few", { n: 1 }],
  ]);
  // (a type the field does not hold)
  expect(problems(factoid({ statements: [{ type: "Day", year: 1 }] }))).toEqual([["statements.0", "type_not_allowed", {}]]);
  // (a document in a document in a document: the models are made as they are needed)
  expect(
    problems(factoid({ statements: [{ ...activity, parts: [{ ...activity, parts: [{ ...activity, text: "" }] }] }] })),
  ).toEqual([["statements.0.parts.0.parts.0.text", "required", {}]]);
});

test("a semantic space holds what its type variable is bound to, where it is used", () => {
  const inside = { type: "Activity", label: "Met", text: "met", doneBy: [{ type: "Person", id: "p1", edgeProperties: { level: 1 } }] };
  expect(problems(factoid({ statements: [{ type: "Negative", contents: [inside] }] }))).toEqual([]);
  expect(problems(factoid({ statements: [{ type: "Negative", contents: [{ ...inside, text: "no" }] }] }))).toEqual([
    ["statements.0.contents.0.text", "too_short", { n: 3 }],
  ]);
  expect(problems(factoid({ statements: [{ type: "Negative", contents: [{ type: "Negative", contents: [] }] }] }))).toEqual([
    ["statements.0.contents.0", "type_not_allowed", {}],
  ]);
});

test("an entity is a reference that has to be chosen; what the relation says of it is checked as its edge model", () => {
  const activity = (doneBy: unknown[]) => factoid({ statements: [{ type: "Activity", label: "M", text: "met", doneBy }] });
  // (not chosen yet: it is not sent, so it is not counted)
  expect(problems(activity([{ type: "Person" }]))).toEqual([["statements.0.doneBy", "too_few", { n: 1 }]]);
  expect(problems(activity([{ type: "Person", id: "p1", edgeProperties: { level: 2 } }]))).toEqual([]);
  // (none given yet: what is required of them is still told)
  expect(problems(activity([{ type: "Person", id: "p1" }]))).toEqual([["statements.0.doneBy.0.edgeProperties.level", "required", {}]]);
  expect(problems(activity([{ type: "Person", id: "p1", edgeProperties: { level: "" } }]))).toEqual([
    ["statements.0.doneBy.0.edgeProperties.level", "required", {}],
  ]);
  // (an entity in a relation has no label of its own to give)
  expect(problems(factoid({ author: { type: "Person", id: "p1" } }))).toEqual([]);
});

test("an embedded value is one of its types, with that type's fields", () => {
  expect(problems(factoid({ when: { type: "Day", year: 1066 } }))).toEqual([]);
  expect(problems(factoid({ when: { type: "Day" } }))).toEqual([["when.year", "required", {}]]);
  expect(problems(factoid({ when: { type: "Week", year: 1 } }))).toEqual([["when", "type_not_allowed", {}]]);
});

test("an annotated value has its value, of the field's type, and the fields of its model", () => {
  expect(problems(factoid({ named: { value: "Rome", certainty: 2 } }))).toEqual([]);
  expect(problems(factoid({ named: { certainty: 2 } }))).toEqual([["named.value", "required", {}]]);
  expect(problems(factoid({ named: { value: 3, certainty: "" } }))).toEqual([
    ["named.certainty", "required", {}],
    ["named.value", "wrong_type", { expected: "string" }],
  ]);
});

test("a list of annotated values has each one checked, at its place in the list", () => {
  expect(problems(factoid({ nicknames: [{ value: "Rome", certainty: 2 }, { value: "Roma", certainty: 1 }] }))).toEqual([]);
  expect(problems(factoid({ nicknames: [{ value: "Rome", certainty: 2 }, { value: 3, certainty: "" }] }))).toEqual([
    ["nicknames.1.certainty", "required", {}],
    ["nicknames.1.value", "wrong_type", { expected: "string" }],
  ]);
});

test("a field the export cannot describe is left to the API", () => {
  expect(problems(factoid({ odd: { anything: [1, 2] } }))).toEqual([]);
});

test("what counts as nothing is what is not sent", () => {
  for (const blank of [undefined, null, "", {}, { type: "Person" }, { type: "Person", id: "" }]) {
    expect(isBlank(definitions, blank)).toBe(true);
  }
  for (const value of [0, false, "x", [], { type: "Day" }, { type: "Person", id: "p1" }]) {
    expect(isBlank(definitions, value)).toBe(false);
  }
});

test("the problems of a 422 are at the paths of the form, without body, the names of models, and the tags of unions", () => {
  const detail = JSON.stringify([
    { loc: ["body", "statements", 0, "Activity", "text"], msg: "String should have at least 3 characters" },
    { loc: ["body", "when", "function-after[check(), Day]", "year"], msg: "Field required" },
    { loc: ["body"], msg: "Something" },
  ]);
  const said = (message: string) => ({ code: "server", params: { message }, message });
  expect(serverProblems(definitions, detail)).toEqual([
    { path: ["statements", 0, "text"], ...said("String should have at least 3 characters") },
    { path: ["when", "year"], ...said("Field required") },
    { path: [], ...said("Something") },
  ]);
  expect(serverProblems(definitions, "Id in use")).toEqual([{ path: [], ...said("Id in use") }]);
});

test("valibot is given the messages of a language, and a check in that language says what is wrong in it", () => {
  const german: Record<string, string> = { required: "Erforderlich", too_short: "Mindestens {n} Zeichen" };
  setValidationMessages("de", (code, params) =>
    (german[code] ?? `?${code}`).replace("{n}", String(params.n)),
  );
  setValidationMessages("en", (code, params) => (code === "required" ? "Required" : `${code} ${params.n ?? ""}`.trim()));
  const item = factoid({ year: "", code: "a", statements: [{ type: "Day", year: 1 }] });
  const said = (lang?: string) => validateItem(definitions, item, { lang }).map((problem) => [problem.path.join("."), problem.message]);
  expect(said("de")).toEqual([
    ["year", "Erforderlich"],
    ["code", "Mindestens 2 Zeichen"],
    ["statements.0", "?type_not_allowed"],
  ]);
  expect(said("en")).toEqual([
    ["year", "Required"],
    ["code", "too_short 2"],
    ["statements.0", "type_not_allowed"],
  ]);
  // (a language valibot has no messages for: its own English; the codes are the same whatever the language)
  expect(said("fr")[0]![1]).toMatch(/^Invalid/);
  expect(validateItem(definitions, item, { lang: "fr" }).map((problem) => problem.code)).toEqual([
    "required",
    "too_short",
    "type_not_allowed",
  ]);
});

test("a field the server works out (a DBField) is not required of the form, whatever the model says", () => {
  const worked = {
    models: {
      Recurrence: model("Recurrence", {
        kind: "Embedded",
        fields: [
          literal("frequency", { type: "str" }, required),
          list("patternKeys", { type: "str" }, { ...required, dbField: true }),
        ],
      }),
    },
    enums: {},
  } as unknown as ModelDefinitions;
  expect(validateItem(worked, { type: "Recurrence", frequency: "yearly" })).toEqual([]);
  expect(validateItem(worked, { type: "Recurrence" }).map((problem) => problem.path.join("."))).toEqual(["frequency"]);
});

test("the shares of a relation's items add up to its total (`SumsTo`): at the list, as the server refuses it", () => {
  const shared = {
    models: {
      Suspicion: model("Suspicion", {
        fields: [
          relation("suspects", [entity("Person", "Probability")], {
            validators: [{ name: "SumsTo", field: "percent", total: 100 }],
          }),
        ],
      }),
      Person: model("Person", { kind: "Entity", requireLabel: true }),
      Probability: model("Probability", {
        kind: "EdgeModel",
        fields: [literal("percent", { type: "int" }, { ...required, validators: [{ name: "Ge", ge: 1 }, { name: "Le", le: 100 }] })],
      }),
    },
    enums: {},
  } as unknown as ModelDefinitions;
  const suspect = (id: string, percent: number) => ({ type: "Person", id, edgeProperties: { percent } });
  const check = (suspects: unknown[]) =>
    validateItem(shared, { type: "Suspicion", suspects }).map((problem) => [problem.path.join("."), problem.code, problem.params]);
  expect(check([suspect("a", 60), suspect("b", 40)])).toEqual([]);
  expect(check([])).toEqual([]);
  expect(check([suspect("a", 60), suspect("b", 30)])).toEqual([["suspects", "shares_total", { n: 100, sum: 90 }]]);
  // (one not chosen yet is not sent, and not counted)
  expect(check([suspect("a", 100), { type: "Person", edgeProperties: { percent: 20 } }])).toEqual([]);
});
