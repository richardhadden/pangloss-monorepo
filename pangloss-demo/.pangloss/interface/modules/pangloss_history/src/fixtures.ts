// Model definitions for the tests: a Factoid with text, a year, a list of Statements (documents inside it) and the
// Places it refers to (entities); a Statement with its own text and a Person; an embedded Date
import type { FieldDefinition, ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";

const base = { description: null, dbField: false, readOnly: false, required: false, nullable: true };

export const literal = (name: string, key = name): FieldDefinition =>
  ({ ...base, name, key, kind: "literal", type: { type: "str" }, validators: [] }) as FieldDefinition;

export const relation = (name: string, key: string, kind: "document" | "entity", type: string, many = true) =>
  ({
    ...base,
    name,
    key,
    kind: "relation",
    many,
    reverseName: "is_in",
    options: [{ kind, type, edgeModel: null }],
    validators: [],
    subclasses: [],
  }) as FieldDefinition;

export const model = (name: string, kind: ModelDefinition["kind"], fields: FieldDefinition[]): ModelDefinition =>
  ({
    name,
    kind,
    abstract: false,
    description: null,
    parent: null,
    concreteTypes: [],
    typeParameters: [],
    createWithId: false,
    createDirectly: true,
    acceptUrlAsId: false,
    requireLabel: true,
    useInSemanticSpaceLabel: true,
    interfaceMeta: null,
    fields,
    incoming: [],
  }) as ModelDefinition;

export const DEFINITIONS: ModelDefinitions = {
  models: {
    // (as exported: the label is not a field)
    Factoid: model("Factoid", "Document", [
      literal("text"),
      literal("year"),
      relation("statements", "statements", "document", "Statement"),
      relation("places", "places", "entity", "Place"),
      { ...base, name: "when", key: "when", kind: "embedded", model: "Date", types: ["Date"] } as FieldDefinition,
    ]),
    Statement: model("Statement", "Document", [
      literal("label"),
      literal("text"),
      relation("about", "about", "entity", "Person", false),
    ]),
    Date: model("Date", "Embedded", [literal("year")]),
    Place: model("Place", "Entity", [literal("label")]),
    Person: model("Person", "Entity", [literal("label")]),
  },
  enums: {},
};
