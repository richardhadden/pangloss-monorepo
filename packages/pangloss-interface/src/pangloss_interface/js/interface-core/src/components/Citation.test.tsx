import { describe, expect, it } from "vitest";
import type { ModelDefinition, ModelDefinitions } from "../types";
import { citableParts, citableTypes, citedHref } from "./Citation";

const model = (name: string, kind: ModelDefinition["kind"], concreteTypes: string[] = [name]) =>
  ({ name, kind, parent: null, abstract: false, concreteTypes, fields: [], incoming: [] }) as unknown as ModelDefinition;

const definitions = {
  models: {
    Statement: model("Statement", "Document", ["Birth", "Naming"]),
    Birth: model("Birth", "Document"),
    Naming: model("Naming", "Document"),
    Factoid: model("Factoid", "Document"),
    Negative: model("Negative", "SemanticSpace"),
    Hypothetical: model("Hypothetical", "SemanticSpace"),
    InRole: model("InRole", "ReifiedRelation"),
    Person: model("Person", "Entity"),
    PGCitation: model("PGCitation", "Document"),
  },
  enums: {},
} as unknown as ModelDefinitions;

describe("what may be cited", () => {
  it("is each class allowed and its subclasses", () => {
    expect([...citableTypes(definitions, ["Statement"])].sort()).toEqual(["Birth", "Naming"]);
    expect([...citableTypes(definitions, ["Birth", "Factoid"])].sort()).toEqual(["Birth", "Factoid"]);
    // (a class the models do not have is kept as it is named)
    expect([...citableTypes(definitions, ["Gone"])]).toEqual(["Gone"]);
  });

  const factoid = {
    type: "Factoid",
    id: "f",
    label: "A factoid",
    meta: { type: "Birth", id: "not-a-part" },
    statements: [
      { type: "Birth", id: "b", label: "Ann is born", person: { type: "Person", id: "p", label: "Ann" } },
      {
        type: "Negative",
        id: "n",
        contents: [
          {
            type: "Hypothetical",
            id: "h",
            contents: [{ type: "Naming", id: "m", label: "Called Anna" }],
          },
        ],
      },
      // (a citation is of another document: what it names is not a part of this one)
      { type: "Naming", id: "c", label: "", evidence: [{ type: "PGCitation", id: "x", targetType: "Birth", targetId: "b" }] },
    ],
  };

  it("finds the parts of a document of the classes allowed, with the spaces round each", () => {
    const types = citableTypes(definitions, ["Statement"]);
    expect(citableParts(definitions, factoid, types)).toEqual([
      { type: "Birth", id: "b", label: "Ann is born", spaces: [] },
      { type: "Naming", id: "m", label: "Called Anna", spaces: ["Negative", "Hypothetical"] },
      { type: "Naming", id: "c", label: "", spaces: [] },
    ]);
  });

  it("has the document itself when that is allowed, and nothing of an entity", () => {
    expect(citableParts(definitions, factoid, new Set(["Factoid"]))).toEqual([
      { type: "Factoid", id: "f", label: "A factoid", spaces: [] },
    ]);
    expect(citableParts(definitions, factoid, new Set(["Person"]))).toEqual([]);
  });
});

describe("where a cited document is", () => {
  it("is its own page, or its document's with the part on show", () => {
    expect(citedHref("Factoid", "f", "f")).toBe("/Factoid/f");
    expect(citedHref("Factoid", "f 1", "b")).toBe("/Factoid/f%201?show=b");
  });
});
