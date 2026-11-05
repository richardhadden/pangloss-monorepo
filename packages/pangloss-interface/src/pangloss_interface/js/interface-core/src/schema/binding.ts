/**
 * Field bindings in a form (`bind_to_child_field`): a field of an item is copied to the fields of what one of its
 * relations holds (who received an order, to who gives what is ordered), as it is typed or chosen, as the server gives
 * it to them when the item is written. A child field that was changed is the child's own: it is not changed again when
 * the item's field is. It still follows while it is empty, or the same as what was copied to it.
 */
import type { FieldBindingDefinition, FieldDefinition, ModelDefinition, ModelDefinitions, RelationField } from "../types";
import { fitsRelation } from "./clipboard";
import { getAt } from "./formValue";
import type { FormData, Path } from "./formValue";
import { getModel } from "./lookup";
import { ancestry } from "./typeChoices";

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

/**
 * What is done to the item of a form around each change: what is to be done for a change at `path`, found before it
 * (`adding`: an object is set); and then done, to the item as it is after it (in the store's draft)
 */
export interface FormHook<Pending> {
  before(root: unknown, path: Path, adding: boolean): Pending[];
  after(root: FormData, pending: Pending[]): void;
}

/** What the bindings over a change are (`createBinder`) */
export type FormBinder = FormHook<PendingBinding>;

/** Several hooks as one: each finds what it does before the change, and does it after, in this order */
export function composeHooks(...hooks: FormHook<unknown>[]): FormHook<unknown[]> {
  return {
    before: (root, path, adding) => hooks.map((hook) => hook.before(root, path, adding)),
    after: (root, pending) => hooks.forEach((hook, at) => hook.after(root, pending[at] as unknown[])),
  };
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

/**
 * Whether a binding applies to an item of `type`: its type, a type above it or one of its traits must be one of the
 * binding's allowed types (if it has any), and none of them one of its excluded types; so a binding to a creation of a
 * physical object applies to a creation of a painting too, narrowed or not (as on the server: `binding_applies`)
 */
function applies(definitions: ModelDefinitions, binding: FieldBindingDefinition, type: string): boolean {
  const names = new Set([...ancestry(definitions, type), ...(getModel(definitions, type)?.traits ?? [])]);
  return (
    (binding.allowedTypes.length === 0 || binding.allowedTypes.some((name) => names.has(name))) &&
    !binding.excludedTypes.some((name) => names.has(name))
  );
}

/** The keys of the fields above `type` (in its ancestors and traits) that `field` stands for (its `subclasses`, by name) */
function keysStoodFor(definitions: ModelDefinitions, type: string, field: FieldDefinition): string[] {
  const names = field.kind === "relation" ? ((field as RelationField).subclasses ?? []) : [];
  if (names.length === 0) return [];
  const above = [...ancestry(definitions, type), ...(getModel(definitions, type)?.traits ?? [])].flatMap(
    (name) => getModel(definitions, name)?.fields ?? [],
  );
  return above.filter((other) => names.includes(other.name)).map((other) => other.key);
}

/**
 * The fields of an item that a binding into `key` gives a value to: the field with that key, or, in a type that
 * narrows it, the field that stands for it (`object_created` is `paintingCreated` in a creation of a painting), as on
 * the server (`fields_bound`)
 */
function fieldsBound(definitions: ModelDefinitions, model: ModelDefinition, key: string): FieldDefinition[] {
  return model.fields.filter(
    (field) => field.key === key || keysStoodFor(definitions, model.name, field).includes(key),
  );
}

/**
 * Whether a bound value can go in a field that stands for the bound one (narrower: only a painting can be the
 * painting created): each thing in it is of a type the field holds, and a list only where it holds a list. Nothing
 * always can
 */
function fitsNarrower(definitions: ModelDefinitions, field: FieldDefinition, value: unknown): boolean {
  if (isEmpty(value)) return true;
  if (field.kind !== "relation") return false;
  const relation = field as RelationField;
  if (Array.isArray(value) && !relation.many) return false;
  const items = Array.isArray(value) ? value : [value];
  return items.every((item) => isObject(item) && fitsRelation(definitions, item, relation.options, {}));
}

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
    if (!applies(definitions, rule.binding, value.type)) continue;
    for (const field of fieldsBound(definitions, model, key)) {
      const now = value[field.key];
      if (!isEmpty(now) && !(rule.follows && same(definitions, now, rule.old))) continue;
      // (a narrower field that cannot hold the value is not given it: if it followed the binding, it is emptied, so
      // that it is filled in by hand, and does not keep a value the bound field no longer has)
      const given = field.key === key || fitsNarrower(definitions, field, rule.value) ? rule.value : undefined;
      if (same(definitions, now, given)) continue;
      if (isEmpty(given)) delete value[field.key];
      else value[field.key] = copyOf(definitions, given);
    }
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
