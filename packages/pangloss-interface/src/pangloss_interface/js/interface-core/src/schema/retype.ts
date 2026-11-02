/**
 * Changing the type of a document inside another to one below it (narrowing: a creation of a
 * physical object becomes a creation of a painting) or above it (widening), keeping what it holds.
 * A field of the new type takes the value of the field of the old one with the same name, or of the
 * one it stands for (`subclasses`: `artwork_created` for `object_created`), or that stands for it.
 * What does not fit is lost, and said: a widening that loses nothing is done without asking.
 */
import type { FieldDefinition, ModelDefinition, ModelDefinitions, RelationField, RelationOption } from "../types";
import { getModel } from "./lookup";
import { blankItem, filled } from "./formValue";
import type { FormData } from "./formValue";
import { fitEdge, fitsEmbedded, fitsRelation } from "./clipboard";
import { ancestry, optionFor } from "./typeChoices";

const isObject = (value: unknown): value is FormData =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** The types below `type` it can be narrowed to, where `options` (of the field it is in) allow them */
export function narrowerTypes(definitions: ModelDefinitions, type: string, options: RelationOption[]): string[] {
  const model = getModel(definitions, type);
  return (model?.concreteTypes ?? []).filter((name) => name !== type && !!optionFor(options, name));
}

/** The types above `type` it can be widened to (not the abstract ones), nearest first */
export function widerTypes(definitions: ModelDefinitions, type: string, options: RelationOption[]): string[] {
  return ancestry(definitions, type)
    .slice(0, -1)
    .reverse()
    .filter((name) => getModel(definitions, name)?.abstract === false && !!optionFor(options, name));
}

/** A field of the old type whose value would be lost, and how many things in it (the items of a list) */
export interface LostField {
  model: string;
  field: string;
  count: number;
}

export interface Retyped {
  value: FormData;
  lost: LostField[];
}

const standsFor = (field: FieldDefinition): string[] =>
  field.kind === "relation" ? ((field as RelationField).subclasses ?? []) : [];

/** The field of `from` whose value `target` takes: the same name, or one stands for the other */
function sourceOf(from: ModelDefinition, target: FieldDefinition, used: Set<string>): FieldDefinition | undefined {
  const free = from.fields.filter((field) => !used.has(field.name));
  return (
    free.find((field) => field.name === target.name) ??
    free.find(
      (field) => standsFor(target).includes(field.name) || standsFor(field).includes(target.name),
    )
  );
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/** The value of `from` as the value of `to`, and how many things in it are lost */
function carry(
  definitions: ModelDefinitions,
  value: unknown,
  from: FieldDefinition,
  to: FieldDefinition,
): { value?: unknown; lost: number } {
  if (value === undefined || value === null) return { lost: 0 };
  const whole = () => (filled(value) ? 1 : 0);
  if (from.kind === "relation" && to.kind === "relation") {
    const items = (Array.isArray(value) ? value : [value]).filter(isObject);
    const fits = (item: FormData) => {
      const model = getModel(definitions, String(item.type));
      // (an entity not yet chosen fits where its type does)
      if (model?.kind === "Entity" && item.id === undefined) return optionFor(to.options, String(item.type))?.kind === "entity";
      return fitsRelation(definitions, item, to.options, {});
    };
    const fromEdge = (item: FormData) => {
      const option = optionFor(from.options, String(item.type));
      return option && "edgeModel" in option ? option.edgeModel : null;
    };
    const kept = items.filter(fits).map((item) => fitEdge(item, to.options, {}, fromEdge(item)));
    let lost = items.filter((item) => !fits(item) && filled(item)).length;
    if (to.many) return { value: kept, lost };
    // (one where there were several: the first, and the rest are lost)
    lost += kept.slice(1).filter(filled).length;
    return { value: kept[0], lost };
  }
  if (from.kind !== to.kind) return { lost: whole() };
  switch (to.kind) {
    case "literal":
      return from.kind === "literal" && same(from.type, to.type) ? { value, lost: 0 } : { lost: whole() };
    case "list":
      return from.kind === "list" && same(from.item, to.item) ? { value, lost: 0 } : { lost: whole() };
    case "annotatedValue":
      return from.kind === "annotatedValue" && from.model === to.model && same(from.valueType, to.valueType)
        ? { value, lost: 0 }
        : { lost: whole() };
    case "embedded":
      return isObject(value) && fitsEmbedded(definitions, value, to) ? { value, lost: 0 } : { lost: whole() };
    default:
      return same(from, to) ? { value, lost: 0 } : { lost: whole() };
  }
}

/**
 * `value` (a document) as one of type `to`: what is not a field (label, id, meta) kept, each field
 * of `to` filled from its field in the old type (see `sourceOf`) or as a new one would be, and the
 * fields whose values could not be kept (or not all of them) in `lost`. Nothing is lost when only
 * the names differ: a list of one where there is room for one, a single thing where a list is.
 */
export function retype(definitions: ModelDefinitions, value: FormData, to: string): Retyped {
  const from = getModel(definitions, String(value.type));
  const target = getModel(definitions, to);
  if (!from || !target) return { value: { ...value, type: to }, lost: [] };
  const fieldKeys = new Set(from.fields.map((field) => field.key));
  const incoming = new Set(from.incoming.map((relation) => relation.key));
  const out: FormData = {};
  for (const [key, inner] of Object.entries(value)) {
    if (!fieldKeys.has(key) && !incoming.has(key)) out[key] = inner;
  }
  out.type = to;
  const blank = blankItem(definitions, to);
  const used = new Set<string>();
  const lost: LostField[] = [];
  for (const field of target.fields) {
    const source = sourceOf(from, field, used);
    let carried: unknown;
    if (source) {
      used.add(source.name);
      const result = carry(definitions, value[source.key], source, field);
      carried = result.value;
      if (result.lost > 0) lost.push({ model: from.name, field: source.name, count: result.lost });
    }
    if (carried === undefined) carried = blank[field.key];
    if (carried !== undefined) out[field.key] = carried;
  }
  for (const field of from.fields) {
    if (!used.has(field.name) && filled(value[field.key])) {
      const inner = value[field.key];
      lost.push({
        model: from.name,
        field: field.name,
        count: Array.isArray(inner) ? inner.filter(filled).length : 1,
      });
    }
  }
  return { value: out, lost };
}
