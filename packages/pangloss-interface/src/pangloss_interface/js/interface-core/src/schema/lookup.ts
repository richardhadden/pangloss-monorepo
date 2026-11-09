import type { ListField, ModelDefinition, ModelDefinitions } from "../types";

export function getModel(definitions: ModelDefinitions, name: string): ModelDefinition | undefined {
  return Object.hasOwn(definitions.models, name) ? definitions.models[name] : undefined;
}

/**
 * The list of URIs of something that can have them, an entity that takes URLs: it is not a field of the model (every
 * entity's API has it, as `urls`) but is edited and checked as one. Undefined for anything else.
 */
export function urlsField(model: ModelDefinition): ListField | undefined {
  if (model.kind !== "Entity" || !model.acceptUrlAsId) return undefined;
  return {
    kind: "list",
    name: "urls",
    key: "urls",
    item: { type: "str", format: "url" },
    description: null,
    dbField: false,
    readOnly: false,
    required: false,
    nullable: false,
    validators: [],
    itemValidators: [],
  };
}
