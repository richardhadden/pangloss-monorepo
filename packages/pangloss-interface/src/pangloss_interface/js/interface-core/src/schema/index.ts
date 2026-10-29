/**
 * Questions of the definitions of the models, that need no components: what can be
 * shown or related to.
 */
import type {
  FieldDefinition,
  ModelDefinition,
  ModelDefinitions,
  RelationField,
} from "../types";

/** The models that have a page of their own: Documents and Entities that can be made */
export function headModels(definitions: ModelDefinitions): ModelDefinition[] {
  return Object.values(definitions.models)
    .filter((model) => (model.kind === "Document" || model.kind === "Entity") && !model.abstract)
    .sort((a, b) => a.name.localeCompare(b.name));
}

export function getModel(definitions: ModelDefinitions, name: string): ModelDefinition | undefined {
  return Object.hasOwn(definitions.models, name) ? definitions.models[name] : undefined;
}

export function isRelation(field: FieldDefinition): field is RelationField {
  return field.kind === "relation";
}

/** The names of the models that a relation can be to (those that have a page of their own) */
export function relatedModelNames(field: RelationField): string[] {
  return [
    ...new Set(
      field.options.flatMap((option) =>
        option.kind === "document" || option.kind === "entity" ? [option.type] : [],
      ),
    ),
  ].sort();
}
export * from "./modules";
export * from "./nav";
export * from "./hierarchy";
