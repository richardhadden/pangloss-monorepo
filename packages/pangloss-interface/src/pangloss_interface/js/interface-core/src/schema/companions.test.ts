import { expect, test } from "vitest";
import type { CompanionDefinition, FieldDefinition, ModelDefinition, ModelDefinitions, RelationOption } from "../types";
import {
  NEW_ENTITY_ID,
  companionToSend,
  isEntitySlot,
  offeredCompanions,
  startCompanion,
  touchedParts,
  withNewEntity,
} from "./companions";
import type { CreationContext } from "./companions";

function model(name: string, kind: ModelDefinition["kind"], given: Partial<ModelDefinition> = {}): ModelDefinition {
  return {
    name,
    kind,
    abstract: false,
    description: null,
    parent: null,
    concreteTypes: [name],
    typeParameters: [],
    createWithId: false,
    createDirectly: true,
    globalSearch: true,
    acceptUrlAsId: false,
    requireLabel: true,
    useInSemanticSpaceLabel: true,
    interfaceMeta: null,
    fields: [],
    incoming: [],
    ...given,
  };
}

const base = { description: null, dbField: false, readOnly: false, nullable: false };
const text = (key: string, required = false): FieldDefinition =>
  ({ ...base, name: key, key, kind: "literal", type: { type: "str" }, validators: [], required, default: null }) as FieldDefinition;
const relation = (
  name: string,
  key: string,
  options: RelationOption[],
  given: { many?: boolean; subclasses?: string[] } = {},
): FieldDefinition =>
  ({
    ...base,
    name,
    key,
    kind: "relation",
    many: given.many ?? false,
    required: true,
    reverseName: `${name}_reverse`,
    options,
    validators: [],
    subclasses: given.subclasses ?? [],
  }) as FieldDefinition;
const entity = (type: string): RelationOption => ({ kind: "entity", type, edgeModel: null });
const document = (type: string): RelationOption => ({ kind: "document", type, edgeModel: null });
const atPage: RelationOption = { kind: "reifiedRelation", type: "AtPage", edgeModel: null, params: {} };

const namingAndGender: CompanionDefinition = {
  name: "naming_and_gender",
  document: "Factoid",
  field: { name: "statements", key: "statements" },
  parts: [
    { type: "Naming", entityField: { name: "named", key: "named" } },
    { type: "Gendering", entityField: { name: "gendered", key: "gendered" } },
  ],
  entityField: null,
  copies: [{ field: { name: "source", key: "source" }, to: { name: "source", key: "source" } }],
  offered: [{ kind: "within", heads: ["Factoid"], fields: [], holders: [] }, { kind: "standalone" }],
};

const definitions: ModelDefinitions = {
  enums: {},
  models: {
    Person: model("Person", "Entity", { companions: [namingAndGender] }),
    Woman: model("Woman", "Entity", { parent: "Person", companions: [namingAndGender] }),
    Place: model("Place", "Entity"),
    Source: model("Source", "Entity"),
    AtPage: model("AtPage", "ReifiedRelation", {
      fields: [text("page", true), relation("target", "target", [entity("Source")], { many: true })],
    }),
    Statement: model("Statement", "Document", {
      abstract: true,
      fields: [relation("involves", "involves", [entity("Person")], { many: true })],
    }),
    Activity: model("Activity", "Document", {
      parent: "Statement",
      fields: [
        relation("carried_out_by", "carriedOutBy", [entity("Person")], { subclasses: ["involves"] }),
        relation("places", "places", [entity("Place")], { many: true }),
        relation("witnesses", "witnesses", [entity("Person")], { many: true }),
      ],
    }),
    Naming: model("Naming", "Document", {
      parent: "Statement",
      fields: [relation("named", "named", [entity("Person")]), text("firstName"), text("familyName")],
    }),
    Gendering: model("Gendering", "Document", {
      parent: "Statement",
      fields: [relation("gendered", "gendered", [entity("Person")]), text("gender", true)],
    }),
    Factoid: model("Factoid", "Document", {
      fields: [
        relation("source", "source", [atPage]),
        relation("statements", "statements", [document("Activity"), document("Naming"), document("Gendering")], {
          many: true,
        }),
      ],
    }),
    Letter: model("Letter", "Document", { fields: [relation("source", "source", [atPage])] }),
  },
};

