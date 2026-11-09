/** What the popup of a type says of it: the fields a person fills in, and what each accepts */
import { ancestry } from "./typeChoices";
import type { FieldDefinition, FieldType, ModelDefinition, ModelDefinitions, ScalarTypeName } from "../types";

export type AcceptedType =
  | { kind: "model"; name: string }
  | { kind: "scalar"; scalar: ScalarTypeName }
  | { kind: "enum"; name: string }
  | { kind: "value"; value: string }
  | { kind: "typeVar"; name: string }
  | { kind: "structured" };

/** The fields a form has: not those only in the database, those something else keeps up to date, or those the model's forms hide */
export function editableFields(model: ModelDefinition): FieldDefinition[] {
  const hidden = model.interfaceMeta?.hideOnForms ?? [];
  return model.fields.filter((field) => !field.dbField && !field.readOnly && !hidden.includes(field.key));
}

/** A docstring as text to read: the line breaks of the source are spaces, and only a blank line is a new paragraph */
export function reflowHelp(text: string): string {
  return text
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.replace(/\s+/g, " ").trim())
    .filter((paragraph) => paragraph !== "")
    .join("\n\n");
}

/** Without those that come under another of them */
function topmost(definitions: ModelDefinitions, names: string[]): string[] {
  const all = new Set(names);
  return [...all].filter((name) => !ancestry(definitions, name).some((above) => above !== name && all.has(above)));
}

function ofFieldType(type: FieldType): AcceptedType[] {
  switch (type.type) {
    case "enum":
      return [{ kind: "enum", name: type.enum }];
    case "typedDict":
      return [{ kind: "structured" }];
    case "list":
      return ofFieldType(type.item);
    case "literal":
      return type.values.map((value) => ({ kind: "value", value: String(value) }));
    case "unknown":
      return [];
    default:
      return [{ kind: "scalar", scalar: type.type }];
  }
}

/**
 * What a field accepts, at the top level: the types it was declared with, not what a reified relation or a space among
 * them holds in turn, and a type only once, not also the types below it.
 */
export function acceptedTypes(definitions: ModelDefinitions, field: FieldDefinition): AcceptedType[] {
  const models = (names: string[]): AcceptedType[] =>
    topmost(definitions, names).map((name) => ({ kind: "model", name }));
  switch (field.kind) {
    case "literal":
      return ofFieldType(field.type);
    case "list":
      return ofFieldType(field.item);
    case "typeVar":
      return [{ kind: "typeVar", name: field.typeVar }];
    case "annotatedValue":
      return models([field.model]);
    case "embedded":
      return models(field.model ? [field.model] : field.types);
    case "relation": {
      const named = field.options.flatMap((option) => (option.kind === "typeVar" ? [] : [option.type]));
      const typeVars = field.options.flatMap((option): AcceptedType[] =>
        option.kind === "typeVar" ? [{ kind: "typeVar", name: option.name }] : [],
      );
      return [...models(named), ...typeVars];
    }
    default:
      return [];
  }
}
