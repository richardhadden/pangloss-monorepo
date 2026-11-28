import { describe, expect, test } from "vitest";
import type { ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import type { PairEntry, Reason } from "./api";
import {
  askedOthers,
  STANDS_AGAINST,
  standsAgainst,
  labelled,
  MOST_OTHERS,
  relationShown,
  statementMark,
  byClass,
  comparePath,
  fieldOf,
  fieldsSaid,
  figure,
  isCompared,
  mergeHref,
  nearGroups,
  pairHref,
  RELATION_WORDS,
  shownPairs,
  verdictRelation,
} from "./compared";

const statement = (id: string, type = "Baptism") => ({
  id,
  type,
  label: id,
  head: { id: `${id}-head`, type: "Account", label: null },
  sources: [],
  prescribes: false,
  prescription: null,
  says: "asserts" as const,
});

const pair = (id: string, changes: Partial<PairEntry> = {}): PairEntry => ({
  other: statement(id),
  relation: "agree",
  fields: [],
  how: {},
  reported: false,
  likelihood: 1,
  within: null,
  strength: 1,
  superseded: false,
  first: "b1",
  second: id,
  common: "Baptism",
  workedOut: { relation: "agree", fields: [], how: {}, reported: false },
  found: "rule",
  by: [],
  judged: null,
  judgements: [],
  ...changes,
});

const person = (id: string) => ({ id, type: "Person", label: id });
const near = (entity: string, other: string, score: number, type = "Person"): Reason => ({
  field: "baptised",
  kind: "near",
  entity: { ...person(entity), type },
  near: { ...person(other), type },
  score,
});

describe("which statements are compared", () => {
  test("a class the package says is compared, and no other", () => {
    expect(isCompared({ extras: { compared: true } } as unknown as ModelDefinition)).toBe(true);
    expect(isCompared({ extras: {} } as unknown as ModelDefinition)).toBe(false);
    expect(isCompared({} as unknown as ModelDefinition)).toBe(false);
    expect(isCompared(undefined)).toBe(false);
  });
});

describe("the addresses", () => {
  test("the route, the page of a pair, and the merge of two entities", () => {
    expect(comparePath("Journey", "j 1")).toBe("/compare/Journey/j%201");
    expect(pairHref("Baptism", "b1", "b2")).toBe("/compare/Baptism/b1/b2");
    expect(mergeHref({ type: "Person", id: "p1" }, { id: "p2" })).toBe("/Person/p1/merge/p2");
  });
});

describe("what is shown, and what folded", () => {
  test("in the route's order, two events and nothing left out, the superseded apart", () => {
    const pairs = [
      pair("a"),
      pair("b", { relation: "carried_out", reported: true, superseded: true }),
      pair("c", { relation: "disagree" }),
      pair("d", { relation: "two" }),
      pair("e", { relation: "nothing" }),
      pair("f", { relation: "carried_out", superseded: true }),
    ];
    const shown = shownPairs(pairs);
    expect(shown.open.map((p) => p.other.id)).toEqual(["a", "c"]);
    expect(shown.superseded.map((p) => p.other.id)).toEqual(["b", "f"]);
  });

  test("a pair a person judged two events is not shown either", () => {
    expect(shownPairs([pair("a", { relation: "two", judged: "two_events" })]).open).toEqual([]);
    expect(verdictRelation("two_events")).toBe("two");
    expect(verdictRelation("agree")).toBe("agree");
  });
});

describe("the pairs through near entities", () => {
  test("grouped by the two entities, each pair under its nearest reason, in the route's order", () => {
    const pairs = [
      pair("x", { found: "near", by: [near("anna", "anne", 0.9)] }),
      pair("y", { found: "near", by: [near("anna", "hanna", 0.7)] }),
      // (reached through two: under the nearer, which the route gives first)
      pair("z", { found: "near", by: [near("anna", "anne", 0.9), near("anna", "hanna", 0.7)] }),
      pair("w", { found: "near", relation: "two", by: [near("anna", "anne", 0.9)] }),
    ];
    const groups = nearGroups(pairs);
    expect(groups.map((g) => [g.entity.id, g.near.id, g.score, g.pairs.map((p) => p.other.id)])).toEqual([
      ["anna", "anne", 0.9, ["x", "z"]],
      ["anna", "hanna", 0.7, ["y"]],
    ]);
  });

  test("under a heading for each class of the entities", () => {
    const groups = nearGroups([
      pair("x", { by: [near("anna", "anne", 0.9)] }),
      pair("y", { by: [near("ghent", "gent", 0.8, "Town")] }),
      pair("z", { by: [near("piet", "pieter", 0.7)] }),
    ]);
    expect(byClass(groups).map((each) => [each.type, each.groups.map((g) => g.near.id)])).toEqual([
      ["Person", ["anne", "pieter"]],
      ["Town", ["gent"]],
    ]);
  });

  test("a pair with no reason through two entities is in no group", () => {
    expect(nearGroups([pair("x", { by: [{ field: "baptised", kind: "rule", entity: person("anna") }] })])).toEqual([]);
  });
});

describe("what a row says of the fields", () => {
  const definitions = {
    models: {
      Occurrence: { name: "Occurrence", fields: [{ name: "when", key: "when" }] },
      Baptism: {
        name: "Baptism",
        fields: [
          { name: "when", key: "when" },
          { name: "baptised", key: "baptised" },
          { name: "parish_town", key: "parishTown" },
        ],
      },
    },
    enums: {},
  } as unknown as ModelDefinitions;

  test("a field by its camelCase key, of the nearest class both are first, then of each's own", () => {
    expect(fieldOf(definitions, ["Occurrence", "Baptism"], "when")).toEqual({ model: "Occurrence", name: "when" });
    expect(fieldOf(definitions, [null, "Baptism"], "parishTown")).toEqual({ model: "Baptism", name: "parish_town" });
    expect(fieldOf(definitions, ["Gone", "Baptism"], "nothing")).toBeNull();
  });

  test("the fields disagreed on; the targets missed, and how; nothing for any other relation", () => {
    expect(fieldsSaid(pair("a", { relation: "disagree", fields: ["parishTown"], how: { parishTown: "different" } }))).toEqual([
      { field: "parishTown", how: null },
    ]);
    expect(
      fieldsSaid(pair("a", { relation: "carried_out_otherwise", fields: ["when", "destination"], how: { when: "late" } })),
    ).toEqual([
      { field: "when", how: "late" },
      { field: "destination", how: null },
    ]);
    expect(fieldsSaid(pair("a", { relation: "agree", fields: ["when"] }))).toEqual([]);
  });

  test("every relation has its words, and a figure has two decimals", () => {
    for (const [slot, words] of Object.values(RELATION_WORDS)) {
      expect(slot).toMatch(/^compare_/);
      expect(words.length).toBeGreaterThan(0);
    }
    expect(figure(0.876, "en")).toBe("0.88");
    expect(figure(1, "de")).toBe("1,00");
  });
});

// --- "Similar" labelled by relation (step 7.6) ---

describe("what stands against this statement", () => {
  test("the six relations of evidence set against evidence, both sides committed, a person's judgement deciding", () => {
    expect([...STANDS_AGAINST].sort()).toEqual(
      ["breach", "conflict", "contradiction", "disagree", "not_carried_out", "orders_at_odds"].sort(),
    );
    for (const relation of STANDS_AGAINST) {
      expect(RELATION_WORDS[relation]).toBeDefined();
      expect(standsAgainst(pair("b2", { relation }))).toBe(true);
    }
    // (leaning only, done otherwise or by another, agreeing, nothing: not)
    for (const relation of ["tension", "at_odds", "carried_out_otherwise", "done_not_carried_out", "agree", "support", "compatible", "carried_out", "complied", "permission_used", "two", "nothing"] as const) {
      expect(standsAgainst(pair("b2", { relation }))).toBe(false);
    }
    // (the judgement overrides the maths)
    const judged = pair("b2", { relation: "agree", judged: "agree", workedOut: { relation: "disagree", fields: [], how: {}, reported: false } });
    expect(standsAgainst(judged)).toBe(false);
  });

  test("not what is only reported (a statement that only leans, of what came of a prescription); a person's verdict is not", () => {
    expect(standsAgainst(pair("b2", { relation: "not_carried_out", reported: true }))).toBe(false);
    expect(standsAgainst(pair("b2", { relation: "breach", reported: true }))).toBe(false);
    // (judged: the override's `reported` is false)
    expect(standsAgainst(pair("b2", { relation: "breach", reported: false, judged: "breach" }))).toBe(true);
  });
});

describe("what a listed statement's label says", () => {
  test("its relation, but not where the maths alone says two events or nothing; a person's two events is named", () => {
    expect(relationShown(pair("b2"))).toBe(true);
    expect(relationShown(pair("b2", { relation: "two" }))).toBe(false);
    expect(relationShown(pair("b2", { relation: "nothing" }))).toBe(false);
    expect(relationShown(pair("b2", { relation: "two", judged: "two_events" }))).toBe(true);
  });

  test("the mark of what the statement itself says, as the interface names it; reported where only the pair says so", () => {
    const says = (value: "asserts" | "denies" | "for" | "against" | "neither", prescribes = false) => ({ says: value, prescribes });
    expect(statementMark(says("asserts"))).toBeUndefined();
    expect(statementMark(says("asserts"), true)).toBe("reported");
    expect(statementMark(says("denies"))).toBe("denied");
    expect(statementMark(says("for"))).toBe("reported");
    expect(statementMark(says("against"))).toBe("reported_not");
    expect(statementMark(says("for", true))).toBe("prescribed");
    expect(statementMark(says("against", true))).toBe("prescribed_not");
    expect(statementMark(says("neither"))).toBe("nothing");
  });
});

describe("what is asked of a list", () => {
  const models = {
    models: {
      Baptism: { name: "Baptism", extras: { compared: true } },
      Account: { name: "Account" },
      Person: { name: "Person" },
    },
    enums: {},
  } as unknown as ModelDefinitions;

  test("each statement of a compared class, not the page's own, once each, in the list's order, at most MOST_OTHERS", () => {
    const items = [
      { id: "p1", type: "Person" },
      { id: "b3", type: "Baptism" },
      { id: "a1", type: "Account" },
      { id: "b1", type: "Baptism" },
      { id: "b2", type: "Baptism" },
      { id: "b3", type: "Baptism" },
      { id: "x1", type: "Unknown" },
    ];
    expect(askedOthers(models, "b1", items)).toEqual(["b3", "b2"]);
    expect(askedOthers(models, "b1", [{ id: "p1", type: "Person" }])).toEqual([]);
    const many = Array.from({ length: MOST_OTHERS + 5 }, (_, n) => ({ id: `b${n + 10}`, type: "Baptism" }));
    expect(askedOthers(models, "b1", many)).toHaveLength(MOST_OTHERS);
  });

  test("each filter keeps what it says, and what has no entry is kept by neither", () => {
    const denied = { ...statement("b3"), says: "denies" as const };
    const found = labelled({
      statement: statement("b1"),
      pairs: [pair("b2"), pair("b3", { other: denied, relation: "contradiction" }), pair("b4", { relation: "disagree", other: { ...statement("b4"), says: "for" } })],
      more: false,
      model: null,
      near: null,
    });
    expect([...found.entries.keys()]).toEqual(["b2", "b3", "b4"]);
    expect(["b2", "b3", "b4", "p1"].map(found.keeps.asserted)).toEqual([true, false, false, false]);
    expect(["b2", "b3", "b4", "p1"].map(found.keeps.against)).toEqual([false, true, true, false]);
  });
});
