import { describe, expect, test } from "vitest";
import type { ModelDefinitions } from "../types";
import { accordingTo } from "./spaces";

// Whose claim what a head holds is: the entities in the field its ground's `by` names (`Ground(by="source")`)

const claim = (by: { name: string; key: string } | null) => ({
  veridical: 1,
  fit: "describes",
  degree: null,
  by,
  standing: "claim",
});

const definitions = {
  models: {
    Account: { name: "Account", kind: "Document", fields: [], ground: claim({ name: "source", key: "source" }) },
    Letters: { name: "Letters", kind: "Document", fields: [], ground: claim({ name: "written_by", key: "writtenBy" }) },
    Hearing: { name: "Hearing", kind: "Document", fields: [], ground: claim({ name: "sworn", key: "sworn" }) },
    Note: { name: "Note", kind: "Document", fields: [], ground: claim(null) },
    // (a record: an entity, and a project's document of the record; neither may name anyone)
    Person: { name: "Person", kind: "Entity", fields: [], ground: { ...claim(null), standing: "record" } },
    Chronicle: { name: "Chronicle", kind: "Entity", fields: [] },
    Claim: { name: "Claim", kind: "Document", fields: [] },
    InRole: {
      name: "InRole",
      kind: "ReifiedRelation",
      fields: [
        { name: "target", key: "target", kind: "relation" },
        { name: "at", key: "at", kind: "relation" },
      ],
    },
  },
  enums: {},
} as unknown as ModelDefinitions;

const chronicle = (id: string, label: string | null = id) => ({ type: "Chronicle", id, label });

describe("accordingTo", () => {
  test("the entity in the field the ground names", () => {
    expect(accordingTo(definitions, { type: "Account", id: "a", source: chronicle("c1", "The annals") })).toEqual([
      { type: "Chronicle", id: "c1", label: "The annals" },
    ]);
  });

  test("each of several, once, in order; a field left empty names none", () => {
    const item = { type: "Letters", id: "l", writtenBy: [chronicle("c2"), chronicle("c1"), chronicle("c2")] };
    expect(accordingTo(definitions, item).map((entity) => entity.id)).toEqual(["c2", "c1"]);
    expect(accordingTo(definitions, { type: "Account", id: "a", source: null })).toEqual([]);
    expect(accordingTo(definitions, { type: "Letters", id: "l", writtenBy: [] })).toEqual([]);
  });

  test("behind a reified relation, by its target only; a document there is passed over", () => {
    const item = {
      type: "Hearing",
      id: "h",
      sworn: [
        { type: "InRole", target: [chronicle("c1")], at: [chronicle("place")] },
        { type: "Claim", id: "x", label: "a claim" },
      ],
    };
    expect(accordingTo(definitions, item).map((entity) => entity.id)).toEqual(["c1"]);
  });

  test("none for a record, a ground that names no one, or a class the models do not know", () => {
    expect(accordingTo(definitions, { type: "Person", id: "p", source: chronicle("c1") })).toEqual([]);
    expect(accordingTo(definitions, { type: "Note", id: "n", source: chronicle("c1") })).toEqual([]);
    expect(accordingTo(definitions, { type: "Claim", id: "x", source: chronicle("c1") })).toEqual([]);
    expect(accordingTo(definitions, { type: "Gone", id: "g", source: chronicle("c1") })).toEqual([]);
  });
});
