import { createRoot, flush } from "solid-js";
import { expect, test } from "vitest";
import { createBinder, createFormHooks } from "../schema";
import type { FieldProblem, FormData } from "../schema";
import type { ModelDefinitions } from "../types";
import { createItemFormState } from "./form";

const problem = (path: FieldProblem["path"]): FieldProblem => ({ path, code: "required", params: {}, message: "Required" });

function withState<T>(run: (state: ReturnType<typeof createItemFormState>) => T): T {
  return createRoot((dispose) => {
    const result = run(createItemFormState({ type: "Factoid", statements: [{ type: "Activity" }, { type: "Activity" }] }));
    dispose();
    return result;
  });
}

test("a problem is shown at the row with the longest path it is under; one with no row is placed nowhere", () => {
  withState((state) => {
    state.registerRow(["year"]);
    state.registerRow(["statements"]);
    state.registerRow(["statements", 1, "text"]);
    state.registerRow(["when"]);
    const placed = state.setProblems([
      problem(["year"]),
      problem(["statements", 1, "text"]),
      problem(["statements", 0, "text"]),
      // (inside an editor of its own, with no rows: at the field)
      problem(["when", "year"]),
      problem(["elsewhere"]),
    ]);
    expect(placed.map(({ row }) => row)).toEqual([
      ["year"],
      ["statements", 1, "text"],
      ["statements"],
      ["when"],
      undefined,
    ]);
    flush();
    expect(state.problemsAt(["statements"]).map((found) => found.path)).toEqual([["statements", 0, "text"]]);
    expect(state.problemsAt(["when"]).map((found) => found.path)).toEqual([["when", "year"]]);
  });
});

test("a row that is gone no longer takes problems; one registered twice stays until both are gone", () => {
  withState((state) => {
    const first = state.registerRow(["year"]);
    const second = state.registerRow(["year"]);
    first();
    expect(state.setProblems([problem(["year"])])[0]!.row).toEqual(["year"]);
    second();
    expect(state.setProblems([problem(["year"])])[0]!.row).toBeUndefined();
  });
});

test("changing a value takes away the problems in it and of what it is in; removing from a list, those of the list", () => {
  withState((state) => {
    state.registerRow(["year"]);
    state.registerRow(["statements"]);
    state.setProblems([problem(["year"]), problem(["statements"]), problem(["statements", 1, "text"]), problem(["label"])]);
    flush();
    state.set(["statements", 1, "text"], "met");
    flush();
    expect(state.problems().map(({ problem }) => problem.path)).toEqual([["year"], ["label"]]);
    state.setProblems([problem(["statements", 0, "text"]), problem(["statements", 1, "text"]), problem(["year"])]);
    flush();
    state.remove(["statements", 0]);
    flush();
    expect(state.problems().map(({ problem }) => problem.path)).toEqual([["year"]]);
  });
});

// (a fill that gives a statement a date: see `fillEmbedded` for the one the calendar gives)
const DAY = { type: "ExactDate", year: 1500, month: 3, day: 2 };
const fill = (item: FormData): FormData => (item.type === "Activity" && !item.date ? { ...item, date: DAY } : item);

test("a form with a fill fills what is added to it", () => {
  const state = createItemFormState({ type: "Factoid", statements: [] }, { fill });
  state.set(["statements", 0], { type: "Activity" });
  expect(state.get(["statements", 0, "date"])).toEqual(DAY);
  // (a date taken away stays away; one changed is not filled)
  state.remove(["statements", 0, "date"]);
  state.set(["statements", 0, "involves"], []);
  expect(state.get(["statements", 0, "date"])).toBeUndefined();
  state.set(["statements", 0, "date"], { type: "Period" });
  expect(state.get(["statements", 0, "date"])).toEqual({ type: "Period" });
});

// (who received an order is who gives, or who orders in turn, in what is ordered: `bind_to_child_field`)
const binding = { boundField: "orderedTo", childFields: ["givenBy", "orderedBy"], allowedTypes: [], excludedTypes: [], converted: false };
const relation = (key: string, more: object = {}) => ({ name: key, key, kind: "relation", many: false, options: [], ...more });
const model = (name: string, kind: string, fields: object[] = []) => ({ name, kind, fields, concreteTypes: [name] });
const bound = {
  models: {
    Order: model("Order", "Document", [
      relation("orderedBy"),
      relation("orderedTo"),
      relation("thingOrdered", { bindings: [binding] }),
    ]),
    Wished: model("Wished", "SemanticSpace", [relation("contents", { many: true })]),
    Transfer: model("Transfer", "Document", [relation("givenBy"), { name: "item", key: "item", kind: "literal" }]),
    Named: model("Named", "ReifiedRelation", [relation("target", { many: true })]),
    Person: model("Person", "Entity"),
  },
  enums: {},
} as unknown as ModelDefinitions;
const person = (id: string) => ({ type: "Person", id, label: id.toUpperCase() });

