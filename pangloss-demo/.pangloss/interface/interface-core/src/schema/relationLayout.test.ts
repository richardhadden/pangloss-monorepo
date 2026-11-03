import { expect, test } from "vitest";
import type { ModelDefinition, ModelDefinitions, RelationOption } from "../types";
import { reachFor, relationLayout, wrapEntity } from "./relationLayout";

const model = (name: string, kind: ModelDefinition["kind"], fields: object[] = [], parent: string | null = null) =>
  ({ name, kind, parent, abstract: false, typeParameters: ["T"], fields, interfaceMeta: null }) as unknown as ModelDefinition;
const target = (name: string, many = true) => ({
  name,
  key: name,
  kind: "relation",
  many,
  required: true,
  options: [{ kind: "typeVar", name: "T", edgeModel: null }],
});
const entity = (type: string, edgeModel: string | null = null): RelationOption => ({ kind: "entity", type, edgeModel });
const wrapping = (kind: "reifiedRelation" | "conjunction", type: string, options: RelationOption[]): RelationOption =>
  ({ kind, type, edgeModel: null, params: { T: { typeVar: "T", options } } }) as RelationOption;

const definitions = {
  models: {
    Person: model("Person", "Entity"),
    Scribe: model("Scribe", "Entity", [], "Person"),
    Group: model("Group", "Entity"),
    InRole: model("InRole", "ReifiedRelation", [target("target"), { name: "role", key: "role", kind: "literal" }]),
    Identification: model("Identification", "ReifiedRelation", [target("target")]),
    Alternative: model("Alternative", "Conjunction", [target("alternatives")]),
    Causes: model("Causes", "Conjunction", [target("cause", false), target("result", false)]),
  },
  enums: {},
} as unknown as ModelDefinitions;

const identification = wrapping("reifiedRelation", "Identification", [
  wrapping("conjunction", "Alternative", [entity("Person", "Probability")]),
]);

test("the entities are searched for, and the rest are buttons", () => {
  const layout = relationLayout(definitions, [entity("Group"), entity("Person"), identification], {});
  expect(layout.search).toEqual([
    { type: "Group", wrappers: [] },
    { type: "Person", wrappers: [] },
  ]);
  expect(layout.rest).toEqual([{ spaces: [], type: "Identification" }]);
});

test("with a default reified type, what it holds is searched for, through a conjunction, and it is not a button", () => {
  const inRole = wrapping("reifiedRelation", "InRole", [entity("Group")]);
  const layout = relationLayout(definitions, [inRole, identification], {}, "Identification");
  expect(layout.search.map((reach) => reach.type)).toEqual(["Person"]);
  expect(layout.rest).toEqual([{ spaces: [], type: "InRole" }]);
  const reach = reachFor(definitions, layout.search, "Scribe")!;
  expect(wrapEntity(definitions, reach, { type: "Scribe", id: "s1" })).toEqual({
    type: "Identification",
    target: [{ type: "Alternative", alternatives: [{ type: "Scribe", id: "s1" }] }],
  });
});

test("a conjunction with several relations is not gone into; a default that reaches nothing falls back", () => {
  const causes = wrapping("conjunction", "Causes", [entity("Person")]);
  const inRole = wrapping("reifiedRelation", "InRole", [causes]);
  const layout = relationLayout(definitions, [inRole], {}, "InRole");
  expect(layout.search).toEqual([]);
  expect(layout.rest).toEqual([{ spaces: [], type: "InRole" }]);
});
