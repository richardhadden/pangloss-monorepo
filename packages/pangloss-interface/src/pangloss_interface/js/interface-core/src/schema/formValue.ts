/**
 * The value an edit form works on: a plain tree of objects as the edit view of the API sends it,
 * read and changed by path, started blank, and cleaned for sending.
 */
import type { EmbeddedField, ModelDefinitions, RelationOption, Validator } from "../types";
import { getModel } from "./lookup";
import { choicesOf, choiceValue, envOf, menuGroups, optionFor, resolveOptions } from "./typeChoices";
import type { Env } from "./typeChoices";

export type FormData = Record<string, unknown>;
/** Keys of objects and indexes of lists, from the root */
export type Path = (string | number)[];

const isObject = (value: unknown): value is FormData =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export function getAt(root: unknown, path: Path): unknown {
  let value = root;
  for (const key of path) {
    if (value === null || typeof value !== "object") return undefined;
    value = (value as Record<string | number, unknown>)[key];
  }
  return value;
}

/** Sets the value at `path` of `root`, making the objects and lists on the way (a number is a place in a list) */
export function setAt(root: FormData, path: Path, value: unknown): void {
  let at = root as Record<string | number, unknown>;
  path.forEach((key, index) => {
    if (index === path.length - 1) {
      at[key] = value;
      return;
    }
    if (at[key] === null || typeof at[key] !== "object") {
      at[key] = typeof path[index + 1] === "number" ? [] : {};
    }
    at = at[key] as Record<string | number, unknown>;
  });
}

/**
 * Whether a value has something in it: not nothing, an empty text or an empty list; a thing that is
 * only its type (an entity not yet chosen) is nothing, and so is an annotated value without its value.
 */
export function filled(value: unknown): boolean {
  if (value === null || value === undefined || value === "") return false;
  if (Array.isArray(value)) return value.some(filled);
  if (isObject(value)) {
    if ("value" in value) return filled(value.value);
    return Object.keys(value).some((key) => key !== "type");
  }
  return true;
}

/** Takes away what is at `path`: an item of a list is cut out, a key of an object is deleted */
export function removeAt(root: FormData, path: Path): void {
  const parent = getAt(root, path.slice(0, -1));
  const key = path[path.length - 1];
  if (key === undefined || parent === null || typeof parent !== "object") return;
  if (Array.isArray(parent)) parent.splice(key as number, 1);
  else delete (parent as Record<string, unknown>)[key];
}

/**
 * A new item of the model `type`: only what is certain. A required field that holds one thing
 * (not a list), and has just one thing to put there that is not an entity (which is searched for),
 * starts with it, so that the form shows what has to be filled in: an `AtPage` whose source is to be found
 * (but not one with a `defaultReifiedType`, whose search is shown instead).
 */
export function blankItem(
  definitions: ModelDefinitions,
  type: string,
  env: Env = {},
  depth = 0,
): FormData {
  const item: FormData = { type };
  const model = getModel(definitions, type);
  if (!model || depth > 4) return item;
  for (const field of model.fields) {
    // (the default the class declares, as the API would fill it in: shown, so that what is sent is what is seen)
    if ((field.kind === "literal" || field.kind === "list") && field.default !== null && field.default !== undefined) {
      item[field.key] = structuredClone(field.default);
      continue;
    }
    // (a required list is sent, empty, when nothing is added: the API does not take it as absent)
    if (field.required && field.kind === "list") {
      item[field.key] = [];
      continue;
    }
    if (field.kind !== "relation" || !field.required) continue;
    // (as many as it must have, when there is only one thing, not an entity, they can be: the target of an
    // identification, which is one alternative, has it at once; otherwise, a required list starts empty)
    const least = field.many ? (lengthBound(field.validators, "min") ?? 0) : 1;
    // (one whose entities are searched for in a reified relation shows the search, not the relation)
    const options = field.defaultReifiedType ? [] : resolveOptions(field.options, env);
    const choices = choicesOf(menuGroups(definitions, options));
    const only = choices.length === 1 ? choices[0]! : undefined;
    const blank =
      only && getModel(definitions, only.type)?.kind !== "Entity"
        ? () => {
            const option = optionFor(options, only.type);
            return only.spaces.length === 0 && option
              ? blankItem(definitions, only.type, envOf(option, env), depth + 1)
              : choiceValue(definitions, only);
          }
        : undefined;
    if (field.many) item[field.key] = blank ? Array.from({ length: least }, blank) : [];
    else if (blank) item[field.key] = blank();
  }
  return item;
}