test("a bound field is copied to what its relation holds, and follows it until that is changed", () => {
  const state = createItemFormState({ type: "Order" }, { binder: createBinder(bound) });
  state.set(["orderedTo"], person("a"));
  // (what is added is given it)
  state.set(["thingOrdered"], { type: "Wished", contents: [{ type: "Transfer" }] });
  const givenBy = ["thingOrdered", "contents", 0, "givenBy"];
  expect(state.get(givenBy)).toEqual(person("a"));
  // (it follows the bound field)
  state.set(["orderedTo"], person("b"));
  expect(state.get(givenBy)).toEqual(person("b"));
  // (typing elsewhere does not change it)
  state.set(["thingOrdered", "contents", 0, "item"], "silver");
  expect(state.get(givenBy)).toEqual(person("b"));
  // (changed in the child, it is the child's own, and stays when the bound field changes)
  state.set(givenBy, person("c"));
  state.set(["orderedTo"], person("d"));
  expect(state.get(givenBy)).toEqual(person("c"));
  // (one added now has the bound field's value; and the bound field taken away takes it from what follows it)
  state.set(["thingOrdered", "contents", 1], { type: "Transfer" });
  expect(state.get(["thingOrdered", "contents", 1, "givenBy"])).toEqual(person("d"));
  state.remove(["orderedTo"]);
  expect(state.get(["thingOrdered", "contents", 1, "givenBy"])).toBeUndefined();
  expect(state.get(givenBy)).toEqual(person("c"));
});

test("an order passed on: each is given by the one who received the order above it, the nearest binding", () => {
  const state = createItemFormState({ type: "Order" }, { binder: createBinder(bound) });
  state.set(["orderedTo"], person("count"));
  state.set(["thingOrdered"], {
    type: "Wished",
    contents: [{ type: "Order", orderedTo: person("messenger"), thingOrdered: { type: "Wished", contents: [{ type: "Transfer" }] } }],
  });
  const inner = ["thingOrdered", "contents", 0];
  const deep = [...inner, "thingOrdered", "contents", 0, "givenBy"];
  expect(state.get([...inner, "orderedBy"])).toEqual(person("count"));
  expect(state.get(deep)).toEqual(person("messenger"));
  // (the outer changed: the inner order follows, what the inner order holds is its own)
  state.set([...inner, "orderedTo"], person("count"));
  expect(state.get(deep)).toEqual(person("count"));
  state.set(["orderedTo"], person("bishop"));
  expect(state.get([...inner, "orderedBy"])).toEqual(person("bishop"));
  expect(state.get(deep)).toEqual(person("count"));
});

test("a reified relation is copied as a new one (without its id), and still follows", () => {
  const state = createItemFormState(
    { type: "Order", orderedTo: { type: "Named", id: "n1", target: [person("a")] }, thingOrdered: { type: "Wished", contents: [] } },
    { binder: createBinder(bound) },
  );
  state.set(["thingOrdered", "contents", 0], { type: "Transfer" });
  const givenBy = ["thingOrdered", "contents", 0, "givenBy"];
  expect(state.get(givenBy)).toEqual({ type: "Named", target: [person("a")] });
  state.set(["orderedTo", "target", 0], person("b"));
  expect(state.get(givenBy)).toEqual({ type: "Named", target: [person("b")] });
});

// (who commissioned the works pays for them: a binding to the things made, and every kind of one below, but not a
// sculpture or a kind of one; and one to anything dated)
const paidBy = (more: object = {}) => ({
  boundField: "commissionedBy",
  childFields: ["paidBy"],
  allowedTypes: [],
  excludedTypes: [],
  converted: false,
  ...more,
});
const made = (name: string, parent: string | null, traits: string[] = []) => ({
  ...model(name, "Document", [relation("paidBy")]),
  parent,
  traits,
});
const commissions = (bindings: object[]) =>
  ({
    models: {
      Commission: model("Commission", "Document", [
        relation("commissionedBy"),
        relation("works", { many: true, bindings }),
      ]),
      Made: made("Made", null),
      PaintingMade: made("PaintingMade", "Made"),
      PortraitMade: made("PortraitMade", "PaintingMade", ["Dated"]),
      SculptureMade: made("SculptureMade", "Made"),
      BustMade: made("BustMade", "SculptureMade"),
      Person: model("Person", "Entity"),
    },
    enums: {},
  }) as unknown as ModelDefinitions;
const kinds = ["Made", "PaintingMade", "PortraitMade", "SculptureMade", "BustMade"];
const paid = (bindings: object[]) => {
  const state = createItemFormState({ type: "Commission" }, { binder: createBinder(commissions(bindings)) });
  state.set(["commissionedBy"], person("duke"));
  kinds.forEach((type, at) => state.set(["works", at], { type }));
  return Object.fromEntries(kinds.map((type, at) => [type, state.get(["works", at, "paidBy"]) !== undefined]));
};

