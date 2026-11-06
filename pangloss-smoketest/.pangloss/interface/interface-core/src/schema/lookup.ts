import type { ModelDefinition, ModelDefinitions } from "../types";

export function getModel(definitions: ModelDefinitions, name: string): ModelDefinition | undefined {
  return Object.hasOwn(definitions.models, name) ? definitions.models[name] : undefined;
}
