import { expect, test } from "vitest";
import { brokenField, brokenOf, citationOf, citedId, holdsCriteria, savedResult, withCriteria } from "./value";

test("whether a description is out of date, and since which migration", () => {
  expect(brokenOf({ broken: "office: gone", brokenSince: "demo_app.0024_remove_office" })).toEqual({
    reason: "office: gone",
    since: "demo_app.0024_remove_office",
  });
  expect(brokenOf({ broken: "office: gone", brokenSince: null })).toEqual({ reason: "office: gone", since: null });
  expect(brokenOf({ broken: "office: gone" })).toEqual({ reason: "office: gone", since: null });
  expect(brokenOf({ broken: null, brokenSince: "x" })).toBeNull();
  expect(brokenOf({})).toBeNull();
  expect(brokenOf(undefined)).toBeNull();
});

test("what the read gave keeps the migration a description is out of date since", () => {
  const saved = savedResult({ target: [], candidateCount: 0, evaluatedWhen: null, broken: "office: gone", brokenSince: "app.0002" });
  expect(saved?.broken).toBe("office: gone");
  expect(saved?.brokenSince).toBe("app.0002");
});

test("the field of the root whose condition failed, from the reason", () => {
  expect(brokenField("where.office: the field 'office' of HoldsOffice was removed")).toBe("office");
  expect(brokenField("office: HoldsOffice has no field 'office'")).toBe("office");
  expect(brokenField("where.born.eq: not a year")).toBe("born");
  // (a condition on the same field as another, or inside what a relation points at: the row of the root it is in)
  expect(brokenField("where.$all.0.born: not a year")).toBe("born");
  expect(brokenField("holder_of.office: gone")).toBe("holder_of");
  // (not a field)
  expect(brokenField("where.$incoming: gone")).toBeNull();
  expect(brokenField("$mentions: gone")).toBeNull();
  expect(brokenField("the criteria no longer fit")).toBeNull();
  expect(brokenField(": nothing")).toBeNull();
});

test("the citation of a shared description a mention holds, and whether it holds anything", () => {
  const citation = { type: "PGCitation", id: "c", targetId: "d", targetLabel: "The secretary", changedSinceCited: true };
  expect(citationOf({ description: citation })).toBe(citation);
  expect(citedId({ description: citation })).toBe("d");
  expect(citationOf({ description: null })).toBeNull();
  expect(citationOf({ description: { type: "PGCitation" } })).toBeNull();
  expect(holdsCriteria({ description: citation, criteria: null })).toBe(true);
  expect(holdsCriteria({ criteria: { type: "Person", where: {} } })).toBe(true);
  expect(holdsCriteria({ criteria: null, sameOne: "m" })).toBe(false);
});

test("a mention given another shared description loses what was worked out; the same one keeps its citation as read", () => {
  const model = { fields: [{ key: "target", computed: true }, { key: "candidateCount", computed: true }] } as never;
  const citation = { type: "PGCitation", id: "c", targetId: "d", targetLabel: "The secretary", changedSinceCited: true };
  const read = { type: "MatchesCriteria", id: "x", criteria: null, description: citation, target: [], candidateCount: 3 };
  // (the same one: the citation, its mark and what the server found stay)
  expect(withCriteria(read, model, "him", null, { id: "d", label: "The secretary" })).toEqual({ ...read, wording: "him" });
  // (another: a new citation, with no id, and no candidates)
  const other = withCriteria(read, model, "", null, { id: "e", label: "The chancellor" });
  expect(other).toMatchObject({ description: { type: "PGCitation", targetId: "e", targetLabel: "The chancellor", changedSinceCited: false } });
  expect((other.description as Record<string, unknown>).id).toBeUndefined();
  expect(other.target).toBeUndefined();
  // (none)
  expect(withCriteria(read, model, "", { type: "Person", where: {} }, null)).toMatchObject({ description: null, criteria: { type: "Person", where: {} } });
});
