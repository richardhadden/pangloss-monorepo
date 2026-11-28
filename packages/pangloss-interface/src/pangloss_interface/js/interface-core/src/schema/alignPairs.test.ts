import { expect, test } from "vitest";
import type { FieldDefinition, ModelDefinition, ModelDefinitions } from "../types";
import { align, partKeys } from "./align";

// Two different statements lined up (`{ pair: "place" }`): they share no ids but those of the entities both name, so
// the parts of a field are matched by a shared id where there is one, else by place

const base = { description: null, dbField: false, readOnly: false, required: false, nullable: true, validators: [] };
const literal = (name: string): FieldDefinition => ({ ...base, name, key: name, kind: "literal", type: { type: "str" } }) as FieldDefinition;
const relation = (name: string, kind: "document" | "entity", type: string, many = true): FieldDefinition =>
  ({ ...base, name, key: name, kind: "relation", many, reverseName: "r", options: [{ kind, type, edgeModel: null }], subclasses: [] }) as FieldDefinition;
const model = (name: string, kind: ModelDefinition["kind"], fields: FieldDefinition[]) =>
  ({ name, kind, abstract: false, parent: null, concreteTypes: [], typeParameters: [], interfaceMeta: null, fields, incoming: [] }) as unknown as ModelDefinition;

const DEFINITIONS = {
  models: {
    Baptism: model("Baptism", "Document", [
      relation("baptised", "entity", "Person", false),
      relation("town", "entity", "Town", false),
      relation("witnesses", "entity", "Person"),
      relation("acts", "document", "Act"),
      literal("note"),
    ]),
    Act: model("Act", "Document", [literal("what")]),
    Person: model("Person", "Entity", []),
    Town: model("Town", "Entity", []),
  },
  enums: {},
} as unknown as ModelDefinitions;

const DEFINITIONS_MORE = {
  models: {
    ...DEFINITIONS.models,
    Baptism: model("Baptism", "Document", [
      relation("witnesses", "entity", "Person"),
      relation("acts", "document", "Act"),
    ]),
    Rite: model("Rite", "Document", [literal("how")]),
    InRole: model("InRole", "ReifiedRelation", [
      relation("target", "entity", "Person"),
      relation("at", "entity", "Town"),
    ]),
  },
  enums: {},
} as unknown as ModelDefinitions;

const anna = { id: "anna", type: "Person", label: "Anna" };
const joos = { id: "joos", type: "Person", label: "Joos" };
const pieter = { id: "pieter", type: "Person", label: "Pieter" };
const ghent = { id: "ghent", type: "Town", label: "Ghent" };
const bruges = { id: "bruges", type: "Town", label: "Bruges" };

const summary = (rows: ReturnType<typeof align>) => rows.map((row) => [row.key, row.cells.map((cell) => cell.mark).join(" ")]);

test("an entity both name is one row by its id; two different ones in one field are one row, changed", () => {
  const a = { type: "Baptism", baptised: anna, town: ghent };
  const b = { type: "Baptism", baptised: anna, town: bruges };
  expect(summary(align(DEFINITIONS, "Baptism", [a, b], { pair: "place" }))).toEqual([
    [".baptised[anna]", "same same"],
    [".town[@0]", "same changed"],
  ]);
  // (by id, as versions of one item are: one removed, one added)
  expect(summary(align(DEFINITIONS, "Baptism", [a, b]))).toEqual([
    [".baptised[anna]", "same same"],
    [".town[ghent]", "same removed"],
    [".town[bruges]", "absent added"],
  ]);
});

test("in a list, the shared ids pair, and the rest by their place among the rest (in the order `mergeOrder` gives)", () => {
  const a = { type: "Baptism", witnesses: [joos, anna] };
  const b = { type: "Baptism", witnesses: [pieter, joos, { id: "kat", type: "Person", label: "Kat" }] };
  expect(summary(align(DEFINITIONS, "Baptism", [a, b], { pair: "place" }))).toEqual([
    [".witnesses[joos]", "same same"],
    [".witnesses[@1]", "absent added"],
    [".witnesses[@0]", "same changed"],
  ]);
});

test("nested documents of two statements never share ids: paired by place, what is in them row by row", () => {
  const a = { type: "Baptism", acts: [{ id: "a1", type: "Act", label: "Water", what: "water" }] };
  const b = {
    type: "Baptism",
    acts: [
      { id: "b1", type: "Act", label: "Water", what: "holy water" },
      { id: "b2", type: "Act", label: "Salt", what: "salt" },
    ],
  };
  expect(summary(align(DEFINITIONS, "Baptism", [a, b], { pair: "place" }))).toEqual([
    [".acts[@0]", "same same"],
    [".acts[@0].what", "same changed"],
    [".acts[@1]", "absent added"],
    [".acts[@1].what", "absent added"],
  ]);
});

test("the keys: by id unless asked; by place, an id kept only where another column has it", () => {
  const parts = [[anna, { type: "Act" }], [{ type: "Act" }, anna, joos]];
  expect(partKeys(parts)).toEqual([["anna", "#1"], ["#0", "anna", "joos"]]);
  expect(partKeys(parts, "place")).toEqual([["anna", "@0"], ["@0", "anna", "@1"]]);
});

test("two entities of one class and label (namesakes) are two, by place: changed; versions of one item keep theirs", () => {
  const anna2 = { id: "anna-2", type: "Person", label: "Anna" };
  const a = { type: "Baptism", baptised: anna };
  const b = { type: "Baptism", baptised: anna2 };
  expect(summary(align(DEFINITIONS, "Baptism", [a, b], { pair: "place" }))).toEqual([[".baptised[@0]", "same changed"]]);
  // (one entity, the same id, is the same)
  expect(summary(align(DEFINITIONS, "Baptism", [a, a], { pair: "place" }))).toEqual([[".baptised[anna]", "same same"]]);
});

test("a wrapper beside a plain entity at one place: one row, changed, and what the wrapper holds drawn on its side", () => {
  const withRole = { type: "Baptism", acts: [{ id: "a1", type: "Act", label: "Water", what: "water" }] };
  const plain = { type: "Baptism", acts: [{ id: "r1", type: "Rite", label: "Water", how: "poured" }] };
  const rows = align(DEFINITIONS_MORE, "Baptism", [withRole, plain], { pair: "place" });
  expect(summary(rows)).toEqual([
    [".acts[@0]", "same changed"],
    [".acts[@0]<Act>.what", "same removed"],
    [".acts[@0]<Rite>.how", "absent added"],
  ]);
  const holds = { type: "Baptism", witnesses: [{ type: "InRole", target: [joos], at: [ghent] }] };
  const bare = { type: "Baptism", witnesses: [joos] };
  const mixed = align(DEFINITIONS_MORE, "Baptism", [holds, bare], { pair: "place" });
  expect(summary(mixed)).toEqual([
    [".witnesses[@0]", "same changed"],
    [".witnesses[@0]<InRole>.target[@0]", "same removed"],
    [".witnesses[@0]<InRole>.at[@0]", "same removed"],
  ]);
  // (the head of a part of two types is no entity's chip: each side is drawn as what it is)
  expect(mixed[0]!.entity).toBe(false);
});
