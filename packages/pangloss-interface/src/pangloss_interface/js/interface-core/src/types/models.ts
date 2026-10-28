/**
 * The definitions of the models, as exported by `pangloss_models.export.export_models()`
 * (see its docstring for what each means). A file generated from the models of a
 * project has them as a `ModelDefinitions`, and says what to show, and how, everywhere.
 *
 * `name` is the Python name of a field, and `key` the name in the JSON of the API.
 */

export type ScalarTypeName =
  | "str"
  | "int"
  | "float"
  | "bool"
  | "decimal"
  | "date"
  | "datetime"
  | "uuid";

export type FieldType =
  | { type: ScalarTypeName }
  | { type: "enum"; enum: string }
  | { type: "typedDict"; fields: Record<string, FieldType> }
  | { type: "list"; item: FieldType }
  | { type: "literal"; values: (string | number | boolean | null)[] }
  | { type: "unknown"; repr: string };

/** A constraint of the field, such as `{ name: "Ge", ge: 0 }` or `{ name: "MaxLen", max_length: 10 }` */
export interface Validator {
  name: string;
  [argument: string]: unknown;
}

export interface FieldBase {
  name: string;
  key: string;
  description: string | null;
  dbField: boolean;
  /** May not be left out */
  required: boolean;
  nullable: boolean;
}

export interface LiteralField extends FieldBase {
  kind: "literal";
  type: FieldType;
  validators: Validator[];
}

export interface ListField extends FieldBase {
  kind: "list";
  item: FieldType;
  validators: Validator[];
  itemValidators: Validator[];
}

/** A value of the type parameter of a generic model */
export interface TypeVarField extends FieldBase {
  kind: "typeVar";
  typeVar: string;
}

export interface AnnotatedValueField extends FieldBase {
  kind: "annotatedValue";
  model: string;
  valueType: FieldType | null;
}

export interface EmbeddedField extends FieldBase {
  kind: "embedded";
  model: string | null;
  /** The (concrete) models that it can be */
  types: string[];
}

export interface ParameterOptions {
  typeVar: string;
  options: RelationOption[];
}

export type RelationOption =
  | { kind: "document" | "entity"; type: string; edgeModel: string | null }
  | { kind: "typeVar"; name: string; edgeModel: string | null }
  | {
      kind: "semanticSpace" | "conjunction" | "reifiedRelation" | "reifiedRelationDocument";
      type: string;
      edgeModel: string | null;
      params: Record<string, ParameterOptions>;
    }
  | { kind: "unknown"; type: string };

export interface RelationField extends FieldBase {
  kind: "relation";
  /** A list of related, rather than one */
  many: boolean;
  reverseName: string;
  /** What it can relate to */
  options: RelationOption[];
  validators: Validator[];
}

export interface UnknownField extends FieldBase {
  kind: "unknown";
}

export type FieldDefinition =
  | LiteralField
  | ListField
  | TypeVarField
  | AnnotatedValueField
  | EmbeddedField
  | RelationField
  | UnknownField;

export type ModelKind =
  | "Document"
  | "Entity"
  | "Embedded"
  | "ReifiedRelation"
  | "ReifiedRelationDocument"
  | "Conjunction"
  | "SemanticSpace"
  | "AnnotatedValue"
  | "EdgeModel";

export interface IncomingRelation {
  /** The name of the field in the JSON (as `name`) */
  name: string;
  key: string;
  sources: { model: string; field: string; viaReified: boolean }[];
}

/** The base colours of Tailwind, except black and white (the same list as `COLOURS` in pangloss_interface.meta) */
export type Colour =
  | "slate"
  | "gray"
  | "zinc"
  | "neutral"
  | "stone"
  | "mauve"
  | "olive"
  | "mist"
  | "taupe"
  | "red"
  | "orange"
  | "amber"
  | "yellow"
  | "lime"
  | "green"
  | "emerald"
  | "teal"
  | "cyan"
  | "sky"
  | "blue"
  | "indigo"
  | "violet"
  | "purple"
  | "fuchsia"
  | "pink"
  | "rose";

/** What the model said about how it is shown: `_interface_meta = InterfaceMeta(...)` */
export interface InterfaceMeta {
  /** (without one: blue for entities, green for documents, a colour by depth for a semantic space) */
  colour: Colour | null;
}

export interface ModelDefinition {
  name: string;
  kind: ModelKind;
  abstract: boolean;
  description: string | null;
  parent: string | null;
  /** This model and the models below it that are not abstract */
  concreteTypes: string[];
  typeParameters: string[];
  createWithId: boolean;
  acceptUrlAsId: boolean;
  requireLabel: boolean;
  /** Whether its label is used in the label of a semantic space that contains it */
  useInSemanticSpaceLabel: boolean;
  fields: FieldDefinition[];
  incoming: IncomingRelation[];
  /** (from the interface's `_interface_meta`; null for a model that sets none, nor its parents) */
  interfaceMeta: InterfaceMeta | null;
}

export interface EnumDefinition {
  name: string;
  members: { name: string; value: string | number | boolean | null }[];
}

export interface ModelDefinitions {
  models: Record<string, ModelDefinition>;
  enums: Record<string, EnumDefinition>;
}
