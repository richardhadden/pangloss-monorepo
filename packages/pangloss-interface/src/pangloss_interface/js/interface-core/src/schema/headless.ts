/**
 * Whether a reified relation or a semantic space is shown without its head bar, only what it holds and its own
 * fields (`InterfaceMeta(headless=True)`): in a field that can hold it and nothing else, one of it, and must. Its
 * type says nothing there, and it is never added or removed. In the view and the form (the view keeps a space's
 * band and its colour, so that a reader still sees that what it holds is inside it).
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

/** The kinds of option, and of model, that can be headless */
const HEADLESS = { reifiedRelation: "ReifiedRelation", semanticSpace: "SemanticSpace" } as const;

/**
 * Whether what `slot` holds, of the type `type`, is shown without its head. (A class declared below it is offered
 * in the field as well: there are two options, and it keeps its head)
 */
export function headlessIn(
  definitions: ModelDefinitions,
  slot: HeadlessSlot | undefined,
  type: string,
): boolean {
  if (!slot || slot.many || !slot.required || slot.options.length !== 1) return false;
  const only = slot.options[0]!;
  if (!(only.kind in HEADLESS) || !("type" in only) || only.type !== type) return false;
  const model = getModel(definitions, type);
  return (
    model?.kind === HEADLESS[only.kind as keyof typeof HEADLESS] && model.interfaceMeta?.headless === true
  );
}
