/**
 * The definitions of the models, as exported by `pangloss_models.export.export_models()`
 * (see its docstring for what each means). A file generated from the models of a
 * project has them as a `ModelDefinitions`, and says what to show, and how, everywhere.
 *
 * `name` is the Python name of a field, and `key` the name in the JSON of the API.
 */

/** How a value is stored (`pangloss_models.literals`): a `uuid`, a URL or a path is a `str` with a `format` */
export type ScalarTypeName =
  | "str"
  | "int"
  | "float"
  | "bool"
  | "decimal"
  | "date"
  | "datetime"
  | "time"
  | "duration";

/** What a stored text means, beyond being text; a date, a time or a number has none */
export type ScalarFormat =
  | "uuid"
  | "url"
  | "email"
  | "ip"
  | "ip-network"
  | "ip-interface"
  | "path"
  | "regex"
  | "fraction"
  | "bytes"
  | (string & {});

export type FieldType =
  | { type: ScalarTypeName; format?: ScalarFormat }
  | { type: "enum"; enum: string }
  | { type: "typedDict"; fields: Record<string, FieldType> }
  | { type: "list"; item: FieldType; unique?: boolean; length?: number }
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
  /** Kept up to date by something other than a person (`Protection`): a form does not show it (the item's page does) */
  readOnly: boolean;
  /** May not be left out */
  required: boolean;
  nullable: boolean;
}

export interface LiteralField extends FieldBase {
  kind: "literal";
  type: FieldType;
  validators: Validator[];
  /** How the interface edits it (`Slider`, with its `step`) */
  markers?: FieldMarker[];
  /** The value the class declares for it when it is left out (`year: int = 0`), or null for none */
  default?: unknown;
}

export interface ListField extends FieldBase {
  kind: "list";
  item: FieldType;
  /** The list's own (`MinLen`, `MaxLen`; `Unique` for a set) */
  validators: Validator[];
  itemValidators: Validator[];
  default?: unknown;
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
  /** A list of them (`list[WithCertainty[str]]`) */
  many?: boolean;
}

export interface EmbeddedField extends FieldBase {
  kind: "embedded";
  model: string | null;
  /** The (concrete) models that it can be */
  types: string[];
  /** What the field is annotated with that the server applies to the value (`SortDefault`), and what each says of itself */
  markers?: FieldMarker[];
}

/** A marker of a field: its name, and what it says of itself (`SortDefault` has `sortBy`, `Slider` may have `step`) */
export interface FieldMarker {
  name: string;
  [argument: string]: unknown;
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
  /** The fields of its ancestors that it stands for (`subclasses_parent_fields`), directly or through another, by name */
  subclasses: string[];
  /** The reified relation that an entity found by searching is put in (`default_reified_type`), if any */
  defaultReifiedType?: string | null;
  /** The fields of the model given to fields of what it holds, where they are not set (`bind_to_child_field`) */
  bindings?: FieldBindingDefinition[];
}

/** A field of a model given to fields of what one of its relations holds (`FieldBinding`), by key */
export interface FieldBindingDefinition {
  boundField: string;
  childFields: string[];
  /** Only items of these types are given it (none: any) */
  allowedTypes: string[];
  excludedTypes: string[];
  /** It is changed on the way (a converter), which only the server can do: the interface does not copy it */
  converted: boolean;
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
  /** The section of the navigation bar the type is listed under, if not Entities or Documents (resolved through the parents) */
  navSection?: string | null;
  /** The component of an interface module for the page of the list of the type (resolved through the parents) */
  listPage: ComponentReference | null;
  itemPage: ComponentReference | null;
  /** A card that shows an item where it is part of something else */
  viewCard: ComponentReference | null;
  editCard: ComponentReference | null;
  /**
   * (a ReifiedRelation or a Conjunction) Whether the item page shows it folded into the one thing it holds:
   * `true` by the built-in rule, the same with conditions (`Collapse(...)`), or a rule in `collapseRules` of an
   * interface module (docs/interface-collapse.md)
   */
  collapse?: true | CollapseConditions | ComponentReference | null;
  /**
   * (a ReifiedRelation) Shown without its head bar, only what it holds and its own fields, where it is the only
   * thing a field can hold, one of it, and must (`headlessIn`). In the view and the form
   */
  headless?: true | null;
  /** The keys of fields its forms do not show (the item's page does): `InterfaceMeta(hide_on_forms=...)` */
  hideOnForms?: string[] | null;
  /** The list page shows at first only what something refers to, with a button for all of it, and how many things refer to each */
  listUsedOnly?: true | null;
}

