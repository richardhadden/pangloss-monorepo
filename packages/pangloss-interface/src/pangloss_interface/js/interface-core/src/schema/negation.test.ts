import { expect, test } from "vitest";
import type { FieldDefinition, ModelDefinitions, RelationOption } from "../types";
import { blankItem } from "./formValue";
import { formMenuGroups, negate, negatedValue, negationFor, unnegate } from "./negation";
import { relationLayout } from "./relationLayout";
import { choicesOf, menuGroups } from "./typeChoices";

const contents: FieldDefinition = {
  name: "contents",
  key: "contents",
  kind: "relation",
  many: true,
  required: true,
  options: [{ kind: "typeVar", name: "T", edgeModel: null }],
} as unknown as FieldDefinition;
const degree = { name: "how_likely", key: "howLikely", kind: "literal", dbField: false } as unknown as FieldDefinition;
const stored = { name: "stamp", key: "stamp", kind: "literal", dbField: true } as unknown as FieldDefinition;

const space = (name: string, not: boolean, fields: FieldDefinition[] = [contents]) => ({
  name,
  kind: "SemanticSpace",
  parent: null,
  fields,
  logical: not ? { not: true } : null,
  interfaceMeta: null,
});
const plain = (name: string, kind: string) => ({ name, kind, parent: null, fields: [], interfaceMeta: null });

const definitions = {
  models: {
    Not: space("Not", true),
    Nicht: space("Nicht", true),
    // (a "not" with a field of its own, and one with a field only in the database)
    Doubted: space("Doubted", true, [contents, degree]),
    Stamped: space("Stamped", true, [contents, stored]),
    Denied: space("Denied", false),
    Person: plain("Person", "Entity"),
    Purchase: plain("Purchase", "Document"),
    Sale: plain("Sale", "Document"),
    InRole: plain("InRole", "ReifiedRelation"),
    Together: plain("Together", "Conjunction"),
    PGCitation: plain("PGCitation", "Document"),
  },
  enums: {},
} as unknown as ModelDefinitions;

const entity = (type: string, edgeModel: string | null = null): RelationOption => ({ kind: "entity", type, edgeModel });
const doc = (type: string, edgeModel: string | null = null): RelationOption => ({ kind: "document", type, edgeModel });
const inSpace = (type: string, inner: RelationOption[], edgeModel: string | null = null): RelationOption => ({
  kind: "semanticSpace",
  type,
  edgeModel,
  params: { T: { typeVar: "T", options: inner } },
});
const reified = (type: string, kind: "reifiedRelation" | "conjunction" = "reifiedRelation"): RelationOption => ({
  kind,
  type,
  edgeModel: null,
  params: {},
});

test("an item offered plainly and inside one bare 'not' space can be negated, in that space", () => {
  expect(negationFor(definitions, [entity("Person"), inSpace("Not", [entity("Person")])], {}, "Person")).toBe("Not");
  const statements = [doc("Purchase"), inSpace("Not", [doc("Purchase")])];
  expect(negationFor(definitions, statements, {}, "Purchase")).toBe("Not");
  // (reified relations and conjunctions too)
  expect(negationFor(definitions, [reified("InRole"), inSpace("Not", [reified("InRole")])], {}, "InRole")).toBe("Not");
  const together = reified("Together", "conjunction");
  expect(negationFor(definitions, [together, inSpace("Not", [together])], {}, "Together")).toBe("Not");
  // (a field only in the database is not one to fill in)
  expect(negationFor(definitions, [doc("Purchase"), inSpace("Stamped", [doc("Purchase")])], {}, "Purchase")).toBe(
    "Stamped",
  );
});

test("the space's contents are read through the type variable the option binds", () => {
  const options = [{ kind: "typeVar", name: "S", edgeModel: null } as RelationOption, inSpace("Not", [doc("Purchase")])];
  expect(negationFor(definitions, options, { S: [doc("Purchase")] }, "Purchase")).toBe("Not");
});

test("no toggle where the type is not offered plainly, or not inside the space", () => {
  // (a field that holds only `Not[X]`: a headless space, say)
  expect(negationFor(definitions, [inSpace("Not", [doc("Purchase")])], {}, "Purchase")).toBeUndefined();
  // (the space does not take it)
  expect(negationFor(definitions, [doc("Purchase"), inSpace("Not", [doc("Sale")])], {}, "Purchase")).toBeUndefined();
  expect(negationFor(definitions, [doc("Purchase")], {}, "Purchase")).toBeUndefined();
});