test("a binding applies to the types below those it allows, and not to those below those it excludes", () => {
  expect(paid([paidBy({ allowedTypes: ["Made"], excludedTypes: ["SculptureMade"] })])).toEqual({
    Made: true,
    PaintingMade: true,
    PortraitMade: true,
    SculptureMade: false,
    BustMade: false,
  });
  // (one above the type is not allowed by one below it)
  expect(paid([paidBy({ allowedTypes: ["PaintingMade"] })])).toEqual({
    Made: false,
    PaintingMade: true,
    PortraitMade: true,
    SculptureMade: false,
    BustMade: false,
  });
  // (below one allowed and one excluded: excluded)
  expect(paid([paidBy({ allowedTypes: ["Made"], excludedTypes: ["PaintingMade"] })])).toEqual({
    Made: true,
    PaintingMade: false,
    PortraitMade: false,
    SculptureMade: true,
    BustMade: true,
  });
  // (a trait is a name of the type too)
  expect(paid([paidBy({ allowedTypes: ["Dated"] })])).toEqual({
    Made: false,
    PaintingMade: false,
    PortraitMade: true,
    SculptureMade: false,
    BustMade: false,
  });
});

test("a child narrowed to a type below still follows the binding; widened out of what it allows, it is not given it", () => {
  const state = createItemFormState(
    { type: "Commission" },
    { binder: createBinder(commissions([paidBy({ allowedTypes: ["PaintingMade"] })])) },
  );
  state.set(["commissionedBy"], person("duke"));
  state.set(["works", 0], { type: "PaintingMade" });
  expect(state.get(["works", 0, "paidBy"])).toEqual(person("duke"));
  // (narrowed, as ↧ does: the same values, of a type below)
  state.set(["works", 0], { ...(state.get(["works", 0]) as FormData), type: "PortraitMade" });
  state.set(["commissionedBy"], person("count"));
  expect(state.get(["works", 0, "paidBy"])).toEqual(person("count"));
  // (widened to one the binding does not allow: what it had is its own, and it no longer follows)
  state.set(["works", 0], { ...(state.get(["works", 0]) as FormData), type: "Made" });
  state.set(["commissionedBy"], person("bishop"));
  expect(state.get(["works", 0, "paidBy"])).toEqual(person("count"));
});

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

test("a binding into a field reaches the field that stands for it in a narrower type", () => {
  const state = commission();
  state.set(["thing"], painting("p1"));
  state.set(["works", 0], { type: "CreationOfPhysicalObject" });
  state.set(["works", 1], { type: "CreationOfArtwork" });
  state.set(["works", 2], { type: "CreationOfPainting" });
  expect(state.get(["works", 0, "objectCreated"])).toEqual(painting("p1"));
  expect(state.get(["works", 1, "artworkCreated"])).toEqual(painting("p1"));
  expect(state.get(["works", 2, "paintingCreated"])).toEqual(painting("p1"));
  // (and they follow it)
  state.set(["thing"], painting("p2"));
  expect(state.get(["works", 2, "paintingCreated"])).toEqual(painting("p2"));
  // (no field of the old name is made in the narrower ones)
  expect(state.get(["works", 2, "objectCreated"])).toBeUndefined();
});

test("a narrower field is not given a value it cannot hold; one that followed is emptied, and filled again when it fits", () => {
  const state = commission();
  state.set(["thing"], artwork("a1"));
  state.set(["works", 0], { type: "CreationOfArtwork" });
  state.set(["works", 1], { type: "CreationOfPainting" });
  // (an artwork is not a painting)
  expect(state.get(["works", 0, "artworkCreated"])).toEqual(artwork("a1"));
  expect(state.get(["works", 1, "paintingCreated"])).toBeUndefined();
  // (a painting: both are given it)
  state.set(["thing"], painting("p1"));
  expect(state.get(["works", 1, "paintingCreated"])).toEqual(painting("p1"));
  // (back to an artwork: the painting created, which followed, is emptied rather than left as it was)
  state.set(["thing"], artwork("a2"));
  expect(state.get(["works", 0, "artworkCreated"])).toEqual(artwork("a2"));
  expect(state.get(["works", 1, "paintingCreated"])).toBeUndefined();
  // (what was chosen by hand is the child's own, whatever the bound field becomes)
  state.set(["works", 1, "paintingCreated"], painting("mine"));
  state.set(["thing"], painting("p3"));
  expect(state.get(["works", 1, "paintingCreated"])).toEqual(painting("mine"));
});

