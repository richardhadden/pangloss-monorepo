import { expect, test } from "vitest";
import type { ModelDefinitions, RelationOption } from "../types";
import { headlessIn } from "./headless";

const definitions = (headless: true | null, kind = "ReifiedRelation") =>
  ({
    models: { AtPage: { name: "AtPage", kind, fields: [], interfaceMeta: { colour: null, headless } } },
    enums: {},
  }) as unknown as ModelDefinitions;

const atPage: RelationOption = { kind: "reifiedRelation", type: "AtPage", edgeModel: null, params: {} };
const other: RelationOption = { kind: "entity", type: "Source", edgeModel: null };
const slot = (given: Partial<{ many: boolean; required: boolean; options: RelationOption[] }> = {}) => ({
  many: false,
  required: true,
  options: [atPage],
  ...given,
});

test("a headless reified relation has no head where it is the one thing its field holds, and must", () => {
  expect(headlessIn(definitions(true), slot(), "AtPage")).toBe(true);
});

test("it has its head where there is a choice, a list, or it may be left out", () => {
  expect(headlessIn(definitions(true), slot({ options: [atPage, other] }), "AtPage")).toBe(false);
  expect(headlessIn(definitions(true), slot({ many: true }), "AtPage")).toBe(false);
  expect(headlessIn(definitions(true), slot({ required: false }), "AtPage")).toBe(false);
  expect(headlessIn(definitions(true), undefined, "AtPage")).toBe(false);
});

test("only a reified relation whose model says so is headless", () => {
  expect(headlessIn(definitions(null), slot(), "AtPage")).toBe(false);
  expect(headlessIn(definitions(true, "Conjunction"), slot(), "AtPage")).toBe(false);
  expect(headlessIn(definitions(true), slot(), "Source")).toBe(false);
});
