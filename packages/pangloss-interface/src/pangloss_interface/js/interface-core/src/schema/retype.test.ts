import { expect, test } from "vitest";
import type { FieldDefinition, ModelDefinition, ModelDefinitions, RelationOption } from "../types";
import { narrowerTypes, retype, widerTypes } from "./retype";

const model = (name: string, extra: Partial<ModelDefinition> = {}) =>
  ({
    name,
    kind: "Document",
    parent: null,
    abstract: false,
    concreteTypes: [name],
    description: null,
    typeParameters: [],
    createWithId: false,
    acceptUrlAsId: false,
    requireLabel: true,
    useInSemanticSpaceLabel: true,
    interfaceMeta: null,
    fields: [],
    incoming: [],
    ...extra,
  }) as ModelDefinition;

const base = { description: null, dbField: false, required: false, nullable: false };
const literal = (name: string, type: object) =>
  ({ ...base, name, key: name, kind: "literal", type, validators: [] }) as FieldDefinition;
const entities = (...types: string[]): RelationOption[] =>
  types.map((type) => ({ kind: "entity", type, edgeModel: null }));
const relation = (name: string, options: RelationOption[], many: boolean, subclasses: string[] = []) =>
  ({
    ...base,
    name,
    key: name.replace(/_(\w)/g, (_, c: string) => c.toUpperCase()),
    kind: "relation",
    many,
    reverseName: `${name}_r`,
    options,
    validators: [],
    subclasses,
  }) as FieldDefinition;
const doc = (type: string): RelationOption => ({ kind: "document", type, edgeModel: null });

// As in the demo: a statement involves agents; a creation's `created_by` (a person) stands for
// `involves`, and each narrower creation's object stands for the one above it
const statement = [literal("text", { type: "str" }), relation("places", entities("Place"), true)];
const creation = [
  ...statement,
  relation("created_by", entities("Person"), false, ["involves"]),
  relation("object_created", entities("PhysicalObject", "Artwork", "Painting"), false),
];
const definitions = {
  models: {
    Statement: model("Statement", {
      abstract: true,
      concreteTypes: ["Activity", "CreationOfArtwork", "CreationOfPainting", "CreationOfPhysicalObject"],
    }),
    Activity: model("Activity", {
      parent: "Statement",
      fields: [...statement, relation("involves", entities("Person", "Group"), true)],
    }),
    CreationOfPhysicalObject: model("CreationOfPhysicalObject", {
      parent: "Statement",
      concreteTypes: ["CreationOfArtwork", "CreationOfPainting", "CreationOfPhysicalObject"],
      fields: creation,
    }),
    CreationOfArtwork: model("CreationOfArtwork", {
      parent: "CreationOfPhysicalObject",
      concreteTypes: ["CreationOfArtwork", "CreationOfPainting"],
      fields: [
        ...creation.filter((field) => field.name !== "object_created"),
        relation("artwork_created", entities("Artwork", "Painting"), false, ["object_created"]),
        literal("medium", { type: "str" }),
      ],
    }),
    CreationOfPainting: model("CreationOfPainting", {
      parent: "CreationOfArtwork",
      fields: [
        ...creation.filter((field) => field.name !== "object_created"),
        relation("painting_created", entities("Painting"), false, ["artwork_created", "object_created"]),
        literal("medium", { type: "str" }),
      ],
    }),
    // (a concrete parent with a list, and a child with one thing that stands for it)
    Event: model("Event", {
      concreteTypes: ["Event", "Meeting"],
      fields: [relation("involves", entities("Person", "Group"), true)],
    }),
    Meeting: model("Meeting", {
      parent: "Event",
      fields: [relation("chaired_by", entities("Person"), false, ["involves"])],
    }),
    Place: model("Place", { kind: "Entity" }),
    Person: model("Person", { kind: "Entity" }),
    Group: model("Group", { kind: "Entity" }),
    PhysicalObject: model("PhysicalObject", { kind: "Entity", concreteTypes: ["Artwork", "Painting", "PhysicalObject"] }),
    Artwork: model("Artwork", { kind: "Entity", parent: "PhysicalObject", concreteTypes: ["Artwork", "Painting"] }),
    Painting: model("Painting", { kind: "Entity", parent: "Artwork" }),
  },
  enums: {},
} as unknown as ModelDefinitions;

const statements = ["Activity", "CreationOfArtwork", "CreationOfPainting", "CreationOfPhysicalObject"].map(doc);
const rome = { type: "Place", id: "pl1", label: "Rome" };
const alice = { type: "Person", id: "p1", label: "Alice" };