test("no toggle for a space that is not a 'not', or one with a field of its own", () => {
  expect(negationFor(definitions, [doc("Purchase"), inSpace("Denied", [doc("Purchase")])], {}, "Purchase")).toBeUndefined();
  expect(negationFor(definitions, [doc("Purchase"), inSpace("Doubted", [doc("Purchase")])], {}, "Purchase")).toBeUndefined();
});

test("no toggle where two 'not' spaces take it: the menu says which", () => {
  const options = [doc("Purchase"), inSpace("Not", [doc("Purchase")]), inSpace("Nicht", [doc("Purchase")])];
  expect(negationFor(definitions, options, {}, "Purchase")).toBeUndefined();
  // (nor where one of the two has a field of its own)
  const either = [doc("Purchase"), inSpace("Not", [doc("Purchase")]), inSpace("Doubted", [doc("Purchase")])];
  expect(negationFor(definitions, either, {}, "Purchase")).toBeUndefined();
});

test("no toggle where a relation has properties on its edge, plainly, to the space or inside it", () => {
  expect(negationFor(definitions, [entity("Person", "Certainty"), inSpace("Not", [entity("Person")])], {}, "Person")).toBeUndefined();
  expect(negationFor(definitions, [entity("Person"), inSpace("Not", [entity("Person")], "Certainty")], {}, "Person")).toBeUndefined();
  expect(negationFor(definitions, [entity("Person"), inSpace("Not", [entity("Person", "Certainty")])], {}, "Person")).toBeUndefined();
});

test("no toggle for a space as the item, nor for a citation", () => {
  const nested = inSpace("Not", [doc("Purchase")]);
  expect(negationFor(definitions, [nested, inSpace("Not", [nested])], {}, "Not")).toBeUndefined();
  const cites = { kind: "document", type: "PGCitation", edgeModel: null, cites: ["Purchase"] } as RelationOption;
  expect(negationFor(definitions, [cites, inSpace("Not", [cites])], {}, "PGCitation")).toBeUndefined();
});

const statements = [doc("Purchase"), doc("Sale"), inSpace("Not", [doc("Purchase"), doc("Sale")])];
const purchase = { type: "Purchase", id: "p1", label: "Bought", price: 3 };

test("a 'not' holding one item that its toggle would make is drawn as that item", () => {
  expect(negatedValue(definitions, statements, {}, { type: "Not", contents: [purchase] })).toEqual({
    space: "Not",
    item: purchase,
    at: ["contents", 0],
  });
  const witness = [entity("Person"), inSpace("Not", [entity("Person")])];
  const someone = { type: "Person", id: "e1", label: "Someone" };
  expect(negatedValue(definitions, witness, {}, { type: "Not", contents: [someone] })?.item).toEqual(someone);
});

test("anything else in a 'not' is drawn as a space, with its head", () => {
  // (empty, or two)
  expect(negatedValue(definitions, statements, {}, { type: "Not", contents: [] })).toBeUndefined();
  expect(negatedValue(definitions, statements, {}, { type: "Not", contents: [purchase, purchase] })).toBeUndefined();
  // (a space in it)
  const deeper = [doc("Purchase"), inSpace("Not", [doc("Purchase"), inSpace("Not", [doc("Purchase")])])];
  expect(
    negatedValue(definitions, deeper, {}, { type: "Not", contents: [{ type: "Not", contents: [purchase] }] }),
  ).toBeUndefined();
  // (what it holds is not offered plainly)
  const onlyInside = [doc("Sale"), inSpace("Not", [doc("Purchase"), doc("Sale")])];
  expect(negatedValue(definitions, onlyInside, {}, { type: "Not", contents: [purchase] })).toBeUndefined();
  // (a space with a field of its own, or not a "not")
  const doubted = [doc("Purchase"), inSpace("Doubted", [doc("Purchase")])];
  expect(negatedValue(definitions, doubted, {}, { type: "Doubted", contents: [purchase] })).toBeUndefined();
  const denied = [doc("Purchase"), inSpace("Denied", [doc("Purchase")])];
  expect(negatedValue(definitions, denied, {}, { type: "Denied", contents: [purchase] })).toBeUndefined();
  // (an entity not yet chosen: a search, with no bar for the toggle)
  const witness = [entity("Person"), inSpace("Not", [entity("Person")])];
  expect(negatedValue(definitions, witness, {}, { type: "Not", contents: [{ type: "Person" }] })).toBeUndefined();
  expect(negatedValue(definitions, statements, {}, purchase)).toBeUndefined();
});

