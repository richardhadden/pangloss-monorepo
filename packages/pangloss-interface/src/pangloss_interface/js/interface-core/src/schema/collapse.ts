/**
 * Whether a reified relation or a conjunction is shown folded into the one thing it holds, on the item page
 * (`InterfaceMeta(collapse=...)`, docs/interface-collapse.md). View only: the data is as it is.
 */
import type {
  CollapseConditions,
  CollapseRule,
  ComponentReference,
  FieldDefinition,
  ModelDefinition,
  ModelDefinitions,
} from "../types";
import { getModel } from "./lookup";

type Data = Record<string, unknown>;

export interface Collapsed {
  /** The one thing it holds, shown in its place */
  held: Data;
  /** Its other fields that are filled, shown after it with their names */
  extras: { field: FieldDefinition; value: unknown }[];
}

const isObject = (value: unknown): value is Data =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isEmpty = (value: unknown) =>
  value === null ||
  value === undefined ||
  value === "" ||
  (Array.isArray(value) && value.length === 0);

const isPlain = (value: unknown): boolean =>
  ["string", "number", "boolean"].includes(typeof value) ||
  (Array.isArray(value) && value.every(isPlain));

/** The field that holds what it relates or joins: `target`, or a conjunction's one relation field */
function heldField(model: ModelDefinition): FieldDefinition | undefined {
  if (model.kind === "ReifiedRelation") {
    return model.fields.find((field) => field.key === "target");
  }
  if (model.kind === "Conjunction") {
    const relations = model.fields.filter((field) => field.kind === "relation");
    return relations.length === 1 ? relations[0] : undefined;
  }
  return undefined;
}

// (`true` is the built-in rule with no conditions)
const NO_CONDITIONS: CollapseConditions = { blocking: [], hidden: [], when: {} };

const isReference = (value: object): value is ComponentReference => "module" in value;

/** Whether a field holds one of the values `when` gives for it (an empty field holds none, unless null is one) */
function holdsOneOf(value: unknown, values: CollapseConditions["when"][string]): boolean {
  if (isEmpty(value)) return values.includes(null);
  return Array.isArray(value)
    ? value.every((item) => values.includes(item))
    : values.includes(value as string | number | boolean);
}

/**
 * How `value` is shown folded, or undefined if it is shown whole. It must hold exactly one thing. By the
 * built-in rule (`collapse: true`, or `Collapse(...)` with conditions), what it holds must end as a chip (an
 * entity, or something that folds into one), its other filled fields that are not hidden must be plain values,
 * no blocking field may be filled and each field of `when` must hold one of its values. A named rule
 * (`findRule`) decides instead of all but the one held item.
 */
export function collapsedView(
  value: Data,
  definitions: ModelDefinitions,
  findRule: (reference: ComponentReference) => CollapseRule | undefined,
): Collapsed | undefined {
  const model = getModel(definitions, typeof value.type === "string" ? value.type : "");
  const collapse = model?.interfaceMeta?.collapse;
  if (!model || !collapse) return undefined;
  const field = heldField(model);
  if (!field) return undefined;
  const contents = value[field.key];
  const items = Array.isArray(contents) ? contents : isEmpty(contents) ? [] : [contents];
  if (items.length !== 1 || !isObject(items[0])) return undefined;
  const held = items[0];
  const filled = model.fields
    .filter((other) => other.key !== field.key && !isEmpty(value[other.key]))
    .map((other) => ({ field: other, value: value[other.key] }));
  if (collapse === true || !isReference(collapse)) {
    const conditions = collapse === true ? NO_CONDITIONS : collapse;
    const extras = filled.filter((extra) => !conditions.hidden.includes(extra.field.key));
    if (!extras.every((extra) => isPlain(extra.value))) return undefined;
    if (filled.some((extra) => conditions.blocking.includes(extra.field.key))) return undefined;
    const fits = Object.entries(conditions.when).every(([key, values]) =>
      holdsOneOf(value[key], values),
    );
    if (!fits) return undefined;
    const heldModel = getModel(definitions, typeof held.type === "string" ? held.type : "");
    const endsAsChip =
      heldModel?.kind === "Entity" || collapsedView(held, definitions, findRule) !== undefined;
    return endsAsChip ? { held, extras } : undefined;
  }
  const rule = findRule(collapse);
  if (!rule) {
    // (`pangloss interface check` says why)
    console.warn(
      `The collapse rule '${collapse.module}:${collapse.name}' (${model.name}) does not exist`,
    );
    return undefined;
  }
  return rule(value, model) ? { held, extras: filled } : undefined;
}

/** What a reified relation holds is its `target`; anything else without a label of its own, all its relations */
function contentFields(model: ModelDefinition): FieldDefinition[] {
  return model.kind === "ReifiedRelation"
    ? model.fields.filter((field) => field.key === "target")
    : model.fields.filter((field) => field.kind === "relation");
}

/** Something a folded block holds, and the fields to name before it, outermost first (see `labelledContents`) */
export interface LabelledContent {
  type: string;
  label: string;
  fields: { model: string; name: string }[];
}

/**
 * The labelled things `value` holds, however many wrappers without a label of their own (a conjunction, a reified
 * relation, a semantic space) they are inside, in order: what a block folded in a form shows on its bar, as chips.
 * Where a wrapper has several fields of contents (a cause and a result) the first thing in each says which field it
 * is in; with one there is nothing to tell apart. What has no label yet (a document not filled in, a place where an
 * entity is still to be chosen) is left out.
 */
export function labelledContents(value: unknown, definitions: ModelDefinitions): LabelledContent[] {
  if (!isObject(value)) return [];
  const model = getModel(definitions, typeof value.type === "string" ? value.type : "");
  if (!model) return [];
  const fields = contentFields(model);
  return fields.flatMap((field) => {
    const contents = value[field.key];
    const held = (Array.isArray(contents) ? contents : [contents]).flatMap((item): LabelledContent[] => {
      if (!isObject(item) || typeof item.type !== "string") return [];
      if (typeof item.label === "string" && item.label !== "") return [{ type: item.type, label: item.label, fields: [] }];
      const kind = getModel(definitions, item.type)?.kind;
      return kind === "Entity" || kind === "Document" ? [] : labelledContents(item, definitions);
    });
    if (fields.length > 1 && held[0]) held[0] = { ...held[0], fields: [{ model: model.name, name: field.name }, ...held[0].fields] };
    return held;
  });
}
