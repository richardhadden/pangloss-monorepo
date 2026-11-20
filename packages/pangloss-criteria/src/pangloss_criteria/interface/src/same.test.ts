import { afterEach, expect, test, vi } from "vitest";
import { holderOf, isBare, newMark, placesIn, placesOf, sameOneChoices } from "./same";
import { CHARLES, definitions } from "./testing";

afterEach(() => vi.unstubAllGlobals());

const MARK = "00000000-0000-0000-0000-00000000000f";
const criteria = { type: "Person", where: { born: { eq: 1500 } } };
const name = (model: string, field: string) => `${model}.${field}`;

const sighting = {
  type: "Sighting",
  meta: { id: "x" },
  seen: [
    { type: "Person", id: CHARLES, label: "Charles" },
    { type: "MatchesCriteria", criteria, sameOne: MARK, target: [{ type: "Person", id: CHARLES }] },
  ],
  company: [{ type: "MatchesCriteria", criteria: null, sameOne: MARK }, { type: "MatchesCriteria", criteria }],
};

test("the descriptions of a document are found where they are, with the name of their field, in its order", () => {
  const places = placesIn(definitions, sighting, "MatchesCriteria", name);
  expect(places.map((place) => [place.path, place.field, place.mark])).toEqual([
    [["seen", 1], "Sighting.seen", MARK],
    [["company", 0], "Sighting.company", MARK],
    [["company", 1], "Sighting.company", null],
  ]);
  expect(placesOf(places, MARK)).toHaveLength(2);
  expect(holderOf(places, MARK)?.path).toEqual(["seen", 1]);
  expect(isBare(places[1]!.value)).toBe(true);
  expect(isBare(places[0]!.value)).toBe(false);
  // (what the place at `company.1` may be the same one as: the holder of the mark, once)
  expect(sameOneChoices(places, ["Person"], ["company", 1]).map((place) => place.path)).toEqual([["seen", 1]]);
  expect(sameOneChoices(places, ["Group"], ["company", 1])).toEqual([]);
});

test("a new mark is a UUID, also where the browser has no randomUUID (not a secure context)", () => {
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  expect(newMark()).toMatch(uuid);
  const real = globalThis.crypto;
  vi.stubGlobal("crypto", { getRandomValues: (bytes: Uint8Array) => real.getRandomValues(bytes) });
  const made = new Set(Array.from({ length: 20 }, () => newMark()));
  expect(made.size).toBe(20);
  for (const mark of made) expect(mark).toMatch(uuid);
});