test("a child narrowed as ↧ does it still follows the binding in the field that stands for the bound one", () => {
  const state = commission();
  state.set(["thing"], painting("p1"));
  state.set(["works", 0], { type: "CreationOfPhysicalObject" });
  // (narrowed: the value moved to the field that stands for the old one)
  state.set(["works", 0], { type: "CreationOfPainting", paintingCreated: state.get(["works", 0, "objectCreated"]) });
  state.set(["thing"], painting("p2"));
  expect(state.get(["works", 0, "paintingCreated"])).toEqual(painting("p2"));
});

// (the alternatives' percentages add up to 100: `SumsTo("percent")`, each at least 1)
const shared = {
  models: {
    Identification: model("Identification", "ReifiedRelation", [relation("target", { many: true })]),
    Alternative: model("Alternative", "Conjunction", [
      relation("alternatives", {
        many: true,
        options: [{ kind: "typeVar", name: "T", edgeModel: "Probability" }],
        validators: [{ name: "SumsTo", field: "percent", total: 100 }],
      }),
    ]),
    Probability: model("Probability", "EdgeModel", [
      { name: "percent", key: "percent", kind: "literal", validators: [{ name: "Ge", ge: 1 }, { name: "Le", le: 100 }] },
    ]),
    Person: model("Person", "Entity"),
  },
  enums: {},
} as unknown as ModelDefinitions;
const alternatives = ["alternatives"];
const percents = (state: ReturnType<typeof createItemFormState>) =>
  ((state.get(alternatives) as FormData[] | undefined) ?? []).map(
    (each) => (each.edgeProperties as FormData | undefined)?.percent,
  );

test("alternatives added share the whole evenly, and the others give way in proportion", () => {
  const state = createItemFormState({ type: "Alternative" }, { binder: createFormHooks(shared) });
  state.set([...alternatives, 0], { type: "Person" });
  expect(percents(state)).toEqual([100]);
  state.set([...alternatives, 1], { type: "Person" });
  expect(percents(state)).toEqual([50, 50]);
  state.set([...alternatives, 0, "edgeProperties", "percent"], 80);
  expect(percents(state)).toEqual([80, 20]);
  state.set([...alternatives, 2], { type: "Person" });
  expect(percents(state)).toEqual([53, 14, 33]);
});

test("dragging one, the others give way in proportion; taking one away, the others share the whole", () => {
  const start = [60, 30, 10].map((percent, at) => ({ ...person(`p${at}`), edgeProperties: { percent } }));
  const state = createItemFormState({ type: "Alternative", alternatives: start }, { binder: createFormHooks(shared) });
  state.set([...alternatives, 0, "edgeProperties", "percent"], 80);
  expect(percents(state)).toEqual([80, 15, 5]);
  // (not more than leaves each of the others 1)
  state.set([...alternatives, 1, "edgeProperties", "percent"], 100);
  expect(percents(state)).toEqual([1, 98, 1]);
  state.remove([...alternatives, 1]);
  expect(percents(state)).toEqual([50, 50]);
  // (the edge properties set as a whole: the same)
  state.set([...alternatives, 1, "edgeProperties"], { percent: 30 });
  expect(percents(state)).toEqual([70, 30]);
});

test("an entity chosen for an alternative keeps its share, and a number being typed waits", () => {
  const state = createItemFormState(
    { type: "Alternative", alternatives: [{ type: "Person", edgeProperties: { percent: 70 } }, { type: "Person", edgeProperties: { percent: 30 } }] },
    { binder: createFormHooks(shared) },
  );
  state.set([...alternatives, 0], person("a"));
  expect(percents(state)).toEqual([70, 30]);
  expect(state.get([...alternatives, 0, "id"])).toBe("a");
  state.set([...alternatives, 1, "edgeProperties", "percent"], "");
  expect(percents(state)).toEqual([70, ""]);
});

test("an alternative there from the start, with no share, is given one when its entity is chosen", () => {
  const state = createItemFormState({ type: "Alternative", alternatives: [{ type: "Person" }] }, { binder: createFormHooks(shared) });
  state.set([...alternatives, 0], person("a"));
  expect(percents(state)).toEqual([100]);
  state.set([...alternatives, 1], { type: "Person" });
  state.set([...alternatives, 1], person("b"));
  expect(percents(state)).toEqual([50, 50]);
});

test("the shares are kept where the conjunction is deep in the item", () => {
  const state = createItemFormState(
    { type: "Identification", target: [{ type: "Alternative", alternatives: [] }] },
    { binder: createFormHooks(shared) },
  );
  const deep = ["target", 0, "alternatives"];
  state.set([...deep, 0], { type: "Person" });
  state.set([...deep, 1], { type: "Person" });
  state.set([...deep, 1, "edgeProperties", "percent"], 25);
  expect((state.get(deep) as FormData[]).map((each) => (each.edgeProperties as FormData).percent)).toEqual([75, 25]);
});
