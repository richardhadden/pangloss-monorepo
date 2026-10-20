import { expect, test } from "vitest";
import { getModel, headModels, relatedModelNames } from "./index";
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