test("the types it can be narrowed or widened to are those the field allows, not the abstract ones", () => {
  expect(narrowerTypes(definitions, "CreationOfPhysicalObject", statements)).toEqual([
    "CreationOfArtwork",
    "CreationOfPainting",
  ]);
  expect(narrowerTypes(definitions, "CreationOfPainting", statements)).toEqual([]);
  // (nearest first; Statement is abstract)
  expect(widerTypes(definitions, "CreationOfPainting", statements)).toEqual([
    "CreationOfArtwork",
    "CreationOfPhysicalObject",
  ]);
  expect(widerTypes(definitions, "CreationOfPhysicalObject", statements)).toEqual([]);
  // (a field that does not hold the wider type)
  expect(widerTypes(definitions, "CreationOfPainting", [doc("CreationOfPainting"), doc("CreationOfArtwork")])).toEqual([
    "CreationOfArtwork",
  ]);
});

const bob = { type: "Person", id: "p2", label: "Bob" };
const thing = { type: "Artwork", id: "a1", label: "The thing" };
const made = {
  type: "CreationOfPhysicalObject",
  id: "s1",
  label: "Making it",
  meta: { version: 3 },
  text: "It was made",
  places: [rome],
  createdBy: alice,
  objectCreated: thing,
};

test("narrowing keeps what is the same and moves a field to the one that stands for it", () => {
  const { value, lost } = retype(definitions, made, "CreationOfArtwork");
  expect(lost).toEqual([]);
  expect(value).toEqual({
    type: "CreationOfArtwork",
    id: "s1",
    label: "Making it",
    meta: { version: 3 },
    text: "It was made",
    places: [rome],
    createdBy: alice,
    artworkCreated: thing,
  });
});

test("narrowing loses what the narrower field does not allow, and says so", () => {
  // (an artwork is not a painting)
  const { value, lost } = retype(definitions, made, "CreationOfPainting");
  expect(lost).toEqual([{ model: "CreationOfPhysicalObject", field: "object_created", count: 1 }]);
  expect(value.paintingCreated).toBeUndefined();
  expect(value.objectCreated).toBeUndefined();
  expect(value.createdBy).toEqual(alice);
});

test("widening by more than one step follows the field it stands for through the others", () => {
  const painting = { type: "Painting", id: "pa1", label: "A painting" };
  const from = { type: "CreationOfPainting", text: "Painted", createdBy: alice, paintingCreated: painting };
  const { value, lost } = retype(definitions, from, "CreationOfPhysicalObject");
  expect(lost).toEqual([]);
  expect(value).toEqual({ type: "CreationOfPhysicalObject", text: "Painted", createdBy: alice, objectCreated: painting });
});

test("widening loses a field the wider type does not have, but only if something is in it", () => {
  const from = { type: "CreationOfArtwork", text: "Made", medium: "oil", artworkCreated: thing };
  const widened = retype(definitions, from, "CreationOfPhysicalObject");
  expect(widened.lost).toEqual([{ model: "CreationOfArtwork", field: "medium", count: 1 }]);
  expect(widened.value).not.toHaveProperty("medium");
  expect(retype(definitions, { ...from, medium: "" }, "CreationOfPhysicalObject").lost).toEqual([]);
  // (a field both have is kept)
  expect(retype(definitions, { ...from, type: "CreationOfPainting" }, "CreationOfArtwork").value.medium).toBe("oil");
});

test("a list becomes one thing when narrowed: the first that fits is kept, the rest are lost", () => {
  const group = { type: "Group", id: "g1", label: "The guild" };
  const { value, lost } = retype(definitions, { type: "Event", involves: [group, alice, bob] }, "Meeting");
  expect(value).toEqual({ type: "Meeting", chairedBy: alice });
  // (the group does not fit; Bob fits, but there is room for one)
  expect(lost).toEqual([{ model: "Event", field: "involves", count: 2 }]);
  expect(retype(definitions, { type: "Event", involves: [alice] }, "Meeting").lost).toEqual([]);
  expect(retype(definitions, { type: "Event", involves: [] }, "Meeting")).toEqual({ value: { type: "Meeting" }, lost: [] });
});

test("one thing becomes a list when widened, and nothing is lost", () => {
  expect(retype(definitions, { type: "Meeting", chairedBy: alice }, "Event")).toEqual({
    value: { type: "Event", involves: [alice] },
    lost: [],
  });
});

test("an entity not yet chosen goes where its type is allowed, and is not counted as lost where it is not", () => {
  const unchosen = { type: "Person" };
  expect(retype(definitions, { type: "Meeting", chairedBy: unchosen }, "Event").value.involves).toEqual([unchosen]);
  const wrong = retype(definitions, { type: "Event", involves: [{ type: "Group" }] }, "Meeting");
  expect(wrong).toEqual({ value: { type: "Meeting" }, lost: [] });
});
