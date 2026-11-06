import type { ModelDefinition, ModelDefinitions } from "../types";

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