const source = { type: "AtPage", id: "at-page-1", page: "12", target: [{ type: "Source", id: "s1", label: "Chronicle" }] };
const fromFactoid = (holder = "Activity", field = "carriedOutBy"): CreationContext => ({
  head: { type: "Factoid", value: { type: "Factoid", id: "f1", source, statements: [] } },
  holder,
  field,
});
const john = { type: "Person", label: "John of Gaunt" };

test("a companion is offered within a head it names, and on its own when it says so", () => {
  expect(offeredCompanions(definitions, "Person", fromFactoid()).map((c) => c.name)).toEqual(["naming_and_gender"]);
  expect(offeredCompanions(definitions, "Person", null).map((c) => c.name)).toEqual(["naming_and_gender"]);
  const inALetter: CreationContext = { head: { type: "Letter", value: { type: "Letter" } }, holder: "Letter", field: "x" };
  expect(offeredCompanions(definitions, "Person", inALetter)).toEqual([]);
  expect(offeredCompanions(definitions, "Place", fromFactoid())).toEqual([]);
});

test("a companion that says nothing of where is offered everywhere", () => {
  const anywhere = { ...namingAndGender, offered: [] };
  const defs = { ...definitions, models: { ...definitions.models, Place: model("Place", "Entity", { companions: [anywhere] }) } };
  const inALetter: CreationContext = { head: { type: "Letter", value: { type: "Letter" } }, holder: "Letter", field: "x" };
  expect(offeredCompanions(defs, "Place", inALetter)).toHaveLength(1);
  expect(offeredCompanions(defs, "Place", null)).toHaveLength(1);
});

test("the heads and holders offered within include the types below them, and a field the fields that stand for it", () => {
  const within = (offer: Partial<{ heads: string[]; fields: { model: string; name: string; key: string }[]; holders: string[] }>) => ({
    ...definitions,
    models: {
      ...definitions.models,
      Person: model("Person", "Entity", {
        companions: [{ ...namingAndGender, offered: [{ kind: "within", heads: [], fields: [], holders: [], ...offer }] }],
      }),
    },
  });
  const involves = [{ model: "Statement", name: "involves", key: "involves" }];
  expect(offeredCompanions(within({ holders: ["Statement"] }), "Person", fromFactoid())).toHaveLength(1);
  expect(offeredCompanions(within({ holders: ["Naming"] }), "Person", fromFactoid())).toHaveLength(0);
  // (`carriedOutBy` of an activity stands for `involves` of a statement)
  expect(offeredCompanions(within({ fields: involves }), "Person", fromFactoid())).toHaveLength(1);
  expect(offeredCompanions(within({ fields: involves }), "Person", fromFactoid("Activity", "involves"))).toHaveLength(1);
  expect(offeredCompanions(within({ fields: involves }), "Person", fromFactoid("Activity", "places"))).toHaveLength(0);
  // (not offered on its own, when it names only where in a document)
  expect(offeredCompanions(within({ holders: ["Statement"] }), "Person", null)).toHaveLength(0);
});

test("a companion starts with its parts, the new entity in each, and what it copies from the head", () => {
  const started = startCompanion(definitions, namingAndGender, john, fromFactoid());

  expect(started.type).toBe("Factoid");
  // (a reified relation is copied as one of its own, without its id)
  expect(started.source).toEqual({ type: "AtPage", page: "12", target: [{ type: "Source", id: "s1", label: "Chronicle" }] });
  const [naming, gendering] = started.statements as Record<string, unknown>[];
  expect(naming).toMatchObject({ type: "Naming", named: { type: "Person", id: NEW_ENTITY_ID, label: "John of Gaunt" } });
  expect(gendering).toMatchObject({ type: "Gendering", gendered: { type: "Person", id: NEW_ENTITY_ID } });
});

test("on its own, nothing is copied", () => {
  const started = startCompanion(definitions, namingAndGender, john, null);
  // (the source is blank, as in a new factoid's form)
  expect(started.source).toEqual({ type: "AtPage", target: [] });
});

