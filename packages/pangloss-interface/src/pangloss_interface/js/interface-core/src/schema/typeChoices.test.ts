import { expect, test } from "vitest";
import type { ModelDefinition, ModelDefinitions, RelationOption } from "../types";
import { blankItem, cleanForSave, getAt, removeAt, setAt } from "./formValue";
import {
  choicesOf,
  choiceValue,
  envOf,
  inSpaces,
  menuGroups,
  resolveOptions,
  spaceOptions,
  typeColumns,
} from "./typeChoices";

const model = (name: string, extra: Partial<ModelDefinition> = {}) =>
  ({
    name,
    kind: "Document",
    parent: null,
    abstract: false,
    concreteTypes: [name],
    fields: [],
    incoming: [],
    ...extra,
  }) as ModelDefinition;

// Statement (abstract) > Activity, Transfer, and Event (abstract) > Battle, Feast; Note stands alone
const definitions = {
  models: {
    Statement: model("Statement", { abstract: true }),
    Activity: model("Activity", { parent: "Statement" }),
    Transfer: model("Transfer", { parent: "Statement" }),
    Event: model("Event", { parent: "Statement", abstract: true }),
    Battle: model("Battle", { parent: "Event" }),
    Feast: model("Feast", { parent: "Event" }),
    Note: model("Note"),
    Person: model("Person", { kind: "Entity" }),
    Negative: model("Negative", {
      kind: "SemanticSpace",
      fields: [
        { name: "contents", key: "contents", kind: "relation", many: true, options: [{ kind: "typeVar", name: "T", edgeModel: null }] },
      ] as never,
    }),
    Causes: model("Causes", { kind: "Conjunction" }),
    AtPage: model("AtPage", {
      kind: "ReifiedRelation",
      fields: [
        { name: "target", key: "target", kind: "relation", many: false, required: true, options: [{ kind: "typeVar", name: "T", edgeModel: null }] },
      ] as never,
    }),
    Letter: model("Letter", {
      fields: [
        {
          name: "source",
          key: "source",
          kind: "relation",
          many: false,
          required: true,
          options: [
            {
              kind: "reifiedRelation",
              type: "AtPage",
              edgeModel: null,
              params: { T: { typeVar: "T", options: [{ kind: "entity", type: "Person", edgeModel: null }] } },
            },
          ],
        },
      ] as never,
      incoming: [{ name: "x", key: "cited", sources: [] }],
    }),
  },
  enums: {},
} as unknown as ModelDefinitions;

const doc = (type: string): RelationOption => ({ kind: "document", type, edgeModel: null });
const names = (rows: { name: string }[][]) => rows.map((column) => column.map((row) => row.name));

test("the lists are split at the last ancestor all the types share: its children are the tops", () => {
  const columns = typeColumns(definitions, ["Activity", "Transfer", "Battle", "Feast"]);
  // (Statement is common to all, so it is not shown: Activity, Transfer and Event are the tops of three lists)
  expect(names(columns)).toEqual([["Activity"], ["Event", "Battle", "Feast"], ["Transfer"]]);
  expect(columns[1]!.map((row) => [row.depth, row.selectable])).toEqual([
    [0, false],
    [1, true],
    [1, true],
  ]);
});

test("types with nothing in common are lists of their own, and one type is one list of one", () => {
  expect(names(typeColumns(definitions, ["Note", "Activity"]))).toEqual([["Note"], ["Statement", "Activity"]]);
  expect(names(typeColumns(definitions, ["Battle"]))).toEqual([["Battle"]]);
  expect(typeColumns(definitions, [])).toEqual([]);
});

test("when the common ancestor is itself a choice, it tops the one list; abstract classes in between are not selectable", () => {
  const both = typeColumns(definitions, ["Statement", "Battle"]);
  expect(names(both)).toEqual([["Statement", "Event", "Battle"]]);
  expect(both[0]!.map((row) => row.selectable)).toEqual([true, false, true]);
});

