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

/**
 * The Documents or the Entities (`kind`), abstract ones too (their pages list their
 * subtypes), in order of the type hierarchy: each model comes after its parent, with its
 * `depth` below the top. Siblings are in alphabetical order.
 */
export function modelHierarchy(
  definitions: ModelDefinitions,
  kind: "Document" | "Entity",
): { model: ModelDefinition; depth: number }[] {
  const ofKind = Object.values(definitions.models).filter((model) => model.kind === kind);
  const names = new Set(ofKind.map((model) => model.name));
  const children = (parent: string | null) =>
    ofKind
      .filter((model) => (model.parent !== null && names.has(model.parent) ? model.parent : null) === parent)
      .sort((a, b) => a.name.localeCompare(b.name));
  const walk = (parent: string | null, depth: number): { model: ModelDefinition; depth: number }[] =>
    children(parent).flatMap((model) => [{ model, depth }, ...walk(model.name, depth + 1)]);
  return walk(null, 0);
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