test("the new entity follows its label as it is typed", () => {
  const started = startCompanion(definitions, namingAndGender, john, null);
  const renamed = withNewEntity(definitions, namingAndGender, started, { type: "Woman", label: "Katherine" });
  const [naming] = renamed.statements as Record<string, Record<string, unknown>>[];
  expect(naming!.named).toEqual({ type: "Woman", id: NEW_ENTITY_ID, label: "Katherine" });
  // (the one given is left as it was)
  expect((started.statements as Record<string, Record<string, unknown>>[])[0]!.named!.label).toBe("John of Gaunt");
});

test("the entity's place in a part is known, so that the form shows it and not a search", () => {
  const started = startCompanion(definitions, namingAndGender, john, null);
  expect(isEntitySlot(namingAndGender, started, ["statements", 0, "named"])).toBe(true);
  expect(isEntitySlot(namingAndGender, started, ["statements", 1, "gendered"])).toBe(true);
  expect(isEntitySlot(namingAndGender, started, ["statements", 0, "firstName"])).toBe(false);
  expect(isEntitySlot(namingAndGender, started, ["source"])).toBe(false);
});

test("a part is touched once something of it is changed, and not by what the companion was given", () => {
  const started = startCompanion(definitions, namingAndGender, john, fromFactoid());
  expect(touchedParts(definitions, namingAndGender, started, started)).toEqual([false, false]);

  const renamed = withNewEntity(definitions, namingAndGender, started, { type: "Person", label: "Johan" });
  // (and a label the template worked out again is not a change of the person's)
  const relabelled = structuredClone(renamed);
  (relabelled.statements as Record<string, unknown>[])[0]!.label = "Johan named";
  (relabelled.statements as Record<string, unknown>[])[0]!.labelAuto = true;
  expect(touchedParts(definitions, namingAndGender, started, relabelled)).toEqual([false, false]);

  const named = structuredClone(started);
  (named.statements as Record<string, unknown>[])[0]!.firstName = "John";
  expect(touchedParts(definitions, namingAndGender, started, named)).toEqual([true, false]);
});

test("what is sent is the touched parts, without the entity, and nothing when none is touched", () => {
  const started = startCompanion(definitions, namingAndGender, john, fromFactoid());
  expect(companionToSend(definitions, namingAndGender, started, started)).toBeNull();

  const named = structuredClone(started);
  (named.statements as Record<string, unknown>[])[0]!.firstName = "John";
  const sent = companionToSend(definitions, namingAndGender, started, named)!;
  expect(sent.source).toEqual(started.source);
  expect(sent.statements).toEqual([{ type: "Naming", firstName: "John" }]);
});

test("a companion that is itself the part is touched by a change to it, and sent without the entity", () => {
  const note: CompanionDefinition = {
    name: "note",
    document: "Letter",
    field: null,
    parts: [],
    entityField: { name: "about", key: "about" },
    copies: [],
    offered: [],
  };
  const defs = {
    ...definitions,
    models: {
      ...definitions.models,
      Letter: model("Letter", "Document", {
        fields: [relation("about", "about", [entity("Person")]), text("body")],
      }),
    },
  };
  const started = startCompanion(defs, note, john, null);
  expect(started.about).toEqual({ type: "Person", id: NEW_ENTITY_ID, label: "John of Gaunt" });
  expect(isEntitySlot(note, started, ["about"])).toBe(true);
  expect(touchedParts(defs, note, started, started)).toEqual([false]);
  expect(companionToSend(defs, note, started, started)).toBeNull();
  const written = { ...started, body: "A letter" };
  expect(touchedParts(defs, note, started, written)).toEqual([true]);
  expect(companionToSend(defs, note, started, written)).toEqual({ type: "Letter", body: "A letter" });
});

test("a list slot holds the entity as its one member", () => {
  const among: CompanionDefinition = {
    ...namingAndGender,
    parts: [{ type: "Activity", entityField: { name: "witnesses", key: "witnesses" } }],
  };
  const started = startCompanion(definitions, among, john, null);
  expect((started.statements as Record<string, unknown>[])[0]!.witnesses).toEqual([
    { type: "Person", id: NEW_ENTITY_ID, label: "John of Gaunt" },
  ]);
});
