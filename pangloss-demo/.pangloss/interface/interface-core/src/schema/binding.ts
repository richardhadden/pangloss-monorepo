/**
 * Field bindings in a form (`bind_to_child_field`): a field of an item is copied to the fields of what one of its
 * relations holds (who received an order, to who gives what is ordered), as it is typed or chosen, as the server gives
 * it to them when the item is written. A child field that was changed is the child's own: it is not changed again when
 * the item's field is. It still follows while it is empty, or the same as what was copied to it.
 */
import type { FieldBindingDefinition, ModelDefinitions, RelationField } from "../types";
import { getAt } from "./formValue";
import type { FormData, Path } from "./formValue";
import { getModel } from "./lookup";

const isObject = (value: unknown): value is FormData =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isEmpty = (value: unknown) =>
  value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0);

/** What a binding is waiting to do after a change: the item it is on, its relation, and the field's value before */
export interface PendingBinding {
  at: Path;
  relation: string;
  binding: FieldBindingDefinition;
  /** The value of the bound field before the change (it changed: what still has it follows); none, for what was added */
  old?: unknown;
  /** Something was added under the relation: what is empty in it is given the value */
  added: boolean;
}

/** What is done to the item of a form around each change: what the bindings over `path` are, before; and then */
export interface FormBinder {
  before: (root: unknown, path: Path, adding: boolean) => PendingBinding[];
  after: (root: FormData, pending: PendingBinding[]) => void;
}

/** The relations of the item that bind (and whose value can be copied: not one with a converter, which only the server can do) */
function bindingsOf(definitions: ModelDefinitions, item: FormData): { relation: string; binding: FieldBindingDefinition }[] {
  const model = typeof item.type === "string" ? getModel(definitions, item.type) : undefined;
  if (!model || model.kind === "Entity" || model.kind === "Embedded") return [];
  return model.fields.flatMap((field) =>
    field.kind === "relation"
      ? ((field as RelationField).bindings ?? [])
          .filter((binding) => !binding.converted)
          .map((binding) => ({ relation: field.key, binding }))
      : [],
  );
}

/**
 * A copy of a value to put in another field: a plain tree, without the ids (and `meta`) of what is not an entity, so
 * that a reified relation copied is a new one, of its own; an entity is referred to as it is
 */
function copyOf(definitions: ModelDefinitions, value: unknown): unknown {
  if (Array.isArray(value)) return value.map((each) => copyOf(definitions, each));
  if (!isObject(value)) return value;
  const entity = typeof value.type === "string" && getModel(definitions, value.type)?.kind === "Entity";
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => entity || (key !== "id" && key !== "meta"))
      .map(([key, each]) => [key, copyOf(definitions, each)]),
  );
}

/** What two values are, to say whether they are the same: an entity is its type, its id and the relation's properties */
function sameAs(definitions: ModelDefinitions, value: unknown): unknown {
  if (Array.isArray(value)) return value.map((each) => sameAs(definitions, each));
  if (!isObject(value)) return value ?? null;
  if (typeof value.type === "string" && getModel(definitions, value.type)?.kind === "Entity") {
    return { type: value.type, id: String(value.id), edgeProperties: sameAs(definitions, value.edgeProperties ?? null) };
  }
  return Object.fromEntries(
    Object.keys(value)
      .filter((key) => key !== "id" && key !== "meta" && key !== "label")
      .sort()
      .map((key) => [key, sameAs(definitions, value[key])]),
  );
}

const same = (definitions: ModelDefinitions, a: unknown, b: unknown) =>
  (isEmpty(a) && isEmpty(b)) || JSON.stringify(sameAs(definitions, a)) === JSON.stringify(sameAs(definitions, b));

const applies = (binding: FieldBindingDefinition, type: string) =>
  (binding.allowedTypes.length === 0 || binding.allowedTypes.includes(type)) && !binding.excludedTypes.includes(type);

/** What a child field is to be given, and whether it is only where it is empty (`old` absent) */
interface Rule {
  binding: FieldBindingDefinition;
  value: unknown;
  old?: unknown;
  follows: boolean;
}

/**
 * The items under a relation, and under them, each given what `rules` say for its fields: where it is empty, or (when
 * the bound field changed) where it is what the bound field was. An item that binds the same field under one of its
 * own relations is the nearest: under it, its own value is given (to what was added), or nothing is changed.
 */
function give(definitions: ModelDefinitions, value: unknown, rules: Map<string, Rule>, adding: boolean): void {
  if (Array.isArray(value)) {
    for (const each of value) give(definitions, each, rules, adding);
    return;
  }
  if (!isObject(value) || typeof value.type !== "string") return;
  const model = getModel(definitions, value.type);
  if (!model || model.kind === "Entity" || model.kind === "Embedded") return;
  for (const [key, rule] of rules) {
    if (!applies(rule.binding, value.type) || !model.fields.some((field) => field.key === key)) continue;
    const now = value[key];
    if (!isEmpty(now) && !(rule.follows && same(definitions, now, rule.old))) continue;
    if (same(definitions, now, rule.value)) continue;
    if (isEmpty(rule.value)) delete value[key];
    else value[key] = copyOf(definitions, rule.value);
  }
  for (const field of model.fields) {
    if (field.kind !== "relation") continue;
    const own = ((field as RelationField).bindings ?? []).filter((binding) => !binding.converted);
    let under = rules;
    if (own.length > 0) {
      under = new Map(rules);
      for (const binding of own) {
        for (const key of binding.childFields) {
          if (adding) under.set(key, { binding, value: value[binding.boundField], follows: false });
          else under.delete(key);
        }
      }
    }
    if (under.size > 0) give(definitions, value[field.key], under, adding);
  }
}

/** The bindings of the models, for a form (`createItemFormState`) */
export function createBinder(definitions: ModelDefinitions): FormBinder {
  return {
    before: (root, path, adding) => {
      const pending: PendingBinding[] = [];
      for (let length = 0; length < path.length; length += 1) {
        const item = getAt(root, path.slice(0, length));
        if (!isObject(item)) continue;
        const key = path[length];
        for (const { relation, binding } of bindingsOf(definitions, item)) {
          const at = path.slice(0, length);
          // (the bound field, or something in it, changes: what has its value follows it)
          if (binding.boundField === key) {
            pending.push({ at, relation, binding, old: copyOf(definitions, item[key]), added: false });
          }
          // (something is put under the relation: what is empty in it is given the value)
          else if (relation === key && adding) pending.push({ at, relation, binding, added: true });
        }
      }
      return pending;
    },
    after: (root, pending) => {
      for (const { at, relation, binding, old, added } of pending) {
        const item = getAt(root, at);
        if (!isObject(item)) continue;
        const value = item[binding.boundField];
        if (!added && same(definitions, value, old)) continue;
        const rules = new Map<string, Rule>(
          binding.childFields.map((key) => [key, { binding, value, old, follows: !added }]),
        );
        give(definitions, item[relation], rules, added);
      }
    },
  };
}
