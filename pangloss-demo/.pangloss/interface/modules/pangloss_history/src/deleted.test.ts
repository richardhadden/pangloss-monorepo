import { expect, test } from "vitest";
import { deletedEntities } from "./deleted";

test("the entities deleted since are found at any depth, each once, in order", () => {
  const marie = { type: "Person", id: "p1", label: "Marie", deleted: true };
  const content = {
    type: "Statement",
    id: "s1",
    label: "S",
    about: marie,
    places: [{ type: "Place", id: "g1", label: "Ghent" }],
    parts: [{ type: "Part", id: "a", witnesses: [marie, { type: "Person", id: "p2", label: "Jan", deleted: true }] }],
  };
  expect(deletedEntities(content)).toEqual([
    { type: "Person", id: "p1", label: "Marie" },
    { type: "Person", id: "p2", label: "Jan" },
  ]);
});

test("one that is missing altogether, or there, is not among them; nor is anything with no content", () => {
  expect(
    deletedEntities({ type: "S", id: "s", about: { type: "Person", id: "p", label: null, missing: true }, by: { type: "Person", id: "q", label: "Q" } }),
  ).toEqual([]);
  expect(deletedEntities(undefined)).toEqual([]);
});
