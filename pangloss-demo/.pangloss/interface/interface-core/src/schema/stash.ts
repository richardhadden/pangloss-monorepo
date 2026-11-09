/**
 * What a form compares to know whether it has changes, and what a stashed item is brought up to date with when it is
 * opened again: no components.
 */
import type { ModelDefinitions } from "../types";
import { getModel } from "./lookup";
import { cleanForSave } from "./formValue";
import type { FormData } from "./formValue";

const isObject = (value: unknown): value is FormData =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** Whether two plain values are the same: lists in order, objects by their keys (in any order) */
export function sameValue(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (Array.isArray(a)) {
    return Array.isArray(b) && a.length === b.length && a.every((item, at) => sameValue(item, b[at]));
  }
  if (!isObject(a) || !isObject(b)) return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every((key) => key in b && sameValue(a[key], b[key]));
}

/**
 * What a form compares to tell whether its item has changed: what would be sent (`cleanForSave`: a field typed in and
 * emptied again is no change, nor an entity's label), with empty lists left out (an empty list and none are the same
 * to whoever reads it). Reads every part of `item`, so in a memo of a store it follows every change
 */
export function comparableItem(definitions: ModelDefinitions, item: FormData): unknown {
  return withoutEmptyLists(cleanForSave(definitions, item));
}

function withoutEmptyLists(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(withoutEmptyLists);
  if (!isObject(value)) return value;
  const out: FormData = {};
  for (const [key, inner] of Object.entries(value)) {
    if (Array.isArray(inner) && inner.length === 0) continue;
    out[key] = withoutEmptyLists(inner);
  }
  return out;
}

/** An entity that an item refers to */
export interface EntityReference {
  type: string;
  id: string;
  label?: string;
}

const isEntity = (definitions: ModelDefinitions, value: FormData) =>
  typeof value.type === "string" && getModel(definitions, value.type)?.kind === "Entity";

/** The entities `value` refers to, anywhere in it, each once */
export function entityReferences(definitions: ModelDefinitions, value: unknown): EntityReference[] {
  const found = new Map<string, EntityReference>();
  const walk = (inner: unknown) => {
    if (Array.isArray(inner)) {
      inner.forEach(walk);
    } else if (isObject(inner)) {
      if (isEntity(definitions, inner)) {
        if (typeof inner.id === "string" && inner.id !== "" && !found.has(inner.id)) {
          found.set(inner.id, {
            type: String(inner.type),
            id: inner.id,
            ...(typeof inner.label === "string" ? { label: inner.label } : {}),
          });
        }
        return;
      }
      for (const [key, nested] of Object.entries(inner)) if (key !== "meta") walk(nested);
    }
  };
  walk(value);
  return [...found.values()];
}

/** What `refreshReferences` did */
export interface RefreshedReferences {
  value: FormData;
  /** The entities that are no longer there, as they were known: taken out */
  gone: EntityReference[];
  /** The entities whose label is not what it was: given the new one */
  renamed: (EntityReference & { was?: string })[];
}

/**
 * `value` with its references to entities brought up to date with `found` (those that are there, with their labels
 * now: `/api/references`): one that is not found is taken out of the list it is in (or, outside a list, unset), and
 * one whose label has changed has the new label. A new object; `value` is not changed.
 */
export function refreshReferences(
  definitions: ModelDefinitions,
  value: FormData,
  found: { id: string; type: string; label: string }[],
): RefreshedReferences {
  const there = new Map(found.map((item) => [item.id, item]));
  const gone = new Map<string, EntityReference>();
  const renamed = new Map<string, EntityReference & { was?: string }>();
  const GONE = Symbol("gone");
  const walk = (inner: unknown): unknown => {
    if (Array.isArray(inner)) return inner.map(walk).filter((item) => item !== GONE);
    if (!isObject(inner)) return inner;
    if (isEntity(definitions, inner) && typeof inner.id === "string" && inner.id !== "") {
      const now = there.get(inner.id);
      const was = typeof inner.label === "string" ? inner.label : undefined;
      if (!now) {
        gone.set(inner.id, { type: String(inner.type), id: inner.id, ...(was === undefined ? {} : { label: was }) });
        return GONE;
      }
      if (was === now.label) return inner;
      renamed.set(inner.id, { type: now.type, id: now.id, label: now.label, was });
      return { ...inner, label: now.label };
    }
    const out: FormData = {};
    for (const [key, nested] of Object.entries(inner)) {
      const next = walk(nested);
      if (next !== GONE) out[key] = next;
    }
    return out;
  };
  return { value: walk(value) as FormData, gone: [...gone.values()], renamed: [...renamed.values()] };
}
