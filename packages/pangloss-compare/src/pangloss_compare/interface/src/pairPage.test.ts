import { describe, expect, test } from "vitest";
import type { ModelDefinitions } from "@pangloss/interface-core";
import type { PairEntry, StatementChip } from "./api";
import { fittingVerdicts, judgedFields, judgementClasses, pairWith, placeProblems, shownPairs, targetsOf, VERDICTS_OF } from "./compared";
import { pairRows } from "./components/PairPage";

// The pure parts of the page of two side by side (`/compare/:type/:a/:b`): which verdicts fit, which class records a
// judgement, the targets met or missed, the rows

const chip = (
  prescribes = false,
  prescription: StatementChip["prescription"] = null,
  says: StatementChip["says"] = prescribes ? "for" : "asserts",
) => ({ prescribes, prescription, says });

describe("the verdicts that fit a pair, by what the two statements say (not by what the maths made of them)", () => {
  test("two that describe: agree, disagree, two events; a denial too, whatever the maths said of the pair", () => {
    expect(fittingVerdicts(chip(), chip(), "Baptism")).toEqual({ verdicts: ["agree", "disagree", "two_events"] });
    expect(fittingVerdicts(chip(), chip(false, null, "denies"), "Baptism")).toEqual({ verdicts: VERDICTS_OF.describe });
    // (a pair the comparison has not found, of one class)
    expect(fittingVerdicts(chip(), chip(), "Journey")).toEqual({ verdicts: VERDICTS_OF.describe });
  });

  test("an order and what came of it, whichever is first (done by another, or before: still judged); a prohibition; a permission", () => {
    const order = { verdicts: ["carried_out", "carried_out_otherwise", "not_carried_out", "done_not_carried_out", "two_events"] };
    expect(fittingVerdicts(chip(true, "order"), chip(), "Journey")).toEqual(order);
    expect(fittingVerdicts(chip(), chip(true, "order"), "Journey")).toEqual(order);
    expect(fittingVerdicts(chip(true, "order"), chip(false, null, "denies"), "Journey")).toEqual(order);
    expect(fittingVerdicts(chip(true, "prohibition", "against"), chip(), "Journey")).toEqual({ verdicts: ["breach", "complied", "two_events"] });
    expect(fittingVerdicts(chip(true, "permission"), chip(false, null, "denies"), "Journey")).toEqual({ verdicts: ["permission_used", "two_events"] });
  });

  test("none, with why: two prescriptions; one that says nothing either way; a prescription of no kind; classes not related", () => {
    expect(fittingVerdicts(chip(true, "order"), chip(true, "prohibition"), "Journey")).toEqual({ why: "two_prescriptions" });
    expect(fittingVerdicts(chip(), chip(false, null, "neither"), "Journey")).toEqual({ why: "says_nothing" });
    expect(fittingVerdicts(chip(true, null, "neither"), chip(), "Journey")).toEqual({ why: "says_nothing" });
    expect(fittingVerdicts(chip(true, null, "for"), chip(), "Journey")).toEqual({ why: "says_nothing" });
    expect(fittingVerdicts(chip(), chip(), null)).toEqual({ why: "unrelated" });
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
    // (cites a baptism first and a journey second only)
    MixedJudgement: judgement("MixedJudgement", ["Baptism"], ["Journey"]),
    // (not the package's: citing alike, but no judgement)
    Inference: judgement("Inference", ["Occurrence"], ["Occurrence"], {}),
  },
  enums: {},
} as unknown as ModelDefinitions;

describe("the class a judgement is recorded with", () => {
  test("those whose `statement` and `other` cite the two (a class or one above it), by name; the package's only", () => {
    const names = (found: { name: string; swapped: boolean }[]) => found.map((each) => `${each.name}${each.swapped ? " swapped" : ""}`);
    expect(names(judgementClasses(DEFINITIONS, "Baptism", "Baptism"))).toEqual(["AJudgement", "ZJudgement"]);
    expect(names(judgementClasses(DEFINITIONS, "Journey", "Baptism"))).toEqual(["ZJudgement"]);
    expect(names(judgementClasses(DEFINITIONS, "Town", "Baptism"))).toEqual([]);
    // (two that describe may be cited the other way round; a prescription always goes in `statement`)
    expect(names(judgementClasses(DEFINITIONS, "Journey", "Baptism", true))).toEqual(["ZJudgement", "MixedJudgement swapped"]);
    expect(names(judgementClasses(DEFINITIONS, "Journey", "Baptism", false))).toEqual(["ZJudgement"]);
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

  const carried = (changes: Partial<PairEntry> = {}) =>
    ({ relation: "carried_out_otherwise", fields: ["town"], how: { town: "different" }, judged: null, workedOut: { relation: "carried_out_otherwise", fields: ["town"], how: { town: "different" }, reported: false }, ...changes }) as PairEntry;

  test("each target met where the rows are the same, missed as the entry says; what only one fills is no target", () => {
    const { shared } = pairRows(
      DEFINITIONS,
      "Baptism",
      { type: "Baptism", baptised: anna, town: ghent },
      { type: "Baptism", baptised: anna, town: bruges },
    );
    expect(targetsOf(shared, carried()).map((target) => [target.key, target.how])).toEqual([
      ["baptised", "met"],
      ["town", "different"],
    ]);
    // (one only one fills: not met)
    const { shared: half } = pairRows(DEFINITIONS, "Baptism", { type: "Baptism", baptised: anna, town: ghent }, { type: "Baptism", baptised: anna });  // prettier-ignore
    expect(targetsOf(half, carried({ relation: "carried_out", fields: [], how: {} })).map((target) => [target.key, target.how])).toEqual([["baptised", "met"]]);  // prettier-ignore
  });

  test("never met by default: a field whose rows differ is no target the entry does not name", () => {
    const { shared } = pairRows(DEFINITIONS, "Baptism", { type: "Baptism", town: ghent }, { type: "Baptism", town: bruges });  // prettier-ignore
    expect(targetsOf(shared, carried({ relation: "carried_out", fields: [], how: {} }))).toEqual([]);
  });

  test("a person's judgement: the fields it names are missed, by the maths' word only where the maths says it too", () => {
    const { shared } = pairRows(
      DEFINITIONS,
      "Baptism",
      { type: "Baptism", baptised: anna, town: ghent },
      { type: "Baptism", baptised: anna, town: bruges },
    );
    const judged = carried({ judged: "carried_out_otherwise", fields: ["town", "baptised"], how: {} });
    expect(targetsOf(shared, judged).map((target) => [target.key, target.how])).toEqual([
      ["baptised", "missed"],
      ["town", "different"],
    ]);
  });

  test("none where the pair is not said to be carried out: judged two events, or the maths' two or nothing", () => {
    const { shared } = pairRows(DEFINITIONS, "Baptism", { type: "Baptism", baptised: anna }, { type: "Baptism", baptised: anna });  // prettier-ignore
    expect(targetsOf(shared, carried({ relation: "two", judged: "two_events" }))).toEqual([]);
    expect(targetsOf(shared, carried({ relation: "nothing" }))).toEqual([]);
  });
});

describe("a refusal of the API", () => {
  test("each problem at the part of the form it is about, and the rest for the toast", () => {
    expect(
      placeProblems([
        { path: ["fields"], message: "'x' is not a field" },
        { path: ["other"], message: "both cite one" },
        { path: [], message: "something else" },
        { path: ["label"], message: "too long" },
      ]),
    ).toEqual({
      placed: [
        { at: "fields", message: "'x' is not a field" },
        { at: "other", message: "both cite one" },
      ],
      unplaced: ["something else", "too long"],
    });
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
