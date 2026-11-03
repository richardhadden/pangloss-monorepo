/**
 * Whether a reified relation is shown without its head bar, only what it holds and its own fields
 * (`InterfaceMeta(headless=True)`): in a field that can hold it and nothing else, one of it, and must. Its
 * type says nothing there, and it is never added or removed. In the view and the form.
 */
import type { ModelDefinitions, RelationOption } from "../types";
import { getModel } from "./lookup";

/** What of a relation field says whether what it holds can go without its head (`RelationField`) */
export interface HeadlessSlot {
  many: boolean;
  required: boolean;
  /** (resolved: the options of a type parameter are the ones it was given) */
  options: RelationOption[];
}

/** Whether what `slot` holds, of the type `type`, is shown without its head */
export function headlessIn(
  definitions: ModelDefinitions,
  slot: HeadlessSlot | undefined,
  type: string,
): boolean {
  if (!slot || slot.many || !slot.required || slot.options.length !== 1) return false;
  const only = slot.options[0]!;
  if (only.kind !== "reifiedRelation" || only.type !== type) return false;
  const model = getModel(definitions, type);
  return model?.kind === "ReifiedRelation" && model.interfaceMeta?.headless === true;
}
