import { createRoot, flush } from "solid-js";
import { expect, test } from "vitest";
import type { FieldProblem, FormData } from "../schema";
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
  const state = createItemFormState({ type: "Factoid", statements: [] }, undefined, fill);
  state.set(["statements", 0], { type: "Activity" });
  expect(state.get(["statements", 0, "date"])).toEqual(DAY);
  // (a date taken away stays away; one changed is not filled)
  state.remove(["statements", 0, "date"]);
  state.set(["statements", 0, "involves"], []);
  expect(state.get(["statements", 0, "date"])).toBeUndefined();
  state.set(["statements", 0, "date"], { type: "Period" });
  expect(state.get(["statements", 0, "date"])).toEqual({ type: "Period" });
});