/** The least (`MinLen`) or the most (`MaxLen`) items a list may have, by the validators of its field */
export function lengthBound(validators: Validator[] | undefined, bound: "min" | "max"): number | undefined {
  const [name, key] = bound === "min" ? ["MinLen", "min_length"] : ["MaxLen", "max_length"];
  const found = validators?.find((validator) => validator.name === name)?.[key];
  return typeof found === "number" ? found : undefined;
}

/**
 * What to send: the item of the form without what the API only reads (`meta`, the fields of
 * incoming relations), and, inside it, a reference to an entity only as `{ type, id }` (and the
 * properties of the relation), one that has not been chosen left out, and what was left empty left out.
 * (An entity inside an item is always a reference: entities are never part of a document.)
 */
export function cleanForSave(definitions: ModelDefinitions, item: FormData): FormData {
  const model = typeof item.type === "string" ? getModel(definitions, item.type) : undefined;
  return cleanObject(definitions, item, model?.incoming.map((i) => i.key) ?? []);
}

function cleanValue(definitions: ModelDefinitions, value: unknown): unknown {
  if (Array.isArray(value)) {
    return value
      .map((item) => cleanValue(definitions, item))
      .filter((item) => item !== undefined && item !== "");
  }
  if (!isObject(value)) return value;
  const type = typeof value.type === "string" ? value.type : undefined;
  const model = type ? getModel(definitions, type) : undefined;
  if (model?.kind === "Entity") {
    if (value.id === undefined || value.id === "") return undefined;
    const reference: FormData = { type, id: value.id };
    const edge = cleanValue(definitions, value.edgeProperties);
    if (isObject(edge) && Object.keys(edge).length > 0) reference.edgeProperties = edge;
    return reference;
  }
  return cleanObject(definitions, value, model?.incoming.map((i) => i.key) ?? []);
}

function cleanObject(definitions: ModelDefinitions, value: FormData, incoming: string[]): FormData {
  const out: FormData = {};
  for (const [key, inner] of Object.entries(value)) {
    if (key === "meta" || incoming.includes(key) || inner === undefined || inner === "") continue;
    const cleaned = cleanValue(definitions, inner);
    if (cleaned !== undefined) out[key] = cleaned;
  }
  return out;
}

/**
 * `item` with each embedded field that is not set given what `pick` says for it (nothing: it stays unset), in the item
 * and in every item under it, through its relations: what a form made somewhere starts with (a date, from the day of a
 * calendar it was made on). Not in an entity under it, which is only a reference, nor inside an embedded value (the
 * start and the end of a period are not filled). A new object where something is set; the rest as it was.
 */
export function fillEmbedded(
  definitions: ModelDefinitions,
  item: FormData,
  pick: (field: EmbeddedField) => unknown,
  under = false,
): FormData {
  const model = typeof item.type === "string" ? getModel(definitions, item.type) : undefined;
  if (!model || model.kind === "Embedded" || (under && model.kind === "Entity")) return item;
  const deeper = (value: unknown): unknown =>
    Array.isArray(value) ? value.map(deeper) : isObject(value) ? fillEmbedded(definitions, value, pick, true) : value;
  let filled: FormData | undefined;
  for (const field of model.fields) {
    const value = item[field.key];
    let next = value;
    if (field.kind === "embedded" && (value === undefined || value === null)) next = pick(field) ?? value;
    else if (field.kind === "relation") next = deeper(value);
    if (next !== value) (filled ??= { ...item })[field.key] = next;
  }
  return filled ?? item;
}

/**
 * Whether an item of `type`, or one that can be put somewhere under it through its relations (not an entity, which is
 * only referred to), has an embedded field that `accepts` says yes to: a document whose statements can have a date
 */
export function reachesEmbedded(
  definitions: ModelDefinitions,
  type: string,
  accepts: (field: EmbeddedField) => boolean,
  seen: Set<string> = new Set(),
): boolean {
  if (seen.has(type)) return false;
  seen.add(type);
  const model = getModel(definitions, type);
  if (!model || model.kind === "Entity") return false;
  const reaches = (option: RelationOption): boolean => {
    if (option.kind === "typeVar" || option.kind === "unknown" || option.kind === "entity") return false;
    const types = [option.type, ...(getModel(definitions, option.type)?.concreteTypes ?? [])];
    if (types.some((each) => reachesEmbedded(definitions, each, accepts, seen))) return true;
    // (what a semantic space, a conjunction or a reified relation holds is in its parameters)
    return "params" in option && Object.values(option.params).some((param) => param.options.some(reaches));
  };
  return model.fields.some((field) =>
    field.kind === "embedded" ? accepts(field) : field.kind === "relation" && field.options.some(reaches),
  );
}
