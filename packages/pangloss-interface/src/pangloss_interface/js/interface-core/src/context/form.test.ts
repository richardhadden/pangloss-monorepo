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