test("negating and taking it out again gives back the same value, and the space's own id is kept", () => {
  const negated = negate(definitions, purchase, "Not");
  expect(negated).toEqual({ type: "Not", contents: [purchase] });
  expect(unnegate(negated)).toEqual({ item: purchase, kept: {} });
  // (a saved one, taken out and put back)
  const saved = { type: "Not", id: "n1", label: "not: Bought", contents: [purchase] };
  const { item, kept } = unnegate(saved);
  expect(item).toEqual(purchase);
  expect(negate(definitions, item, "Not", kept)).toEqual(saved);
});

test("the menu leaves out of a 'not' what its toggle makes, and keeps what is only offered inside it", () => {
  const names = (options: RelationOption[]) =>
    formMenuGroups(definitions, options).map((group) => [group.spaces, group.columns.flat().map((row) => row.name)]);
  expect(names([doc("Purchase"), inSpace("Not", [doc("Purchase")])])).toEqual([[[], ["Purchase"]]]);
  expect(names([doc("Purchase"), inSpace("Not", [doc("Purchase"), doc("Sale")])])).toEqual([
    [[], ["Purchase"]],
    [["Not"], ["Sale"]],
  ]);
  // (no toggle: the menu as it was)
  const two = [doc("Purchase"), inSpace("Not", [doc("Purchase")]), inSpace("Nicht", [doc("Purchase")])];
  expect(formMenuGroups(definitions, two)).toEqual(menuGroups(definitions, two));
  const denied = [doc("Purchase"), inSpace("Denied", [doc("Purchase")])];
  expect(formMenuGroups(definitions, denied)).toEqual(menuGroups(definitions, denied));
  // (a space inside a space has a group of its own, chosen there)
  const deeper = [doc("Purchase"), inSpace("Denied", [doc("Purchase"), inSpace("Not", [doc("Purchase")])])];
  expect(formMenuGroups(definitions, deeper)).toEqual(menuGroups(definitions, deeper));
});

test("an entity in a 'not' is not a button beside the search, and a blank item follows the menu", () => {
  const witness = [entity("Person"), inSpace("Not", [entity("Person")])];
  expect(relationLayout(definitions, witness, {})).toEqual({ search: [{ type: "Person", wrappers: [] }], rest: [] });
  // (a required claim that is plain or denied: the one choice left, there at once)
  const withClaim = {
    ...definitions,
    models: {
      ...definitions.models,
      Report: {
        ...plain("Report", "Document"),
        fields: [{ name: "claim", key: "claim", kind: "relation", many: false, required: true, options: statements.slice(0, 1).concat(inSpace("Not", [doc("Purchase")])) }],
      },
    },
  } as unknown as ModelDefinitions;
  expect(choicesOf(formMenuGroups(withClaim, [doc("Purchase"), inSpace("Not", [doc("Purchase")])]))).toHaveLength(1);
  expect(blankItem(withClaim, "Report").claim).toEqual({ type: "Purchase" });
});

test("a type that an interface module draws by a card of its own has no toggle, and stays in the menu", () => {
  // (found by the second reading: review's stand-in and criteria's `MatchesCriteria` are drawn by an `editCard`,
  // which has no bar to put the toggle in)
  const carded = {
    ...definitions,
    models: {
      ...definitions.models,
      Mention: { ...plain("Mention", "Document"), interfaceMeta: { editCard: { module: "review", name: "Editor" } } },
    },
  } as unknown as ModelDefinitions;
  const options = [doc("Mention"), doc("Purchase"), inSpace("Not", [doc("Mention"), doc("Purchase")])];
  expect(negationFor(carded, options, {}, "Mention")).toBeUndefined();
  expect(negationFor(carded, options, {}, "Purchase")).toBe("Not");
  expect(negatedValue(carded, options, {}, { type: "Not", contents: [{ type: "Mention" }] })).toBeUndefined();
  // (the menu still offers it inside the space, and no longer the one its toggle makes)
  expect(choicesOf(formMenuGroups(carded, options))).toEqual([
    { spaces: [], type: "Mention" },
    { spaces: [], type: "Purchase" },
    { spaces: ["Not"], type: "Mention" },
  ]);
});
