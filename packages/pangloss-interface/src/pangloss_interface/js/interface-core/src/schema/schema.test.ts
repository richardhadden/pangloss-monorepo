import { expect, test } from "vitest";
import { getModel, headModels, modelHierarchy, relatedModelNames } from "./index";
import type { ModelDefinition, ModelDefinitions, RelationField } from "../types";

function model(name: string, kind: ModelDefinition["kind"], abstract = false): ModelDefinition {
  return {
    name,
    kind,
    abstract,
    description: null,
    parent: null,
    concreteTypes: [],
    typeParameters: [],
    createWithId: false,
    acceptUrlAsId: false,
    requireLabel: true,
    useInSemanticSpaceLabel: true,
    interfaceMeta: null,
    fields: [],
    incoming: [],
  };
}

const definitions: ModelDefinitions = {
  models: {
    Person: model("Person", "Entity"),
    Agent: model("Agent", "Entity", true),
    Date: model("Date", "Embedded"),
    Book: model("Book", "Document"),
  },
  enums: {},
};

test("only the Documents and Entities that are not abstract have pages", () => {
  expect(headModels(definitions).map((m) => m.name)).toEqual(["Book", "Person"]);
});

test("a model is found by name, and only by its own", () => {
  expect(getModel(definitions, "Person")?.name).toBe("Person");
  expect(getModel(definitions, "toString")).toBeUndefined();
});

test("a relation is to the models it can relate to", () => {
  const field = {
    kind: "relation",
    options: [
      { kind: "entity", type: "Person", edgeModel: null },
      { kind: "typeVar", name: "T", edgeModel: null },
      { kind: "document", type: "Book", edgeModel: null },
    ],
  } as unknown as RelationField;
  expect(relatedModelNames(field)).toEqual(["Book", "Person"]);
});

test("models are in the order of the hierarchy, each below its parent", () => {
  const tree: ModelDefinitions = {
    enums: {},
    models: {
      Transfer: { ...model("Transfer", "Document"), parent: "Statement" },
      Statement: model("Statement", "Document", true),
      Activity: { ...model("Activity", "Document"), parent: "Statement" },
      Factoid: model("Factoid", "Document"),
      Person: model("Person", "Entity"),
    },
  };
  expect(modelHierarchy(tree, "Document").map((m) => [m.model.name, m.depth])).toEqual([
    ["Factoid", 0],
    ["Statement", 0],
    ["Activity", 1],
    ["Transfer", 1],
  ]);
  expect(modelHierarchy(tree, "Entity").map((m) => m.model.name)).toEqual(["Person"]);
});
