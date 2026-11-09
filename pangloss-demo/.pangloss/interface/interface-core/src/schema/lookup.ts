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

/** A label short enough for the title of a window: cut at a word, if there is one near the end */
export function shortenLabel(text: string, length = 40): string {
  const whole = text.replace(/\s+/g, " ").trim();
  if (whole.length <= length) return whole;
  const cut = whole.slice(0, length);
  const word = cut.lastIndexOf(" ");
  return `${(word > length / 2 ? cut.slice(0, word) : cut).trimEnd()}…`;
}

// (what the name of a model is when the translations have no plural for it: an English stand-in)
function pluralOf(name: string): string {
  if (/(s|x|ch|sh)$/.test(name)) return `${name}es`;
  if (/[^aeiou]y$/.test(name)) return `${name.slice(0, -1)}ies`;
  return `${name}s`;
}

/** The name of a model in the plural, in the language of the page (given as `modelName` of `useTranslations`) */
export function pluralNameOf(modelName: (model: string, plural?: boolean) => string, type: string): string {
  const named = modelName(type, true);
  return named !== type ? named : pluralOf(modelName(type));
}
