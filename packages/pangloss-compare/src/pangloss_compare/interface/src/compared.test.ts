import { describe, expect, test } from "vitest";
import type { ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import type { PairEntry, Reason } from "./api";
import {
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
  source: null,
  prescribes: false,
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
