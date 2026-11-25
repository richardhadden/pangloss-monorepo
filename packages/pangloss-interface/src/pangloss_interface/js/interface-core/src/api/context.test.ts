import { expect, test } from "vitest";
import type { ModelDefinition, ModelDefinitions } from "../types";
import { contextPath, contextTrail, wrappingSpaces } from "./context";
import type { PathEntry } from "./types";

const model = (name: string, kind: string, useInSemanticSpaceLabel = true) =>
  ({ name, kind, useInSemanticSpaceLabel }) as unknown as ModelDefinition;

const definitions = {
  models: {
    Factoid: model("Factoid", "Document"),
    Order: model("Order", "Document"),
    Service: model("Service", "Document", false),
    Negative: model("Negative", "SemanticSpace"),
    Doubt: model("Doubt", "SemanticSpace"),
    Causes: model("Causes", "Conjunction"),
    Involves: model("Involves", "ReifiedRelation"),
  },
} as unknown as ModelDefinitions;

const at = (kind: PathEntry["kind"], type: string, id: string, field: string): PathEntry => ({ kind, type, id, field });

test("the spaces an item is in are its meta's semanticSpaces, outermost first", () => {
  expect(wrappingSpaces(undefined)).toEqual([]);
  expect(wrappingSpaces(null)).toEqual([]);
  expect(wrappingSpaces({})).toEqual([]);
  expect(wrappingSpaces({ semanticSpaces: null })).toEqual([]);
  expect(wrappingSpaces({ semanticSpaces: ["Doubt", "Negative"] })).toEqual(["Doubt", "Negative"]);
});

test("the spaces are read from semanticSpaces alone: data stored before the path has them and no path", () => {
  const stored = { semanticSpaces: ["Negative"], path: [] };
  expect(wrappingSpaces(stored)).toEqual(["Negative"]);
});

test("nothing is round a head, nor round an item stored before the path", () => {
  expect(contextPath(undefined, definitions)).toEqual([]);
  expect(contextPath(null, definitions)).toEqual([]);
  expect(contextPath([], definitions)).toEqual([]);
});

test("the head is not round the item: it is shown apart", () => {
  expect(contextPath([at("document", "Factoid", "f1", "statements")], definitions)).toEqual([]);
  expect(contextPath([at("entity", "Person", "p1", "roles")], definitions)).toEqual([]);
});

test("the spaces and the documents after the head, outermost first, each with its kind, type, id and field", () => {
  const path = [
    at("document", "Factoid", "f1", "statements"),
    at("space", "Doubt", "d1", "contents"),
    at("space", "Negative", "n1", "contents"),
    at("document", "Order", "o1", "thing_ordered"),
  ];
  expect(contextPath(path, definitions)).toEqual(path.slice(1));
  expect(contextTrail(path, definitions)).toEqual(["Doubt", "Negative", "Order"]);
});

test("a reified relation, a conjunction and an embedded object are passed over", () => {
  const path = [
    at("document", "Factoid", "f1", "statements"),
    at("document", "Order", "o1", "carried_out"),
    at("reified", "Involves", "r1", "target"),
    at("conjunction", "Causes", "c1", "result"),
    at("embedded", "Date", "e1", "about"),
  ];
  // (the document's own field is what it holds the rest by: the one that is said)
  expect(contextPath(path, definitions)).toEqual([at("document", "Order", "o1", "carried_out")]);
  expect(contextTrail(path, definitions)).toEqual(["Order"]);
});

test("a document of a class that is not to be shown in a trail is left out; a space is not", () => {
  const path = [
    at("document", "Factoid", "f1", "statements"),
    at("space", "Negative", "n1", "contents"),
    at("document", "Service", "s1", "parts"),
  ];
  expect(contextTrail(path, definitions)).toEqual(["Negative"]);
});

test("a document whose class the models do not know is kept", () => {
  const path = [at("document", "Factoid", "f1", "statements"), at("document", "Unknown", "u1", "parts")];
  expect(contextTrail(path, definitions)).toEqual(["Unknown"]);
});

test("an entry gives only its four keys, a copy of it", () => {
  const entry = { ...at("document", "Order", "o1", "thing"), extra: 1 } as PathEntry;
  const [shown] = contextPath([at("document", "Factoid", "f1", "statements"), entry], definitions);
  expect(shown).toEqual(at("document", "Order", "o1", "thing"));
  expect(shown).not.toBe(entry);
});
