import { getModel } from "@pangloss/interface-core";
import type { FieldDefinition, ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import type { Values } from "./api";

// The comparison of two entities to be merged, without a DOM: a row for each field, which of the two the survivor
// takes it from, and the fields that are sent (implementation_docs/entity-identity.md, "The comparison page").
// `a` is the entity that stays and `b` the one it absorbs, each as its edit view; `suggested` is what the API
// would give the survivor if nothing were chosen (the preview's `values`, or those of a proposal).

/** Where the survivor's value of a field comes from: one of the two, both (a list), or what was suggested as it is */
export type Choice = "a" | "b" | "both" | "suggested";

export interface Row {
  field: FieldDefinition;
  /** The values of the two, without references to either of them */
  a: unknown;
  b: unknown;
  /** What can be chosen, in the order it is offered */
  options: Choice[];
}

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** Nothing to show or keep: absent, the empty text, a list of none */
export function isEmpty(value: unknown): boolean {
  return value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0);
}

/** Whether a value is a reference to an entity: `{ type, id }` of an entity class */
export function isReference(value: unknown, definitions: ModelDefinitions): value is Record<string, unknown> {
  return (
    isObject(value) &&
    typeof value.id === "string" &&
    typeof value.type === "string" &&
    getModel(definitions, value.type)?.kind === "Entity"
  );
}

// (the keys in order, without the ids of nodes and what says only how a value is shown, so that two readings of one
// value are alike)
function plain(value: unknown, definitions: ModelDefinitions): unknown {
  if (Array.isArray(value)) return value.map((item) => plain(item, definitions));
  if (!isObject(value)) return value ?? null;
  // (a reference is its id, whatever label it was read with; its edge's properties are part of it)
  if (isReference(value, definitions)) return { id: value.id, edge: plain(value.edgeProperties, definitions) };
  return Object.fromEntries(
    Object.keys(value)
      .filter((key) => key !== "id" && key !== "meta" && value[key] !== undefined && value[key] !== null)
      .sort()
      .map((key) => [key, plain(value[key], definitions)]),
  );
}

/** What says that two values of a field are the same one: a reference by its id, anything else by what it holds */
export function identity(value: unknown, definitions: ModelDefinitions): string {
  return JSON.stringify(plain(value, definitions));
}

/** Whether two values of a field are the same (nothing is nothing, however it is written) */
export function same(one: unknown, other: unknown, definitions: ModelDefinitions): boolean {
  if (isEmpty(one) || isEmpty(other)) return isEmpty(one) && isEmpty(other);
  return identity(one, definitions) === identity(other, definitions);
}

