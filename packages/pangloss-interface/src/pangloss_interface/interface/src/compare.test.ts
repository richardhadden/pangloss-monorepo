import type { FieldDefinition, ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import { describe, expect, it } from "vitest";
import {
  asNew,
  chosenValues,
  classChoices,
  daysSince,
  identity,
  isEmpty,
  mergeableTypes,
  notKept,
  referringKinds,
  rows,
  same,
  startingChoice,
  startingChoices,
  union,
  valueOf,
  without,
} from "./compare";

const base = { description: null, dbField: false, readOnly: false, required: false, nullable: true };
const literal = (name: string, key = name): FieldDefinition =>
  ({ ...base, name, key, kind: "literal", type: { type: "str" }, validators: [] }) as FieldDefinition;
const list = (name: string, key = name): FieldDefinition =>
  ({ ...base, name, key, kind: "list", item: { type: "str" }, validators: [], itemValidators: [] }) as FieldDefinition;
const relation = (name: string, key: string, type: string, many = true): FieldDefinition =>
  ({
    ...base,
    name,
    key,
    kind: "relation",
    many,
    reverseName: "is_in",
    options: [{ kind: "entity", type, edgeModel: null }],
    validators: [],
    subclasses: [],
  }) as FieldDefinition;
const model = (
  name: string,
  kind: ModelDefinition["kind"],
  fields: FieldDefinition[],
  parent: string | null = null,
  concreteTypes: string[] = [name],
): ModelDefinition =>
  ({ name, kind, abstract: false, parent, concreteTypes, fields, incoming: [], interfaceMeta: null }) as unknown as ModelDefinition;

const PERSON_FIELDS = [
  literal("born"),
  list("aliases"),
  relation("member_of", "memberOf", "Group"),
  relation("spouse", "spouse", "Person", false),
  { ...base, name: "when", key: "when", kind: "embedded", model: "Date", types: ["Date"] } as FieldDefinition,
  { ...literal("synced"), readOnly: true } as FieldDefinition,
];
const DEFINITIONS = {
  models: {
    Agent: model("Agent", "Entity", [], null, ["Person", "Poet", "Group"]),
    Person: model("Person", "Entity", PERSON_FIELDS, "Agent", ["Person", "Poet"]),
    Poet: model("Poet", "Entity", [...PERSON_FIELDS, list("works")], "Person"),
    Group: model("Group", "Entity", [], "Agent"),
    Date: model("Date", "Embedded", [literal("year")]),
    Factoid: model("Factoid", "Document", []),
  },
} as unknown as ModelDefinitions;
const PERSON = DEFINITIONS.models.Person!;
const group = (id: string, label = id) => ({ type: "Group", id, label });

const A = {
  id: "a",
  type: "Person",
  label: "John Smith",
  born: "1800",
  aliases: ["J. Smith"],
  memberOf: [group("g1"), group("g2")],
  spouse: { type: "Person", id: "b", label: "Jon Smyth" },
  when: null,
};
const B = {
  id: "b",
  type: "Person",
  label: "Jon Smyth",
  born: "1801",
  aliases: ["J. Smith", "Smyth"],
  memberOf: [group("g2", "another label"), group("g3")],
  spouse: null,
  when: { type: "Date", id: "node-of-b", year: "1850" },
};

const byKey = (key: string) => rows(PERSON, A, B, DEFINITIONS).find((row) => row.field.key === key)!;

describe("what is the same value", () => {
  it("takes nothing for nothing, however it is written", () => {
    expect([undefined, null, "", []].every(isEmpty)).toBe(true);
    expect(isEmpty(0) || isEmpty(false) || isEmpty("x") || isEmpty([null])).toBe(false);
    expect(same(null, [], DEFINITIONS)).toBe(true);
    expect(same(null, "x", DEFINITIONS)).toBe(false);
  });

  it("knows a reference to an entity by its id, whatever label it was read with", () => {
    expect(same(group("g2"), group("g2", "another label"), DEFINITIONS)).toBe(true);
    expect(same(group("g2"), group("g3"), DEFINITIONS)).toBe(false);
  });

  it("takes the properties of the edge to an entity as part of the reference", () => {
    const one = { ...group("g1"), edgeProperties: { level: 1 } };
    const other = { ...group("g1"), edgeProperties: { level: 2 } };
    expect(same(one, other, DEFINITIONS)).toBe(false);
  });

  it("knows a node that is not an entity by what it holds, not by its id", () => {
    const one = { type: "Date", id: "one", year: "1850" };
    const other = { year: "1850", type: "Date", id: "other", meta: { version: 3 } };
    expect(same(one, other, DEFINITIONS)).toBe(true);
    expect(identity(one, DEFINITIONS)).toBe(identity(other, DEFINITIONS));
    expect(same(one, { ...other, year: "1851" }, DEFINITIONS)).toBe(false);
  });
});

describe("the two lists as one", () => {
  it("keeps the first, then what only the second has, each once", () => {
    expect(union(["x", "y"], ["y", "z", "z"], DEFINITIONS)).toEqual(["x", "y", "z"]);
    expect(union(A.memberOf, B.memberOf, DEFINITIONS).map((each) => (each as { id: string }).id)).toEqual(["g1", "g2", "g3"]);
  });

  it("takes what is not a list for an empty one", () => {
    expect(union(null, ["x"], DEFINITIONS)).toEqual(["x"]);
    expect(union(["x"], undefined, DEFINITIONS)).toEqual(["x"]);
  });
});

describe("the rows of the comparison", () => {
  it("has a row for each field either entity has something in, in the order of the model", () => {
    expect(rows(PERSON, A, B, DEFINITIONS).map((row) => row.field.key)).toEqual(["born", "aliases", "memberOf", "when"]);
  });

  it("leaves out a field that something other than a person keeps up to date", () => {
    const found = rows(PERSON, { ...A, synced: "x" }, { ...B, synced: "y" }, DEFINITIONS);
    expect(found.some((row) => row.field.key === "synced")).toBe(false);
  });

  it("leaves the two entities themselves out of each other's fields, so that the survivor never refers to itself", () => {
    // (A's spouse is B: after the merge that would be A married to A)
    expect(rows(PERSON, A, B, DEFINITIONS).some((row) => row.field.key === "spouse")).toBe(false);
    expect(without([group("g1"), { type: "Person", id: "a" }], ["a", "b"])).toEqual([group("g1")]);
    expect(without({ type: "Person", id: "c" }, ["a", "b"])).toEqual({ type: "Person", id: "c" });
  });

  it("offers both only where the field holds several", () => {
    expect(byKey("born").options).toEqual(["a", "b"]);
    expect(byKey("aliases").options).toEqual(["a", "b", "both"]);
    expect(byKey("memberOf").options).toEqual(["a", "b", "both"]);
  });

  it("gives the survivor a node of the absorbed entity as a new one, and its references as they are", () => {
    expect(byKey("when").b).toEqual({ type: "Date", year: "1850" });
    expect(byKey("memberOf").b).toEqual(B.memberOf);
    expect(asNew({ type: "Date", id: "x", inner: [{ type: "Date", id: "y", year: "1" }] }, DEFINITIONS)).toEqual({
      type: "Date",
      inner: [{ type: "Date", year: "1" }],
    });
  });
});

describe("what a row starts with", () => {
  const suggested = {
    label: "John Smith",
    born: "1800",
    aliases: ["J. Smith", "Smyth"],
    memberOf: [{ type: "Group", id: "g1" }, { type: "Group", id: "g2" }, { type: "Group", id: "g3" }],
    when: { type: "Date", year: "1850" },
  };

  it("is the choice that gives what the API suggests", () => {
    expect(startingChoices(rows(PERSON, A, B, DEFINITIONS), suggested, DEFINITIONS)).toEqual({
      born: "a",
      aliases: "both",
      memberOf: "both",
      when: "b",
    });
  });

  it("is what was suggested itself where that is none of them: the absorbed label put among the aliases", () => {
    const withLabel = { ...suggested, aliases: ["J. Smith", "Smyth", "Jon Smyth"] };
    expect(startingChoice(byKey("aliases"), withLabel, DEFINITIONS)).toBe("suggested");
    expect(valueOf(byKey("aliases"), "suggested", withLabel, DEFINITIONS)).toEqual(["J. Smith", "Smyth", "Jon Smyth"]);
  });

  it("follows what a proposal chose, where it is one of the choices", () => {
    const proposed = { ...suggested, born: "1801", aliases: ["J. Smith"] };
    const choices = startingChoices(rows(PERSON, A, B, DEFINITIONS), proposed, DEFINITIONS);
    expect(choices.born).toBe("b");
    expect(choices.aliases).toBe("a");
  });

  it("is both of a list, and the survivor's value or else the other's, when nothing is suggested", () => {
    expect(startingChoices(rows(PERSON, A, B, DEFINITIONS), null, DEFINITIONS)).toEqual({
      born: "a",
      aliases: "both",
      memberOf: "both",
      when: "b",
    });
  });
});

describe("the fields that are sent", () => {
  const suggested = { label: "John Smith", urls: ["http://a", "http://b"], born: "1800", aliases: ["J. Smith", "Smyth"] };
  const all = rows(PERSON, A, B, DEFINITIONS);

  it("are what was suggested with each row's choice over it, and the label and the class", () => {
    const values = chosenValues(all, { born: "b", aliases: "a", memberOf: "b", when: "a" }, suggested, "J. S.", "Poet", DEFINITIONS);
    expect(values).toMatchObject({
      type: "Poet",
      label: "J. S.",
      // (what no row shows stays as suggested: the URLs of both)
      urls: ["http://a", "http://b"],
      born: "1801",
      aliases: ["J. Smith"],
      when: null,
    });
    expect((values.memberOf as { id: string }[]).map((each) => each.id)).toEqual(["g2", "g3"]);
  });

  it("gives a list field a list, and a single one null, when the side chosen has nothing", () => {
    const emptyA = { ...A, aliases: undefined, born: undefined };
    const found = rows(PERSON, emptyA, B, DEFINITIONS);
    const values = chosenValues(found, { born: "a", aliases: "a" }, suggested, "x", "Person", DEFINITIONS);
    expect(values.aliases).toEqual([]);
    expect(values.born).toBeNull();
  });

  it("uses each row's starting choice where none was made", () => {
    const values = chosenValues(all, {}, suggested, "John Smith", "Person", DEFINITIONS);
    expect(values.born).toBe("1800");
    expect(values.aliases).toEqual(["J. Smith", "Smyth"]);
  });
});

describe("the class of the survivor", () => {
  it("offers the one suggested first, then each entity's own, each once", () => {
    expect(classChoices(DEFINITIONS, "Person", "Poet", "Poet")).toEqual(["Poet", "Person"]);
    expect(classChoices(DEFINITIONS, "Person", "Person", "Person")).toEqual(["Person"]);
    expect(classChoices(DEFINITIONS, "Person", "Poet", "Gone")).toEqual(["Person", "Poet"]);
  });

  it("says which fields with something in them the class chosen does not have", () => {
    const poet = { id: "b", type: "Poet", works: ["Odes"], aliases: ["x"] };
    expect(notKept(DEFINITIONS, "Person", [A, poet]).map((each) => `${each.model}.${each.field.key}`)).toEqual(["Poet.works"]);
    expect(notKept(DEFINITIONS, "Poet", [A, poet])).toEqual([]);
    expect(notKept(DEFINITIONS, "Person", [A, { ...poet, works: [] }])).toEqual([]);
  });

  it("searches the whole family of an entity for the one to merge it with", () => {
    expect(mergeableTypes(DEFINITIONS, "Poet")).toEqual(["Person", "Poet", "Group"]);
    expect(mergeableTypes(DEFINITIONS, "Unknown")).toEqual(["Unknown"]);
  });
});

describe("the numbers on the page", () => {
  it("lists what refers to an entity by kind, the most first, ten at most", () => {
    expect(referringKinds({ Group: 1, Factoid: 12, Empty: 0, Letter: 12 })).toEqual([
      ["Factoid", 12],
      ["Letter", 12],
      ["Group", 1],
    ]);
    const many = Object.fromEntries(Array.from({ length: 14 }, (_, index) => [`T${index}`, index + 1]));
    expect(referringKinds(many)).toHaveLength(10);
    expect(referringKinds(undefined)).toEqual([]);
  });

  it("says how old a merge is in whole days", () => {
    const now = Date.parse("2026-11-12T12:00:00Z");
    expect(daysSince("2026-11-12T09:00:00Z", now)).toBe(0);
    expect(daysSince("2026-11-01T11:00:00Z", now)).toBe(11);
    expect(daysSince(null, now)).toBe(0);
    expect(daysSince("not a time", now)).toBe(0);
    // (a clock that is behind the server's is not a negative age)
    expect(daysSince("2026-11-13T12:00:00Z", now)).toBe(0);
  });
});
