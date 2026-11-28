import { describe, expect, test } from "vitest";
import type { ModelDefinitions } from "../types";
import { accordingTo, accordingToField } from "./spaces";

// Whose claim what a head holds is: the entities in the field its ground's `by` names (`Ground(by="source")`)

const typeVar = { kind: "typeVar", name: "T", edgeModel: null };

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
        { name: "target", key: "target", kind: "relation", options: [typeVar] },
        { name: "at", key: "at", kind: "relation", options: [{ kind: "entity", type: "Chronicle" }] },
      ],
    },
    // (a guess no person has confirmed, and one below it; a stand-in, a document and a wrapper)
    Suggestion: {
      name: "Suggestion",
      kind: "ReifiedRelation",
      unconfirmed: true,
      fields: [{ name: "target", key: "target", kind: "relation", options: [typeVar] }],
    },
    ToolchainSuggestion: { name: "ToolchainSuggestion", kind: "ReifiedRelation", parent: "Suggestion", fields: [{ name: "target", key: "target", kind: "relation", options: [typeVar] }] },
    Mention: { name: "Mention", kind: "Document", standIn: true, fields: [] },
    MatchesCriteria: {
      name: "MatchesCriteria",
      kind: "ReifiedRelation",
      standIn: true,
      fields: [{ name: "target", key: "target", kind: "relation", options: [typeVar] }],
    },
    // (a conjunction of two slots: each is a relation the server follows)
    Together: {
      name: "Together",
      kind: "Conjunction",
      fields: [
        { name: "first", key: "first", kind: "relation", options: [typeVar] },
        { name: "second", key: "second", kind: "relation", options: [typeVar] },
        { name: "where", key: "where", kind: "relation", options: [{ kind: "entity", type: "Chronicle" }] },
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

  test("never through a guess no person has confirmed (or one below it), nor a stand-in, as the server reads it", () => {
    const item = (sworn: unknown[]) => ({ type: "Hearing", id: "h", sworn });
    expect(accordingTo(definitions, item([{ type: "Suggestion", target: [chronicle("c1")] }]))).toEqual([]);
    expect(accordingTo(definitions, item([{ type: "ToolchainSuggestion", target: [chronicle("c1")] }]))).toEqual([]);
    expect(accordingTo(definitions, item([{ type: "MatchesCriteria", target: [chronicle("c1")] }]))).toEqual([]);
    expect(accordingTo(definitions, item([{ type: "Mention", id: "m", label: "someone" }, chronicle("c2")]))).toEqual([
      chronicle("c2"),
    ]);
  });

  test("a conjunction of several relations: each slot, as the server follows them, and not its other relations", () => {
    const item = {
      type: "Hearing",
      id: "h",
      sworn: [{ type: "Together", first: [chronicle("c1")], second: [chronicle("c2")], where: [chronicle("place")] }],
    };
    expect(accordingTo(definitions, item).map((entity) => entity.id)).toEqual(["c1", "c2"]);
  });
});

describe("accordingToField", () => {
  test("the field whose every value is an entity said: its row is not drawn again", () => {
    expect(accordingToField(definitions, { type: "Account", id: "a", source: chronicle("c1") })).toBe("source");
    expect(accordingToField(definitions, { type: "Letters", id: "l", writtenBy: [chronicle("c1"), chronicle("c2")] })).toBe(
      "writtenBy",
    );
  });

  test("none where the field is empty, says more than its entities (a wrapper), or is no claim's", () => {
    expect(accordingToField(definitions, { type: "Account", id: "a", source: null })).toBeNull();
    expect(accordingToField(definitions, { type: "Letters", id: "l", writtenBy: [] })).toBeNull();
    const wrapped = { type: "Hearing", id: "h", sworn: [{ type: "InRole", target: [chronicle("c1")], at: [chronicle("p")] }] };
    expect(accordingToField(definitions, wrapped)).toBeNull();
    expect(accordingToField(definitions, { type: "Hearing", id: "h", sworn: [{ type: "Suggestion", target: [chronicle("c1")] }] })).toBeNull();
    expect(accordingToField(definitions, { type: "Person", id: "p", source: chronicle("c1") })).toBeNull();
  });
});
