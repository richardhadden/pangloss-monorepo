import { describe, expect, test } from "vitest";
import type { ModelDefinitions } from "@pangloss/interface-core";
import type { PairEntry, StatementChip } from "./api";
import { fittingVerdicts, judgedFields, judgementClasses, pairWith, shownPairs, targetsOf, VERDICTS_OF } from "./compared";
import { pairRows } from "./components/PairPage";

// The pure parts of the page of two side by side (`/compare/:type/:a/:b`): which verdicts fit, which class records a
// judgement, the targets met or missed, the rows

const chip = (prescribes = false, prescription: StatementChip["prescription"] = null) => ({ prescribes, prescription });

describe("the verdicts that fit a pair", () => {
  test("two that describe: agree, disagree, two events", () => {
    expect(fittingVerdicts(chip(), chip(), "disagree")).toEqual({ verdicts: ["agree", "disagree", "two_events"] });
    // (a pair the comparison has not found is judged by what the two are)
    expect(fittingVerdicts(chip(), chip())).toEqual({ verdicts: VERDICTS_OF.describe });
  });

  test("an order and what came of it, whichever is first; a prohibition; a permission", () => {
    const order = { verdicts: ["carried_out", "carried_out_otherwise", "not_carried_out", "done_not_carried_out", "two_events"] };
    expect(fittingVerdicts(chip(true, "order"), chip(), "carried_out_otherwise")).toEqual(order);
    expect(fittingVerdicts(chip(), chip(true, "order"))).toEqual(order);
    expect(fittingVerdicts(chip(true, "prohibition"), chip(), "breach")).toEqual({ verdicts: ["breach", "complied", "two_events"] });
    expect(fittingVerdicts(chip(true, "permission"), chip(), "permission_used")).toEqual({ verdicts: ["permission_used", "two_events"] });
  });

  test("none of two prescriptions, of a pair that says nothing, nor of a prescription whose kind is not said", () => {
    expect(fittingVerdicts(chip(true, "order"), chip(true, "prohibition"), "conflict")).toEqual({ why: "two_prescriptions" });
    expect(fittingVerdicts(chip(), chip(), "nothing")).toEqual({ why: "says_nothing" });
    expect(fittingVerdicts(chip(true, null), chip())).toEqual({ why: "says_nothing" });
  });

  test("all ten verdicts are offered of some pair, and each kind offers two events", () => {
    const all = new Set(Object.values(VERDICTS_OF).flat());
    expect(all.size).toBe(10);
    for (const verdicts of Object.values(VERDICTS_OF)) expect(verdicts).toContain("two_events");
  });
});

const relation = (key: string, cites: string[] | null, type = "Occurrence") => ({
  name: key,
  key,
  kind: "relation",
  options: [{ kind: "document", type: "PGCitation", edgeModel: null, ...(cites ? { cites } : {}) }, { kind: "entity", type, edgeModel: null }],
});
const judgement = (name: string, statement: string[], other: string[], extras: object = { judgement: true }) => ({
  name,
  kind: "Document",
  abstract: false,
  extras,
  fields: [relation("statement", statement), relation("other", other)],
});

const DEFINITIONS = {
  models: {
    Occurrence: { name: "Occurrence", kind: "Document", abstract: true, concreteTypes: ["Baptism", "Journey"], fields: [] },
    Baptism: {
      name: "Baptism",
      kind: "Document",
      abstract: false,
      concreteTypes: ["Baptism"],
      fields: [
        { name: "baptised", key: "baptised", kind: "relation", dbField: false, readOnly: false, options: [] },
        { name: "town", key: "town", kind: "relation", dbField: false, readOnly: false, options: [] },
        { name: "sort_day", key: "sortDay", kind: "literal", dbField: true, readOnly: true, type: { type: "int" } },
        { name: "kept", key: "kept", kind: "literal", dbField: false, readOnly: true, type: { type: "str" } },
      ],
      incoming: [],
    },
    Journey: { name: "Journey", kind: "Document", abstract: false, concreteTypes: ["Journey"], fields: [] },
    Town: { name: "Town", kind: "Entity", abstract: false, concreteTypes: ["Town"], fields: [], incoming: [] },
    Person: { name: "Person", kind: "Entity", abstract: false, concreteTypes: ["Person"], fields: [], incoming: [] },
    ZJudgement: judgement("ZJudgement", ["Occurrence"], ["Occurrence"]),
    AJudgement: judgement("AJudgement", ["Baptism"], ["Baptism"]),
    JourneyJudgement: judgement("JourneyJudgement", ["Journey"], ["Journey"]),
    // (not the package's: citing alike, but no judgement)
    Inference: judgement("Inference", ["Occurrence"], ["Occurrence"], {}),
  },
  enums: {},
} as unknown as ModelDefinitions;

describe("the class a judgement is recorded with", () => {
  test("those whose `statement` and `other` cite the two (a class or one above it), by name; the package's only", () => {
    expect(judgementClasses(DEFINITIONS, "Baptism", "Baptism")).toEqual(["AJudgement", "ZJudgement"]);
    expect(judgementClasses(DEFINITIONS, "Journey", "Baptism")).toEqual(["ZJudgement"]);
    expect(judgementClasses(DEFINITIONS, "Town", "Baptism")).toEqual([]);
  });

  test("the fields a judgement may name: those a person writes", () => {
    expect(judgedFields(DEFINITIONS, "Baptism").map((field) => field.key)).toEqual(["baptised", "town"]);
    expect(judgedFields(DEFINITIONS, "Gone")).toEqual([]);
  });
});

const ghent = { id: "ghent", type: "Town", label: "Ghent" };
const bruges = { id: "bruges", type: "Town", label: "Bruges" };
const anna = { id: "anna", type: "Person", label: "Anna" };

describe("the rows and the targets", () => {
  test("the rows of the nearest class both are, the label left out (each column is headed by its chip)", () => {
    const { shared, apart } = pairRows(
      DEFINITIONS,
      "Baptism",
      { type: "Baptism", label: "One", baptised: anna, town: ghent },
      { type: "Baptism", label: "Two", baptised: anna, town: bruges },
    );
    expect(shared.map((row) => [row.key, row.cells.map((cell) => cell.mark).join(" ")])).toEqual([
      [".baptised[anna]", "same same"],
      [".town[@0]", "same changed"],
    ]);
    expect(apart).toEqual([]);
  });

  test("each target met, or missed and how; what only one says is no target unless missed", () => {
    const { shared } = pairRows(
      DEFINITIONS,
      "Baptism",
      { type: "Baptism", baptised: anna, town: ghent },
      { type: "Baptism", baptised: anna },
    );
    expect(targetsOf(shared, {}).map((target) => [target.key, target.how])).toEqual([["baptised", "met"]]);
    expect(targetsOf(shared, { town: "different" }).map((target) => [target.key, target.how])).toEqual([
      ["baptised", "met"],
      ["town", "different"],
    ]);
  });
});

describe("the pair of the page", () => {
  const entry = { other: { id: "b2" }, relation: "two", judged: "two_events" } as unknown as PairEntry;
  test("the entry for the other statement, or none", () => {
    const comparison = { pairs: [entry] } as never;
    expect(pairWith(comparison, "b2")).toBe(entry);
    expect(pairWith(comparison, "b3")).toBeUndefined();
    expect(pairWith(undefined, "b2")).toBeUndefined();
  });

  test("a pair judged two events is folded apart in the section", () => {
    expect(shownPairs([entry]).twoEvents).toEqual([entry]);
    expect(shownPairs([entry]).open).toEqual([]);
  });
});