/** Both lists as one: the first, then what the second has that it has not */
export function union(one: unknown, other: unknown, definitions: ModelDefinitions): unknown[] {
  const first = Array.isArray(one) ? one : [];
  const seen = new Set(first.map((item) => identity(item, definitions)));
  const rest = (Array.isArray(other) ? other : []).filter((item) => {
    const key = identity(item, definitions);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  return [...first, ...rest];
}

/** A value without its references to the entities `ids`: the survivor never refers to itself, nor to what it absorbs */
export function without(value: unknown, ids: readonly string[]): unknown {
  const named = (item: unknown) => isObject(item) && typeof item.id === "string" && ids.includes(item.id);
  if (Array.isArray(value)) return value.filter((item) => !named(item));
  return named(value) ? null : value;
}

/**
 * A value of the entity absorbed as the survivor can be given it: what is a node of that entity (an embedded date, a
 * document nested in it) without its id, so that it is made anew and the absorbed entity keeps its own. References
 * to entities stay as they are
 */
export function asNew(value: unknown, definitions: ModelDefinitions): unknown {
  if (Array.isArray(value)) return value.map((item) => asNew(item, definitions));
  if (!isObject(value) || isReference(value, definitions)) return value;
  return Object.fromEntries(
    Object.keys(value)
      .filter((key) => key !== "id" && key !== "meta")
      .map((key) => [key, asNew(value[key], definitions)]),
  );
}

/** Whether a field holds several: a list of literals, of relations or of annotated values */
export function isList(field: FieldDefinition): boolean {
  return (
    field.kind === "list" ||
    (field.kind === "relation" && field.many) ||
    (field.kind === "annotatedValue" && field.many === true)
  );
}

/**
 * The rows of the comparison: the fields of the class the survivor is to have that either entity has something in,
 * in the order of the model. A field that something other than a person keeps up to date is not offered
 */
export function rows(model: ModelDefinition, a: Values, b: Values, definitions: ModelDefinitions): Row[] {
  const ids = [String(a.id ?? ""), String(b.id ?? "")];
  return model.fields
    .filter((field) => !field.readOnly && field.kind !== "unknown")
    .map((field) => ({
      field,
      a: without(a[field.key], ids),
      b: asNew(without(b[field.key], ids), definitions),
      options: (isList(field) ? ["a", "b", "both"] : ["a", "b"]) as Choice[],
    }))
    .filter((row) => !isEmpty(row.a) || !isEmpty(row.b));
}

/** What a choice gives a field */
export function valueOf(
  row: Row,
  choice: Choice,
  suggested: Values | null | undefined,
  definitions: ModelDefinitions,
): unknown {
  if (choice === "suggested") return suggested?.[row.field.key];
  if (choice === "both") return union(row.a, row.b, definitions);
  const value = choice === "a" ? row.a : row.b;
  return isList(row.field) ? (Array.isArray(value) ? value : []) : (value ?? null);
}

/**
 * The choice a row starts with: the one that gives what was suggested (a list: both; a single value: the survivor's,
 * or the other's where it has none). What was suggested and is none of them (the absorbed label put among the
 * aliases by the class's rule) is kept as it is, as a choice of its own. With nothing suggested, the same rule.
 */
export function startingChoice(
  row: Row,
  suggested: Values | null | undefined,
  definitions: ModelDefinitions,
): Choice {
  const order: Choice[] = isList(row.field) ? ["both", "a", "b"] : ["a", "b"];
  if (!suggested || !(row.field.key in suggested)) {
    if (isList(row.field)) return "both";
    return isEmpty(row.a) ? "b" : "a";
  }
  const wanted = suggested[row.field.key];
  return order.find((choice) => same(valueOf(row, choice, suggested, definitions), wanted, definitions)) ?? "suggested";
}

export type Choices = Record<string, Choice>;

/** The starting choice of every row, by the key of its field */
export function startingChoices(
  all: Row[],
  suggested: Values | null | undefined,
  definitions: ModelDefinitions,
): Choices {
  return Object.fromEntries(all.map((row) => [row.field.key, startingChoice(row, suggested, definitions)]));
}

/**
 * The fields that are sent: what was suggested (which has what no row shows: the URLs of both, the fields nothing
 * is in), with each row's choice over it, and the label and the class
 */
export function chosenValues(
  all: Row[],
  choices: Choices,
  suggested: Values | null | undefined,
  label: string,
  type: string,
  definitions: ModelDefinitions,
): Values {
  const values: Values = { ...(suggested ?? {}) };
  for (const row of all) {
    const choice = choices[row.field.key] ?? startingChoice(row, suggested, definitions);
    values[row.field.key] = valueOf(row, choice, suggested, definitions);
  }
  return { ...values, type, label };
}

function ancestors(definitions: ModelDefinitions, type: string): string[] {
  const found: string[] = [];
  for (let model = getModel(definitions, type); model; model = model.parent ? getModel(definitions, model.parent) : undefined) {
    found.push(model.name);
  }
  return found;
}

/**
 * The classes the survivor can be offered: the one suggested first (the narrower of the two, or one that is both),
 * then each entity's own. One only when the two are of one class: there is then nothing to choose
 */
export function classChoices(
  definitions: ModelDefinitions,
  aType: string,
  bType: string,
  suggested: string | null | undefined,
): string[] {
  const all = [suggested, aType, bType].filter(
    (type): type is string => typeof type === "string" && getModel(definitions, type) !== undefined,
  );
  return [...new Set(all)];
}

/** Whether `type` is `other` or below it */
export function isA(definitions: ModelDefinitions, type: string, other: string): boolean {
  return ancestors(definitions, type).includes(other);
}

/**
 * The fields that the survivor's class does not have and that an entity of another class has something in: they are
 * not kept on the survivor (they stay on the entity absorbed, or in the survivor's history)
 */
export function notKept(
  definitions: ModelDefinitions,
  type: string,
  entities: Values[],
): { model: string; field: FieldDefinition }[] {
  const kept = new Set((getModel(definitions, type)?.fields ?? []).map((field) => field.key));
  const lost = new Map<string, { model: string; field: FieldDefinition }>();
  for (const entity of entities) {
    const model = typeof entity.type === "string" ? getModel(definitions, entity.type) : undefined;
    for (const field of model?.fields ?? []) {
      if (!kept.has(field.key) && !isEmpty(entity[field.key])) lost.set(field.key, { model: model!.name, field });
    }
  }
  return [...lost.values()];
}

/**
 * The classes an entity to merge with one of `type` may be of: its whole family, from the topmost entity class it
 * descends from down (a parent, a subclass and a sibling can each be merged with it, if the models allow)
 */
export function mergeableTypes(definitions: ModelDefinitions, type: string): string[] {
  const top = ancestors(definitions, type)
    .filter((name) => getModel(definitions, name)?.kind === "Entity")
    .at(-1);
  return top ? (getModel(definitions, top)?.concreteTypes ?? [type]) : [type];
}

/** How many refer to an entity, the kinds with most first: `[["Factoid", 12], ["Group", 1]]` (ten at most) */
export function referringKinds(counts: Record<string, number> | undefined, most = 10): [string, number][] {
  return Object.entries(counts ?? {})
    .filter(([, count]) => count > 0)
    .sort((one, other) => other[1] - one[1] || one[0].localeCompare(other[0]))
    .slice(0, most);
}

/** How long ago, in whole days (0 for today, or a time that cannot be read) */
export function daysSince(when: string | null | undefined, now: number): number {
  const then = when ? new Date(when).getTime() : Number.NaN;
  return Number.isNaN(then) ? 0 : Math.max(0, Math.floor((now - then) / 86_400_000));
}
