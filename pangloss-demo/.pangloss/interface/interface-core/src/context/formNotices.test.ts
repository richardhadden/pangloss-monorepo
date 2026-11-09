// @vitest-environment happy-dom
/**
 * What the form's hooks say at fields (`FormHook.notices`): a narrower field that a bound value cannot go in. In the
 * browser's build of Solid (the notices are a memo, which the server's build never works out again), with `flush()`
 * after writes, as a row of the page reads them after the change.
 */
import { createRoot, flush } from "solid-js";
import { expect, test } from "vitest";
import { createBinder } from "../schema";
import type { FieldProblem } from "../schema";
import type { ModelDefinitions } from "../types";
import { createItemFormState } from "./form";

const relation = (key: string, more: object = {}) => ({ name: key, key, kind: "relation", many: false, options: [], ...more });
const model = (name: string, kind: string, fields: object[] = []) => ({ name, kind, fields, concreteTypes: [name] });
const problem = (path: FieldProblem["path"]): FieldProblem => ({ path, code: "required", params: {}, message: "Required" });

// (a commission of a thing, given to the creations it holds: into `object_created`, which each narrower creation
// has under another name; only a painting can be the painting created)
const entityOptions = (...types: string[]) => types.map((type) => ({ kind: "entity", type, edgeModel: null }));
const created = (name: string, key: string, options: object[], subclasses: string[] = []) =>
  relation(key, { name, options, subclasses });
const creationModels = {
  models: {
    Commission: model("Commission", "Document", [
      relation("thing", { options: entityOptions("PhysicalObject", "Artwork", "Painting") }),
      relation("works", {
        many: true,
        bindings: [{ boundField: "thing", childFields: ["objectCreated"], allowedTypes: [], excludedTypes: [], converted: false }],
      }),
    ]),
    CreationOfPhysicalObject: {
      ...model("CreationOfPhysicalObject", "Document", [
        created("object_created", "objectCreated", entityOptions("PhysicalObject", "Artwork", "Painting")),
      ]),
      parent: null,
    },
    CreationOfArtwork: {
      ...model("CreationOfArtwork", "Document", [
        created("artwork_created", "artworkCreated", entityOptions("Artwork", "Painting"), ["object_created"]),
      ]),
      parent: "CreationOfPhysicalObject",
    },
    CreationOfPainting: {
      ...model("CreationOfPainting", "Document", [
        created("painting_created", "paintingCreated", entityOptions("Painting"), ["artwork_created", "object_created"]),
      ]),
      parent: "CreationOfArtwork",
    },
    PhysicalObject: model("PhysicalObject", "Entity"),
    Artwork: { ...model("Artwork", "Entity"), parent: "PhysicalObject" },
    Painting: { ...model("Painting", "Entity"), parent: "Artwork" },
  },
  enums: {},
} as unknown as ModelDefinitions;
const painting = (id: string) => ({ type: "Painting", id, label: id });
const artwork = (id: string) => ({ type: "Artwork", id, label: id });
const commission = () => createItemFormState({ type: "Commission" }, { binder: createBinder(creationModels) });

// (the notices are a memo over the item: read after the writes are flushed, as a row of the page reads them)
const noticesAt = (state: ReturnType<typeof createItemFormState>, path: (string | number)[]) => {
  flush();
  return state.problemsAt(path).map((problem) => [problem.code, problem.params.value]);
};
// (the form made in a root, as a page makes it, so that its memo has an owner; written to outside it, as an event is)
const owned = () => createRoot((dispose) => [commission(), dispose] as const);

test("a narrower field the bound value cannot go in says so, until it is filled in or the value fits", () => {
  const [state, dispose] = owned();
  state.set(["thing"], artwork("The thing"));
  state.set(["works", 0], { type: "CreationOfArtwork" });
  state.set(["works", 1], { type: "CreationOfPainting" });
  const painted = ["works", 1, "paintingCreated"];
  expect(noticesAt(state, painted)).toEqual([["bound_not_held", "The thing"]]);
  // (not where it went: the artwork created, nor the creation itself)
  expect(noticesAt(state, ["works", 0, "artworkCreated"])).toEqual([]);
  expect(noticesAt(state, ["works", 1])).toEqual([]);
  // (a painting: given, and nothing to say)
  state.set(["thing"], painting("p1"));
  expect(noticesAt(state, painted)).toEqual([]);
  // (back to an artwork: emptied, and said why)
  state.set(["thing"], artwork("Another"));
  expect(noticesAt(state, painted)).toEqual([["bound_not_held", "Another"]]);
  // (filled in by hand: nothing to say)
  state.set(painted, painting("mine"));
  expect(noticesAt(state, painted)).toEqual([]);
  // (nothing bound: nothing to say)
  state.set(["works", 2], { type: "CreationOfPainting" });
  state.remove(["thing"]);
  expect(noticesAt(state, ["works", 2, "paintingCreated"])).toEqual([]);
  dispose();
});

test("a notice is beside the problems found on save, and stays when they are replaced", () => {
  const [state, dispose] = owned();
  state.set(["thing"], artwork("The thing"));
  state.set(["works", 0], { type: "CreationOfPainting" });
  const painted = ["works", 0, "paintingCreated"];
  state.registerRow(painted);
  state.setProblems([problem(painted)]);
  flush();
  expect(state.problemsAt(painted).map((found) => found.code)).toEqual(["required", "bound_not_held"]);
  state.setProblems([]);
  flush();
  expect(state.problemsAt(painted).map((found) => found.code)).toEqual(["bound_not_held"]);
  dispose();
});

