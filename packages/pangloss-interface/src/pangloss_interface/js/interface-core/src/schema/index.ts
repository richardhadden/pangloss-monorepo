/**
 * Questions of the definitions of the models, that need no components: what can be
 * shown or related to.
 */
export { getModel } from "./lookup";
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

/** Whether a new one can be made on its own page (`/TYPE/new`): not an abstract class, nor a document
 * that is only ever part of another (`create_directly=False`) */
export function canCreate(model: ModelDefinition): boolean {
  return !model.abstract && model.createDirectly;
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
export * from "./typeChoices";
export * from "./formValue";
export * from "./relationLayout";
export * from "./clipboard";
export * from "./retype";
export * from "./validation";
export * from "./collapse";
export * from "./searchForm";