test("a field offers its plain types, and the same types inside each semantic space it accepts", () => {
  const space = (type: string, inner: RelationOption[]): RelationOption => ({
    kind: "semanticSpace",
    type,
    edgeModel: null,
    params: { T: { typeVar: "T", options: inner } },
  });
  const options = [doc("Activity"), doc("Transfer"), space("Negative", [doc("Activity"), doc("Transfer")])];
  const groups = menuGroups(definitions, options);
  expect(groups.map((group) => group.spaces)).toEqual([[], ["Negative"]]);
  expect(names(groups[1]!.columns)).toEqual([["Activity"], ["Transfer"]]);
  const choices = choicesOf(groups);
  expect(choices).toHaveLength(4);
  expect(choiceValue(definitions, { spaces: ["Negative"], type: "Activity" })).toEqual({
    type: "Negative",
    contents: [{ type: "Activity" }],
  });
  expect(choiceValue(definitions, { spaces: [], type: "Activity" })).toEqual({ type: "Activity" });
});

test("a semantic space inside a semantic space is a group of its own, and type variables are bound by the option", () => {
  const inner: RelationOption = {
    kind: "semanticSpace",
    type: "Negative",
    edgeModel: null,
    params: { T: { typeVar: "T", options: [{ kind: "typeVar", name: "U", edgeModel: null }] } },
  };
  const options: RelationOption[] = [
    { kind: "semanticSpace", type: "Negative", edgeModel: null, params: { T: { typeVar: "T", options: [doc("Note"), inner] } } },
  ];
  // (the inner one's T is bound to U, which nothing binds: it offers nothing, and so has no group)
  expect(menuGroups(definitions, options).map((group) => group.spaces)).toEqual([["Negative"]]);
  const env = envOf(options[0]!, {});
  expect(resolveOptions([{ kind: "typeVar", name: "T", edgeModel: null }], env)).toHaveLength(2);
});

test("what goes inside a semantic space is its contents' options; something pasted there is put in a new one", () => {
  const space = (type: string, inner: RelationOption[]): RelationOption => ({
    kind: "semanticSpace",
    type,
    edgeModel: null,
    params: { T: { typeVar: "T", options: inner } },
  });
  const options = [
    doc("Activity"),
    space("Negative", [doc("Activity"), space("Hypothetical", [{ kind: "typeVar", name: "U", edgeModel: null }])]),
  ];
  const env = { U: [doc("Transfer")] };
  const types = (found: RelationOption[] | undefined) => found?.map((option) => ("type" in option ? option.type : option.kind));
  expect(types(spaceOptions(options, env, []))).toEqual(["Activity", "Negative"]);
  expect(types(spaceOptions(options, env, ["Negative"]))).toEqual(["Activity", "Hypothetical"]);
  // (a type variable inside is bound as the field binds it)
  expect(types(spaceOptions(options, env, ["Negative", "Hypothetical"]))).toEqual(["Transfer"]);
  // (a space the field does not accept there)
  expect(spaceOptions(options, env, ["Hypothetical"])).toBeUndefined();
  const pasted = { type: "Transfer", label: "Gift", date: { type: "ExactDate", year: 800 } };
  expect(inSpaces(definitions, ["Negative", "Hypothetical"], pasted)).toEqual({
    type: "Negative",
    contents: [{ type: "Hypothetical", contents: [pasted] }],
  });
});

test("a type variable with an edge model gives it to what it stands for (`list[ViaEdge[T, Probability]]`)", () => {
  const env = { T: [{ kind: "entity", type: "Person", edgeModel: null }, doc("Note")] as RelationOption[] };
  const edgeModels = (options: RelationOption[]) => options.map((option) => ("edgeModel" in option ? option.edgeModel : undefined));
  const resolved = resolveOptions([{ kind: "typeVar", name: "T", edgeModel: "Probability" }], env);
  expect(edgeModels(resolved)).toEqual(["Probability", "Probability"]);
  // (what it is bound to is not changed)
  expect(edgeModels(env.T)).toEqual([null, null]);
});

