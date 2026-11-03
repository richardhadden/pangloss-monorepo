import { createRoot, flush } from "solid-js";
import { expect, test } from "vitest";
import { createBinder } from "../schema";
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
