/**
 * What is cut or copied, as the clipboard keeps it, and what may be pasted where: no components.
 * A thing on the clipboard is a part of a document (a document inside it, a reified relation, a
 * semantic space, an embedded value) or a reference to an entity, with all that is inside it.
 */
import type { EmbeddedField, ModelDefinition, ModelDefinitions, RelationOption } from "../types";
import { getModel } from "./lookup";
import { envOf, optionFor, resolveOptions } from "./typeChoices";
import type { Env } from "./typeChoices";
import type { FormData } from "./formValue";

const isObject = (value: unknown): value is FormData =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const modelOf = (definitions: ModelDefinitions, value: FormData) =>
  typeof value.type === "string" ? getModel(definitions, value.type) : undefined;

/**
 * A copy of `value` to keep: without what the API only reads (`meta`, and the fields of incoming
 * relations, which a view has and the edit view of a document does not), at every level. An
 * entity is kept only as a reference: `{ type, id, label }` and the properties of the relation.
 */
export function clipValue(definitions: ModelDefinitions, value: FormData): FormData {
  return clipObject(definitions, value);
}

function clipInner(definitions: ModelDefinitions, value: unknown): unknown {
  if (Array.isArray(value)) return value.map((item) => clipInner(definitions, item));
  return isObject(value) ? clipObject(definitions, value) : value;
}

function clipObject(definitions: ModelDefinitions, value: FormData): FormData {
  const model = modelOf(definitions, value);
  if (model?.kind === "Entity") {
    const reference: FormData = { type: value.type, id: value.id };
    if (typeof value.label === "string") reference.label = value.label;
    if (isObject(value.edgeProperties)) reference.edgeProperties = clipObject(definitions, value.edgeProperties);
    return reference;
  }
  const incoming = model?.incoming.map((i) => i.key) ?? [];
  const out: FormData = {};
  for (const [key, inner] of Object.entries(value)) {
    if (key === "meta" || incoming.includes(key) || inner === undefined) continue;
    out[key] = clipInner(definitions, inner);
  }
  return out;
}

/** The ids of the nodes of a document in `value` (not those of the entities it refers to) */
export function nodeIds(definitions: ModelDefinitions, value: unknown, into = new Set<string>()): Set<string> {
  if (Array.isArray(value)) {
    for (const item of value) nodeIds(definitions, item, into);
  } else if (isObject(value) && modelOf(definitions, value)?.kind !== "Entity") {
    if (typeof value.id === "string" && value.id !== "") into.add(value.id);
    for (const [key, inner] of Object.entries(value)) {
      if (key !== "meta") nodeIds(definitions, inner, into);
    }
  }
  return into;
}

/**
 * `value` made ready to paste. A node keeps its id only if it is pasted into the document it was
 * taken from (`sameDocument`) and the id is not there already (`used`): it is then the same node,
 * moved, and keeps when and by whom it was made. Otherwise it is a new node, and has no id (the
 * API refuses the id of a node of another document; two nodes with one id would be written as two).
 * An entity is a reference, and keeps its id wherever it goes.
 */
export function forPaste(
  definitions: ModelDefinitions,
  value: FormData,
  sameDocument: boolean,
  used: Set<string>,
): FormData {
  const taken = new Set(used);
  const walk = (inner: unknown): unknown => {
    if (Array.isArray(inner)) return inner.map(walk);
    if (!isObject(inner)) return inner;
    if (modelOf(definitions, inner)?.kind === "Entity") return structuredClone(inner);
    const out: FormData = {};
    for (const [key, item] of Object.entries(inner)) {
      if (key === "id") {
        if (sameDocument && typeof item === "string" && !taken.has(item)) {
          out.id = item;
          taken.add(item);
        }
        continue;
      }
      out[key] = walk(item);
    }
    return out;
  };
  return walk(value) as FormData;
}

/**
 * Whether `value` can be put in a relation with these `options` (`env` binding its type
 * variables): its type is one of them, and all that is inside it is allowed where it would be. An
 * entity's relation properties are not part of it: they are kept only where the relation has the
 * same properties (`fitEdge`).
 */
export function fitsRelation(
  definitions: ModelDefinitions,
  value: FormData,
  options: RelationOption[],
  env: Env,
): boolean {
  const type = typeof value.type === "string" ? value.type : undefined;
  const option = type ? optionFor(resolveOptions(options, env), type) : undefined;
  const model = type ? getModel(definitions, type) : undefined;
  if (!option || !model || option.kind === "unknown") return false;
  if (model.kind === "Entity") return option.kind === "entity" && typeof value.id === "string";
  // (a document's fields are its own; what else is generic takes its variables from the option)
  const inner = model.kind === "Document" || model.kind === "ReifiedRelationDocument" ? {} : envOf(option, env);
  return fitsModel(definitions, value, model, inner);
}

/** Whether `value` can be the value of an embedded field: one of its types, with all inside allowed */
export function fitsEmbedded(definitions: ModelDefinitions, value: FormData, field: EmbeddedField): boolean {
  const type = typeof value.type === "string" ? value.type : undefined;
  const model = type && field.types.includes(type) ? getModel(definitions, type) : undefined;
  return !!model && fitsModel(definitions, value, model, {});
}

function fitsModel(definitions: ModelDefinitions, value: FormData, model: ModelDefinition, env: Env): boolean {
  return model.fields.every((field) => {
    const inner = value[field.key];
    if (inner === undefined || inner === null) return true;
    if (field.kind === "relation") {
      const items = Array.isArray(inner) ? inner : [inner];
      if (!field.many && Array.isArray(inner)) return false;
      return items.every((item) => isObject(item) && fitsRelation(definitions, item, field.options, env));
    }
    if (field.kind === "embedded") return isObject(inner) && fitsEmbedded(definitions, inner, field);
    return true;
  });
}

/**
 * The entity reference `value`, for a relation with these `options`: its relation properties are
 * kept where the relation has the same model of them, and left out otherwise.
 */
export function fitEdge(value: FormData, options: RelationOption[], env: Env, from?: string | null): FormData {
  if (!isObject(value.edgeProperties)) return value;
  const option = optionFor(resolveOptions(options, env), String(value.type));
  const edgeModel = option && "edgeModel" in option ? option.edgeModel : null;
  if (edgeModel && edgeModel === from) return value;
  const { edgeProperties: _, ...rest } = value;
  return rest;
}

/** A line of the outline of something on the clipboard: its type, its label, and how deep it is */
export interface OutlineLine {
  depth: number;
  type: string;
  label?: string;
  /** The name of the field it is in (none for the top) */
  field?: string;
}

/**
 * What is inside `value`, as lines: each thing with a type, under the one it is in, down to
 * `maxDepth` (an entity is one line: what it refers to is not part of it).
 */
export function outline(definitions: ModelDefinitions, value: FormData, maxDepth = Infinity): OutlineLine[] {
  const lines: OutlineLine[] = [];
  const walk = (inner: FormData, depth: number, field?: string) => {
    const type = typeof inner.type === "string" ? inner.type : undefined;
    if (!type) return;
    lines.push({ depth, type, label: typeof inner.label === "string" ? inner.label : undefined, field });
    const model = getModel(definitions, type);
    if (!model || model.kind === "Entity" || depth >= maxDepth) return;
    for (const f of model.fields) {
      if (f.kind !== "relation" && f.kind !== "embedded") continue;
      const held = inner[f.key];
      for (const item of Array.isArray(held) ? held : [held]) {
        if (isObject(item)) walk(item, depth + 1, f.name);
      }
    }
  };
  walk(value, 0);
  return lines;
}
