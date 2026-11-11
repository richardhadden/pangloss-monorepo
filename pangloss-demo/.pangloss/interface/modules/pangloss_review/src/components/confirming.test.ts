import type { ModelDefinitions } from "@pangloss/interface-core";
import { describe, expect, it } from "vitest";
import { candidatesIn, confirmedPart, entityInPlace, fresh, partAt, pathOf, strangers, targetOfOne } from "./confirming";
import type { Suggestion } from "../api";

const model = (kind: string, fields: string[] = []) => ({ kind, fields: fields.map((name) => ({ name, key: name })) });
const definitions = {
  models: {
    Person: model("Entity"),
    WeightedAlternative: model("Conjunction", ["alternatives"]),
    Identification: model("ReifiedRelation", ["identifiedBy", "target", "uris"]),
    Reading: model("ReifiedRelation", ["identifiedBy", "target", "uris", "note"]),
  },
} as unknown as ModelDefinitions;

const suggestion = {
  type: "SuggestedReading",
  id: "s1",
  identifiedBy: "extractor",
  toolchainVersion: "1.2",
  uris: ["http://example.org/john"],
  note: "smudged",
  model: "big",
  edgeProperties: { certainty: 1 },
  target: [
    {
      type: "WeightedAlternative",
      id: "w1",
      alternatives: [
        { type: "Person", id: "p1", label: "John", edgeProperties: { percent: 70 } },
        { type: "Person", id: "p2", label: "Jack", edgeProperties: { percent: 30 } },
      ],
    },
  ],
};

describe("a suggestion confirmed in a form", () => {
  it("is the same part as the class it becomes, with what the two have in common", () => {
    expect(confirmedPart(definitions, suggestion, "Reading")).toEqual({
      type: "Reading",
      id: "s1",
      note: "smudged",
      edgeProperties: { certainty: 1 },
      target: suggestion.target,
      uris: suggestion.uris,
    });
    // (who identified it is for the server to say; the toolchain's version is not kept)
    expect(confirmedPart(definitions, suggestion, "Identification")).toEqual({
      type: "Identification",
      id: "s1",
      edgeProperties: { certainty: 1 },
      target: suggestion.target,
      uris: suggestion.uris,
    });
  });

  it("keeps the URIs only while it has several candidates: one candidate is given them by the server", () => {
    const one = { ...suggestion, target: [{ type: "Person", id: "p1", label: "John" }] };
    expect(confirmedPart(definitions, one, "Identification")).toEqual({
      type: "Identification",
      id: "s1",
      edgeProperties: { certainty: 1 },
      target: one.target,
    });
  });

  it("has the candidates the form holds, each with how likely", () => {
    expect(candidatesIn(definitions, suggestion)).toEqual([
      { type: "Person", id: "p1", label: "John", percent: 70 },
      { type: "Person", id: "p2", label: "Jack", percent: 30 },
    ]);
    expect(candidatesIn(definitions, { target: [{ type: "Person", id: "p1", label: "John" }] })).toEqual([
      { type: "Person", id: "p1", label: "John", percent: undefined },
    ]);
  });
});

describe("the other parts of the document, changed in the form with one", () => {
  const form = {
    id: "head",
    testimonies: [
      { id: "t1", givenBy: [{ type: "Unreconciled", id: "m1", label: "Iohannes", edgeProperties: { certainty: 2 } }], names: [suggestion] },
    ],
  };

  it("are found by their ids, where the form has them", () => {
    expect(pathOf(form, "s1")).toEqual(["testimonies", 0, "names", 0]);
    expect(pathOf(form, "m1")).toEqual(["testimonies", 0, "givenBy", 0]);
    // (not the item itself, and not what is no longer there)
    expect(pathOf(form, "head")).toBeUndefined();
    expect(pathOf(form, "gone")).toBeUndefined();
    expect(partAt(form, ["testimonies", 0, "givenBy", 0])?.label).toBe("Iohannes");
  });

  it("are given what this one holds, made anew: the entities as they are, the wrappers without their ids", () => {
    expect(fresh(definitions, suggestion.target)).toEqual([
      {
        type: "WeightedAlternative",
        alternatives: [
          { type: "Person", id: "p1", label: "John", edgeProperties: { percent: 70 } },
          { type: "Person", id: "p2", label: "Jack", edgeProperties: { percent: 30 } },
        ],
      },
    ]);
  });

  it("an entity takes a mention's place with the properties of the relation, and is the one alternative of a suggestion", () => {
    const john = { type: "Person", id: "p1", label: "John" };
    expect(entityInPlace(form.testimonies[0].givenBy[0], john)).toEqual({ ...john, edgeProperties: { certainty: 2 } });
    expect(targetOfOne(suggestion.target, john)).toEqual([
      { type: "WeightedAlternative", alternatives: [{ ...john, edgeProperties: { percent: 100 } }] },
    ]);
    expect(targetOfOne([{ type: "Person", id: "p2" }], john)).toEqual([john]);
  });

  it("someone who has its URI and is not a candidate is said", () => {
    const asked = {
      candidates: [{ type: "Person", id: "p1" }],
      known: [
        { type: "Person", id: "p1" },
        { type: "Person", id: "p9", label: "Another" },
      ],
    } as unknown as Suggestion;
    expect(strangers(asked)).toEqual([{ type: "Person", id: "p9", label: "Another" }]);
  });
});