test("a path reads and writes into a tree, making what is not there, and takes things out", () => {
  const root: Record<string, unknown> = {};
  setAt(root, ["a", "b", 1, "c"], "x");
  expect(root).toEqual({ a: { b: [undefined, { c: "x" }] } });
  expect(getAt(root, ["a", "b", 1, "c"])).toBe("x");
  expect(getAt(root, ["a", "z", 1])).toBeUndefined();
  removeAt(root, ["a", "b", 0]);
  expect(getAt(root, ["a", "b"])).toEqual([{ c: "x" }]);
  removeAt(root, ["a", "b"]);
  expect(root).toEqual({ a: {} });
});

test("a new item starts with the one thing a required single field can hold, unless it is an entity", () => {
  expect(blankItem(definitions, "Letter")).toEqual({
    type: "Letter",
    source: { type: "AtPage" },
  });
  expect(blankItem(definitions, "Note")).toEqual({ type: "Note" });
  // (a required list starts empty, and is sent so)
  const withList = {
    models: {
      Bag: model("Bag", {
        fields: [{ name: "items", key: "items", kind: "list", required: true }] as never,
      }),
    },
    enums: {},
  } as unknown as ModelDefinitions;
  expect(blankItem(withList, "Bag")).toEqual({ type: "Bag", items: [] });
  // (a field with a default the class declares starts with it; a copy, so that editing it changes nothing else)
  const withDefaults = {
    models: {
      Counted: model("Counted", {
        fields: [
          { name: "count", key: "count", kind: "literal", type: { type: "int" }, required: false, default: 0 },
          { name: "tags", key: "tags", kind: "list", item: { type: "str" }, required: false, default: ["a"] },
          { name: "note", key: "note", kind: "literal", type: { type: "str" }, required: false, default: null },
        ] as never,
      }),
    },
    enums: {},
  } as unknown as ModelDefinitions;
  const counted = blankItem(withDefaults, "Counted");
  expect(counted).toEqual({ type: "Counted", count: 0, tags: ["a"] });
  (counted.tags as string[]).push("b");
  expect(blankItem(withDefaults, "Counted").tags).toEqual(["a"]);
});

test("what is sent has no meta and no incoming fields, references are only type and id, and empty things are gone", () => {
  const sent = cleanForSave(definitions, {
    type: "Letter",
    id: "l1",
    label: "A letter",
    meta: { version: 2 },
    cited: [{ type: "Note", id: "n" }],
    note: "",
    source: {
      type: "AtPage",
      page: "3",
      target: { type: "Person", id: "p1", label: "Rome", meta: {}, edgeProperties: { level: 2 } },
    },
    aliases: ["a", ""],
    unchosen: [{ type: "Person" }],
    nothing: null,
    zero: 0,
    no: false,
  });
  expect(sent).toEqual({
    type: "Letter",
    id: "l1",
    label: "A letter",
    source: { type: "AtPage", page: "3", target: { type: "Person", id: "p1", edgeProperties: { level: 2 } } },
    aliases: ["a"],
    unchosen: [],
    nothing: null,
    zero: 0,
    no: false,
  });
});

test("nothing inside a new node is sent with an id, but references to entities keep theirs", () => {
  // (a statement cut and pasted, with its ids, into a new semantic space of the same document)
  const moved = { type: "Transfer", id: "t1", label: "Gift", date: { type: "Note", id: "d1" }, to: { type: "Person", id: "p1" } };
  const sent = cleanForSave(definitions, {
    type: "Letter",
    id: "l1",
    statements: [{ type: "Negative", contents: [moved] }, { type: "Activity", id: "a1", date: { type: "Note", id: "d2" } }],
  });
  expect(sent).toEqual({
    type: "Letter",
    id: "l1",
    statements: [
      { type: "Negative", contents: [{ type: "Transfer", label: "Gift", date: { type: "Note" }, to: { type: "Person", id: "p1" } }] },
      // (what is saved already keeps its ids)
      { type: "Activity", id: "a1", date: { type: "Note", id: "d2" } },
    ],
  });
});
