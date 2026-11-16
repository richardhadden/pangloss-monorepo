import type { FieldDefinition, ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import { describe, expect, it } from "vitest";
import {
  byContext,
  claimDirect,
  claimHref,
  claimsHeld,
  contested,
  grouped,
  clusterClaimHref,
  disputes,
  further,
  hasCluster,
  identityFields,
  identityIncoming,
  stepsOf,
} from "./identity";
import type { Cluster } from "./identity";

const base = { description: null, dbField: false, readOnly: false, required: false, nullable: true };
const relation = (name: string, options: unknown[], markers?: unknown[]): FieldDefinition =>
  ({ ...base, name, key: name, kind: "relation", many: true, reverseName: `${name}_reverse`, options, validators: [], subclasses: [], markers }) as FieldDefinition;
const model = (name: string, kind: ModelDefinition["kind"], fields: FieldDefinition[], incoming: unknown[] = []): ModelDefinition =>
  ({ name, kind, abstract: false, parent: null, concreteTypes: [name], fields, incoming, interfaceMeta: null }) as unknown as ModelDefinition;

const CLAIM = [{ name: "IdentityClaim", keepOnMerge: true, identityClaim: true }];
const person = { kind: "entity", type: "Person", edgeModel: null };
const sameEntity = { kind: "reifiedRelationDocument", type: "SameEntity", edgeModel: null, params: {} };
const inRole = { kind: "reifiedRelation", type: "InRole", edgeModel: null, params: { T: { typeVar: "T", options: [person] } } };
const negative = {
  kind: "semanticSpace",
  type: "Negative",
  edgeModel: null,
  params: { T: { typeVar: "T", options: [{ kind: "document", type: "Statement", edgeModel: null }, sameEntity] } },
};

const DEFINITIONS = {
  models: {
    Person: model("Person", "Entity", [], [
      { name: "entities_reverse", key: "entitiesReverse", sources: [{ model: "SameAs", field: "entities", viaReified: false }] },
      { name: "statements_reverse", key: "statementsReverse", sources: [{ model: "Factoid", field: "statements", viaReified: true }] },
      // (held by a wrapper that claims nothing, and named plainly by a document: neither is looked through)
      { name: "by_reverse", key: "byReverse", sources: [{ model: "Activity", field: "by", viaReified: true }] },
      { name: "about_reverse", key: "aboutReverse", sources: [{ model: "Activity", field: "about", viaReified: false }] },
      // (a generic class the export names in full, which is no model of the interface's)
      { name: "target_reverse", key: "targetReverse", sources: [{ model: "SameEntity[Person]", field: "target", viaReified: false }] },
    ]),
    Place: model("Place", "Entity", [], []),
    SameEntity: model("SameEntity", "ReifiedRelationDocument", [relation("target", [{ kind: "typeVar", name: "T", edgeModel: null }], CLAIM)]),
    SameAs: model("SameAs", "Document", [relation("entities", [person], CLAIM), relation("witnesses", [person])]),
    InRole: model("InRole", "ReifiedRelation", [relation("target", [{ kind: "typeVar", name: "T", edgeModel: null }])]),
    Negative: model("Negative", "SemanticSpace", []),
    Statement: model("Statement", "Document", []),
    Activity: model("Activity", "Document", [relation("by", [inRole]), relation("about", [person])]),
    Factoid: model("Factoid", "Document", [relation("statements", [{ kind: "document", type: "Statement", edgeModel: null }, sameEntity, negative])]),
  },
} as unknown as ModelDefinitions;

const ref = (id: string, label = id.toUpperCase(), mergedInto: string | null = null) => ({ type: "Person", id, label, mergedInto });
const same = (id: string, label: string, others: string[], argument: string | null = null) => ({
  type: "SameEntity",
  id,
  label,
  argument,
  meta: { semanticSpaces: [] },
  target: [ref("a"), ...others.map((other) => ref(other))],
});
const factoid = (id: string, label: string, statement: unknown) => ({ type: "Factoid", id, label, meta: {}, statements: [statement] });

describe("where claims of identity are found", () => {
  it("knows a field that claims identity by what its marker says, not by its name", () => {
    expect(identityFields(DEFINITIONS.models.SameAs).map((field) => field.name)).toEqual(["entities"]);
    expect(identityFields(DEFINITIONS.models.Activity)).toEqual([]);
    const own = model("Alias", "Document", [relation("of", [person], [{ name: "MyClaim", identityClaim: true }])]);
    expect(identityFields(own).map((field) => field.name)).toEqual(["of"]);
    expect(identityFields(undefined)).toEqual([]);
  });

  it("looks through the reverse fields that can hold one, and no others", () => {
    expect(identityIncoming(DEFINITIONS, "Person")).toEqual([
      { key: "entitiesReverse", direct: true },
      { key: "statementsReverse", direct: false },
    ]);
  });

  it("asks nothing for a type that no claim can name", () => {
    expect(identityIncoming(DEFINITIONS, "Place")).toEqual([]);
    expect(identityIncoming(DEFINITIONS, "Nothing")).toEqual([]);
  });
});

describe("a claim held in a document", () => {
  it("names the others, the statement, the document, and why", () => {
    const [claim, ...rest] = claimsHeld(factoid("f1", "Charter", same("s1", "A is B", ["b"], "same seal")), "a", DEFINITIONS);
    expect(rest).toEqual([]);
    expect(claim).toEqual({
      statement: { id: "s1", type: "SameEntity", label: "A is B", mergedInto: null },
      head: { id: "f1", type: "Factoid", label: "Charter", mergedInto: null },
      spaces: [],
      others: [ref("b")],
      argument: "same seal",
    });
    expect(claimHref(claim!)).toBe("/Factoid/f1?show=s1");
  });

  it("says which semantic spaces it is in, outermost first", () => {
    const inner = { type: "Negative", id: "n2", contents: [same("s1", "A is not B", ["b"])] };
    const [claim] = claimsHeld(factoid("f1", "Charter", { type: "Negative", id: "n1", contents: [inner] }), "a", DEFINITIONS);
    expect(claim!.spaces).toEqual(["Negative", "Negative"]);
    expect(claim!.argument).toBeUndefined();
  });

  it("is not made by a statement that names other entities, nor by a field that claims nothing", () => {
    const others = { ...same("s1", "C is B", []), target: [ref("c"), ref("b")] };
    expect(claimsHeld(factoid("f1", "Charter", others), "a", DEFINITIONS)).toEqual([]);
    const role = { type: "InRole", id: "r1", target: [ref("a"), ref("b")] };
    expect(claimsHeld({ type: "Activity", id: "x", label: "X", by: [role] }, "a", DEFINITIONS)).toEqual([]);
  });

  it("keeps an entity that was merged as it is named, with what it was merged into", () => {
    const merged = { ...same("s1", "A is B", []), target: [ref("a"), ref("b", "B", "a")] };
    const [claim] = claimsHeld(factoid("f1", "Charter", merged), "a", DEFINITIONS);
    expect(claim!.others).toEqual([{ type: "Person", id: "b", label: "B", mergedInto: "a" }]);
  });
});

describe("a claim that is a document's own relation", () => {
  const listed = {
    type: "SameAs",
    id: "s1",
    label: "A is C",
    meta: { headNodeId: "f1", headNodeType: "Factoid", semanticSpaces: ["Negative"] },
  };
  const read = { type: "SameAs", id: "s1", label: "A is C", meta: { headNodeLabel: "Charter" }, entities: [ref("a"), ref("c")], witnesses: [ref("w")] };

  it("takes its spaces and its document from the list, and the entities it names from the statement read in full", () => {
    expect(claimDirect(listed, read, "a", DEFINITIONS)).toEqual([
      {
        statement: { id: "s1", type: "SameAs", label: "A is C", mergedInto: null },
        head: { id: "f1", type: "Factoid", label: "Charter" },
        spaces: ["Negative"],
        others: [ref("c")],
        argument: undefined,
      },
    ]);
  });

  it("is its own document when it is a head, and links to its own page", () => {
    const head = { ...listed, meta: { headNodeId: "s1", headNodeType: "SameAs", semanticSpaces: [] } };
    const [claim] = claimDirect(head, read, "a", DEFINITIONS);
    expect(claim!.head).toEqual({ id: "s1", type: "SameAs", label: "A is C" });
    expect(claimHref(claim!)).toBe("/SameAs/s1");
  });

  it("is none where the statement names the entity only in another of its fields", () => {
    expect(claimDirect(listed, { ...read, entities: [ref("b"), ref("c")], witnesses: [ref("a")] }, "a", DEFINITIONS)).toEqual([]);
  });
});

describe("the claims as the page shows them", () => {
  const plain = claimsHeld(factoid("f1", "Charter", same("s1", "A is B", ["b"])), "a", DEFINITIONS);
  const again = claimsHeld(factoid("f2", "Roll", same("s2", "A is B again", ["b"])), "a", DEFINITIONS);
  const denied = claimsHeld(factoid("f3", "Letter", { type: "Negative", id: "n", contents: [same("s3", "A is not B", ["b"])] }), "a", DEFINITIONS);
  const other = claimsHeld(factoid("f4", "Will", { type: "Negative", id: "n", contents: [same("s4", "A is not C", ["c"])] }), "a", DEFINITIONS);

  it("puts the statements about one entity together, those said plainly before those in a space", () => {
    const groups = grouped([...denied, ...plain, ...other, ...again]);
    expect(groups.map((group) => [group.other.id, group.spaces.join("/"), group.claims.map((claim) => claim.statement.id)])).toEqual([
      ["b", "", ["s1", "s2"]],
      ["b", "Negative", ["s3"]],
      ["c", "Negative", ["s4"]],
    ]);
    expect(byContext(groups).map((context) => [context.spaces, context.groups.map((group) => group.other.id)])).toEqual([
      [[], ["b"]],
      [["Negative"], ["b", "c"]],
    ]);
  });

  it("counts a statement once, though two reverse fields lead to it", () => {
    expect(grouped([...plain, ...plain])[0]!.claims).toHaveLength(1);
  });

  it("puts a statement that names two others under each", () => {
    const three = claimsHeld(factoid("f1", "Charter", same("s1", "All one", ["b", "c"])), "a", DEFINITIONS);
    expect(grouped(three).map((group) => group.other.id)).toEqual(["b", "c"]);
  });

  it("says which entities are said to be the same and, in a space, something else", () => {
    expect([...contested(grouped([...plain, ...denied, ...other]))]).toEqual(["b"]);
    expect(contested(grouped([...plain, ...other])).size).toBe(0);
  });
});

describe("the cluster of an entity", () => {
  const member = (id: string, distance: number, through: string[] = []) => ({ type: "Person", id, label: id.toUpperCase(), mergedInto: null, distance, through });
  const claimOf = (id: string, a: string, b: string, spaces: string[] = [], head = "f1") => ({
    id,
    type: "SameEntity",
    label: `${a} is ${b}`,
    head: { type: "Factoid", id: head, label: "Charter" },
    spaces,
    between: [a, b] as [string, string],
    argument: null,
  });
  const cluster: Cluster = {
    entity: { type: "Person", id: "a", label: "Ann" },
    steps: "all",
    members: [member("b", 1), member("c", 2, ["b"]), member("d", 3, ["b", "c"])],
    size: 4,
    warningSize: 5,
    large: false,
    claims: [claimOf("s1", "a", "b"), claimOf("s2", "b", "c"), claimOf("s3", "c", "d")],
    inSpaces: [claimOf("s4", "a", "c", ["Negative"])],
    truncated: false,
  };

  it("names those the entity is the same as only through others, with the way to each", () => {
    expect(further(cluster).map((found) => [found.member.id, found.through.map((step) => step.label)])).toEqual([
      ["c", ["B"]],
      ["d", ["B", "C"]],
    ]);
    expect(further({ ...cluster, members: [member("b", 1)] })).toEqual([]);
  });

  it("gives each statement in a space with the two members it is about, the entity itself among them", () => {
    const [dispute] = disputes(cluster);
    expect(dispute.claim.spaces).toEqual(["Negative"]);
    expect(dispute.between.map((ref) => [ref.id, ref.label, ref.type])).toEqual([
      ["a", "Ann", "Person"],
      ["c", "C", "Person"],
    ]);
    expect(disputes({ ...cluster, inSpaces: [] })).toEqual([]);
  });

  it("links a claim to its place in its document, or to its own page", () => {
    expect(clusterClaimHref(cluster.claims[0])).toBe("/Factoid/f1?show=s1");
    expect(clusterClaimHref({ ...claimOf("s9", "a", "b", [], "s9"), type: "Alias", head: { type: "Alias", id: "s9", label: "x" } })).toBe("/Alias/s9");
  });

  it("is something to show only when it has a member", () => {
    expect(hasCluster(cluster)).toBe(true);
    expect(hasCluster({ ...cluster, members: [], size: 1 })).toBe(false);
    expect(hasCluster(null)).toBe(false);
    expect(hasCluster(undefined)).toBe(false);
  });

  it("reads from the page's address whether to include the others, and how far", () => {
    expect(stepsOf("all")).toBe("all");
    expect(stepsOf("one")).toBe("one");
    expect(stepsOf(["one", "all"])).toBe("one");
    expect(stepsOf(undefined)).toBeNull();
    expect(stepsOf("")).toBeNull();
    expect(stepsOf("yes")).toBeNull();
  });
});
