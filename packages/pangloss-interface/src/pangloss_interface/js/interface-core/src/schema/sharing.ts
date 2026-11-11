/**
 * Shares in a form (`SumsTo`): the items of a list relation whose edge property adds up to a total (the
 * percentages of alternatives) are kept to it as the form is changed. One is set (a slider dragged): the others
 * give way. One is added: it is given an even share. One is taken away: the others share the whole. One is put in
 * the place of another (an entity chosen for it): it keeps its share. (The arithmetic is `share.ts`.)
 */
import type { FieldDefinition, ModelDefinitions, RelationField, Validator } from "../types";
import { composeHooks, createBinder } from "./binding";
import type { FormHook } from "./binding";
import { getAt } from "./formValue";
import type { FormData, Path } from "./formValue";
import { getModel } from "./lookup";
import { added, adjust, removed } from "./share";
import { createLabeller } from "./labelTemplate";
import type { LabelContext } from "./labelTemplate";

const isObject = (value: unknown): value is FormData =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** What the items of a relation share: the key of the edge property, the total, and the least each has */
export interface Shares {
  key: string;
  total: number;
  min: number;
}

/** The least a number field can be, by its validators (`Ge(1)`, `Gt(0)`: 1), or 0 */
function least(validators: Validator[]): number {
  let min = 0;
  for (const validator of validators) {
    if (validator.name === "Ge") min = Math.max(min, Math.ceil(Number(validator.ge)));
    if (validator.name === "Gt") min = Math.max(min, Math.floor(Number(validator.gt)) + 1);
  }
  return min;
}

/** What the items of `field` share (`SumsTo`), if they do */
export function sharesOf(definitions: ModelDefinitions, field: FieldDefinition | undefined): Shares | undefined {
  if (!field || field.kind !== "relation" || !field.many) return undefined;
  const sumsTo = (field.validators ?? []).find((validator) => validator.name === "SumsTo");
  if (!sumsTo) return undefined;
  const option = (field as RelationField).options.find((each) => "edgeModel" in each && each.edgeModel);
  const edgeModel = option && "edgeModel" in option && option.edgeModel ? getModel(definitions, option.edgeModel) : undefined;
  const edgeField = edgeModel?.fields.find((each) => each.name === sumsTo.field);
  if (!edgeField || edgeField.kind !== "literal") return undefined;
  return { key: edgeField.key, total: Number(sumsTo.total ?? 100), min: least(edgeField.validators) };
}

const shareOf = (item: unknown, key: string): number => {
  const value = isObject(item) && isObject(item.edgeProperties) ? Number(item.edgeProperties[key]) : NaN;
  return Number.isFinite(value) ? value : 0;
};

/** What a change under a relation that shares is, and what the shares were before it */
export interface PendingShare {
  at: Path;
  shares: Shares;
  op: "adjust" | "add" | "remove" | "replace";
  index: number;
  before: number[];
}

/** The shares of the models, for a form (`createItemFormState`), beside the bindings (`composeHooks`) */
export function createSharer(definitions: ModelDefinitions): FormHook<PendingShare> {
  return {
    before(root, path, adding) {
      const pending: PendingShare[] = [];
      for (let length = 0; length < path.length - 1; length += 1) {
        const item = getAt(root, path.slice(0, length));
        if (!isObject(item) || typeof item.type !== "string") continue;
        const key = path[length];
        const field = getModel(definitions, item.type)?.fields.find((each) => each.key === key);
        const shares = sharesOf(definitions, field);
        const index = path[length + 1];
        if (!shares || typeof index !== "number") continue;
        const at = path.slice(0, length + 1);
        const list = getAt(root, at);
        const before = Array.isArray(list) ? list.map((each) => shareOf(each, shares.key)) : [];
        const rest = path.slice(length + 2);
        let op: PendingShare["op"] | undefined;
        if (rest.length === 0) op = !adding ? "remove" : index >= before.length ? "add" : "replace";
        else if (rest[0] === "edgeProperties" && (rest.length === 1 || (rest.length === 2 && rest[1] === shares.key))) {
          op = "adjust";
        }
        if (op) pending.push({ at, shares, op, index, before });
      }
      return pending;
    },
    after(root, pending) {
      for (const { at, shares, op, index, before } of pending) {
        const list = getAt(root, at);
        if (!Array.isArray(list)) continue;
        const { key, total, min } = shares;
        let next: number[] | undefined;
        if (op === "add") next = added(before, total, min);
        else if (op === "remove") next = removed(before, index, total, min);
        else if (op === "adjust") {
          const raw = isObject(list[index]) && isObject(list[index].edgeProperties) ? list[index].edgeProperties[key] : undefined;
          const value = raw === "" || raw === null || raw === undefined ? NaN : Number(raw);
          // (a number being typed, not yet one: the others wait for it)
          if (!Number.isFinite(value)) continue;
          next = adjust(before, index, value, total, min);
        } else {
          const item = list[index];
          if (!isObject(item) || (isObject(item.edgeProperties) && item.edgeProperties[key] !== undefined)) continue;
          // (it keeps the share of what it is in the place of; one that had none, as one there from the start, is
          // given an even share)
          next = before[index]! > 0 ? before : adjust(before, index, total / list.length, total, min);
        }
        next.forEach((share, at) => {
          const item = list[at];
          if (!isObject(item)) return;
          // (the one key changed in place: what shows the others is not drawn again)
          if (!isObject(item.edgeProperties)) item.edgeProperties = { [key]: share };
          else if (item.edgeProperties[key] !== share) item.edgeProperties[key] = share;
        });
      }
    },
  };
}

/**
 * What a form of these models does around each change: their bindings, then their shares, then the labels worked out
 * from what the item holds (with the label formatters of the modules, `ModulesValue.labelFormatter`)
 */
export function createFormHooks(
  definitions: ModelDefinitions,
  formatter: LabelContext["formatter"] = () => undefined,
): FormHook<unknown> {
  return composeHooks(
    createBinder(definitions),
    createSharer(definitions),
    createLabeller({ definitions, formatter }),
  ) as FormHook<unknown>;
}
