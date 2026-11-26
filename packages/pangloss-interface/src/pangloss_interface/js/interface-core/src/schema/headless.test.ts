import { expect, test } from "vitest";
import type { ModelDefinitions, RelationOption } from "../types";
import { blankItem } from "./formValue";
import { headlessIn } from "./headless";

const definitions = (headless: true | null, kind = "ReifiedRelation") =>
  ({
    models: {
      AtPage: { name: "AtPage", kind, fields: [], interfaceMeta: { colour: null, headless } },
      Reported: { name: "Reported", kind: "SemanticSpace", fields: [], interfaceMeta: { colour: null, headless } },
      Overheard: {
        name: "Overheard",
        kind: "SemanticSpace",
        parent: "Reported",
        fields: [],
        interfaceMeta: { colour: null, headless },
      },
    },
    enums: {},
  }) as unknown as ModelDefinitions;

const atPage: RelationOption = { kind: "reifiedRelation", type: "AtPage", edgeModel: null, params: {} };
const other: RelationOption = { kind: "entity", type: "Source", edgeModel: null };
const reported: RelationOption = { kind: "semanticSpace", type: "Reported", edgeModel: null, params: {} };
const overheard: RelationOption = { kind: "semanticSpace", type: "Overheard", edgeModel: null, params: {} };
const claim: RelationOption = { kind: "document", type: "Claim", edgeModel: null };
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

test("a headless semantic space has no head where it is the one thing its field holds, and must", () => {
  expect(headlessIn(definitions(true), slot({ options: [reported] }), "Reported")).toBe(true);
});

test("a headless space has its head where there is a choice, a list, or it may be left out", () => {
  // (beside what it would hold, plainly)
  expect(headlessIn(definitions(true), slot({ options: [reported, claim] }), "Reported")).toBe(false);
  // (a class declared below it is offered in the field too: the head says which a value is)
  expect(headlessIn(definitions(true), slot({ options: [reported, overheard] }), "Reported")).toBe(false);
  expect(headlessIn(definitions(true), slot({ options: [reported, overheard] }), "Overheard")).toBe(false);
  expect(headlessIn(definitions(true), slot({ options: [reported], many: true }), "Reported")).toBe(false);
  expect(headlessIn(definitions(true), slot({ options: [reported], required: false }), "Reported")).toBe(false);
});

test("only a space whose model says so is headless, and only as itself", () => {
  expect(headlessIn(definitions(null), slot({ options: [reported] }), "Reported")).toBe(false);
  // (what is in the field is of another type than its one option)
  expect(headlessIn(definitions(true), slot({ options: [reported] }), "Overheard")).toBe(false);
  // (an option that says it is a space, of a model that is not one)
  expect(headlessIn(definitions(true), slot({ options: [{ ...reported, type: "AtPage" }] }), "AtPage")).toBe(false);
});

test("a new item holds its headless space from the start, which is never added, with what is certain of it", () => {
  const field = (key: string, options: RelationOption[], many = false) => ({
    name: key,
    key,
    kind: "relation",
    many,
    required: true,
    options,
    validators: [],
  });
  const between = (headless: true | null): ModelDefinitions =>
    ({
      models: {
        Reported: {
          name: "Reported",
          kind: "SemanticSpace",
          fields: [field("contents", [{ kind: "typeVar", name: "T", edgeModel: null }], true)],
          interfaceMeta: { colour: null, headless },
        },
        Claim: { name: "Claim", kind: "Document", fields: [], interfaceMeta: null },
        Rumour: { name: "Rumour", kind: "Document", fields: [], interfaceMeta: null },
        Report: {
          name: "Report",
          kind: "Document",
          fields: [
            field("account", [
              {
                ...reported,
                params: { T: { typeVar: "T", options: [claim, { ...claim, type: "Rumour" }] } },
              },
            ]),
          ],
          interfaceMeta: null,
        },
      },
      enums: {},
    }) as unknown as ModelDefinitions;
  // (what it holds may be one of two: chosen in it)
  expect(blankItem(between(true), "Report")).toEqual({
    type: "Report",
    account: { type: "Reported", contents: [] },
  });
  // (with its head, it is added as anything else is: inside it, one of the two)
  expect(blankItem(between(null), "Report")).toEqual({ type: "Report" });
});