/** `Collapse(...)` in Python: conditions on top of the built-in rule, by the keys of fields */
export interface CollapseConditions {
  /** These, filled, show it whole */
  blocking: string[];
  /** These are not shown beside what it holds when it is folded (and do not stop it, whatever they hold) */
  hidden: string[];
  /** Each of these must hold one of its values */
  when: Record<string, (string | number | boolean | null)[]>;
}

/** `"app:Name"` in Python: a key of `components` in the manifest of the interface module of an app */
export interface ComponentReference {
  module: string;
  name: string;
}

/** Where an app puts a type in the navigation bar (`NavModel`) */
export interface NavModelEntry {
  label: string | null;
  /** The UI translation slot of the label (the label as written is its default-language text) */
  labelSlot: string;
  section: string | null;
  order: number | null;
  hidden: boolean;
}

/** Any other link in the bar (`NavLink`) */
export interface NavLinkEntry {
  label: string;
  labelSlot: string;
  href: string;
  section: string | null;
  order: number | null;
  external: boolean;
  requiresLogin: boolean;
}

/** The apps' `InterfaceConfig`s, merged (the later app wins) */
export interface NavConfig {
  /** The titles of the sections of the bar, in order */
  sections: string[];
  models: Record<string, NavModelEntry>;
  links: NavLinkEntry[];
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
  /** Whether one can be made on its own (`create_directly`): if not, a document is only ever part of another */
  createDirectly: boolean;
  acceptUrlAsId: boolean;
  requireLabel: boolean;
  /** Whether its label is used in the label of a semantic space that contains it */
  useInSemanticSpaceLabel: boolean;
  fields: FieldDefinition[];
  incoming: IncomingRelation[];
  /** The traits it has, by name (`Dateable`...): what kind of thing it is, without reading its fields (none if absent) */
  traits?: string[];
  /** (from the interface's `_interface_meta`; null for a model that sets none, nor its parents) */
  interfaceMeta: InterfaceMeta | null;
}

export interface EnumDefinition {
  name: string;
  members: { name: string; value: string | number | boolean | null }[];
}

/** A field of a search pattern (`export_search_patterns`): the operators it takes, the type of its values, and
 * for a relation the classes it can point at */
export interface SearchFieldDefinition {
  operators: "text" | "compare" | "choice" | "items" | "relation";
  value?: FieldType;
  targets?: string[];
}

/** The search pattern of a model: its fields, and what a search of it can be ordered by */
export interface SearchPatternDefinition {
  kind: "document" | "entity" | "embedded";
  fields: Record<string, SearchFieldDefinition>;
  orderBy: string[];
}

export interface ModelDefinitions {
  models: Record<string, ModelDefinition>;
  enums: Record<string, EnumDefinition>;
  /** (absent: made before there were search patterns) */
  searchPatterns?: Record<string, SearchPatternDefinition>;
  /** (absent: nothing configured) */
  nav?: NavConfig;
  /**
   * What the interface modules add that the project does not use (`InterfaceConfig(disabled=...)`), as `app:key`: a
   * key of `consoleActions`, `newItemActions`, `newItemFields`, `itemSections` or `incomingViews` (absent: none)
   */
  disabled?: string[];
}
