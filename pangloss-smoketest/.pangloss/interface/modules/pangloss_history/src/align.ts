// Several versions of an item lined up, row by row, as the compare page shows them and as a restore says what it
// changes: the fields of each object in the order of its model; the parts of a field (nested documents, reified
// relations, entities referred to, an embedded object) matched by id across the versions, in the order they come in;
// each cell marked against the version before it. (docs/history-interface.md)
import { getModel } from "@pangloss/interface-core";
import type { FieldDefinition, ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";

type Data = Record<string, unknown>;

/** A cell against the one in the version before it (the first version has nothing before it: `same` or `absent`) */
export type Mark = "same" | "added" | "removed" | "changed" | "absent";

export interface Cell {
  /** What this version has there (undefined if nothing) */
  value: unknown;
  mark: Mark;
}

/** A step of where a row is: a field of a model, or a part (its type and label) */
export type Step =
  | { kind: "field"; field: FieldDefinition; model: ModelDefinition }
  | { kind: "item"; type: string; label?: string };

export interface AlignedRow {
  /** Unique among the rows: the path to it */
  key: string;
  /** `field`: a value (text, a number, a list of them); `head`: a part (its type and label, or an entity's chip) */
  kind: "field" | "head";
  depth: number;
  /** The field it is the value of, or (a head) that the part is in, and the model that has the field */
  field: FieldDefinition;
  model: ModelDefinition;
  /** A head that is the first of its field's parts says the field's name */
  first: boolean;
  /** A head of an entity referred to (a chip, with nothing under it) */
  entity: boolean;
  /** Where it is, outermost first (not itself) */
  trail: Step[];
  /** The keys of the heads it is under */
  ancestors: string[];
  cells: Cell[];
}

const isObject = (value: unknown): value is Data =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** Nothing to show (the item's page leaves such a row out) */
export const isEmpty = (value: unknown) =>
  value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0);

// (JSON with the keys in order, so that two values that are the same compare the same)
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (isObject(value)) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value ?? null);
}

export const sameValue = (a: unknown, b: unknown) => canonical(a) === canonical(b);

function mark(cells: unknown[], index: number, same: (a: unknown, b: unknown) => boolean): Mark {
  const here = !isEmpty(cells[index]);
  if (index === 0) return here ? "same" : "absent";
  const before = !isEmpty(cells[index - 1]);
  if (here && !before) return "added";
  if (!here && before) return "removed";
  if (!here) return "absent";
  return same(cells[index - 1], cells[index]) ? "same" : "changed";
}

const NESTED_KINDS = new Set(["relation", "embedded", "annotatedValue"]);

/** The parts of a field's value: a list as it is, one object as a list of one */
const partsOf = (value: unknown): unknown[] => (Array.isArray(value) ? value : isObject(value) ? [value] : []);

const partKey = (part: unknown, index: number) =>
  isObject(part) && (typeof part.id === "string" || typeof part.id === "number") ? String(part.id) : `#${index}`;

/** The keys of the parts of every version, in one order: each version's parts in theirs, one new to it after the one
 * it follows there, and after those that this version does not have (what was taken out comes before what was put in
 * its place) */
export function mergeOrder(versions: string[][]): string[] {
  const merged: string[] = [];
  for (const keys of versions) {
    const here = new Set(keys);
    let after = -1;
    for (const key of keys) {
      const at = merged.indexOf(key);
      if (at >= 0) {
        after = at;
        continue;
      }
      while (after + 1 < merged.length && !here.has(merged[after + 1]!)) after += 1;
      merged.splice(after + 1, 0, key);
      after += 1;
    }
  }
  return merged;
}

const typeOf = (part: unknown, field: FieldDefinition): string | undefined =>
  isObject(part) && typeof part.type === "string"
    ? part.type
    : field.kind === "annotatedValue"
      ? field.model
      : field.kind === "embedded"
        ? (field.model ?? undefined)
        : undefined;

const labelOf = (part: unknown) => (isObject(part) && typeof part.label === "string" ? part.label : undefined);

// (a part is the same if it is the same type with the same label; an entity, the same edge properties too: what is
// inside a part is in its own rows)
const samePart = (a: unknown, b: unknown) =>
  isObject(a) &&
  isObject(b) &&
  a.type === b.type &&
  labelOf(a) === labelOf(b) &&
  sameValue(a.edgeProperties ?? null, b.edgeProperties ?? null);

interface Place {
  depth: number;
  path: string;
  trail: Step[];
  ancestors: string[];
}

function alignObject(
  definitions: ModelDefinitions,
  values: unknown[],
  model: ModelDefinition,
  place: Place,
  rows: AlignedRow[],
) {
  for (const field of model.fields ?? []) {
    const cells = values.map((value) => (isObject(value) ? value[field.key] : undefined));
    if (cells.every(isEmpty)) continue;
    const path = `${place.path}.${field.key}`;
    const fieldStep: Step = { kind: "field", field, model };
    if (!NESTED_KINDS.has(field.kind)) {
      rows.push({
        key: path,
        kind: "field",
        depth: place.depth,
        field,
        model,
        first: true,
        entity: false,
        trail: place.trail,
        ancestors: place.ancestors,
        cells: cells.map((value, index) => ({ value: isEmpty(value) ? undefined : value, mark: mark(cells, index, sameValue) })),
      });
      continue;
    }
    const parts = cells.map(partsOf);
    const order = mergeOrder(parts.map((each) => each.map(partKey)));
    order.forEach((partId, position) => {
      const found = parts.map((each) => each.find((part, index) => partKey(part, index) === partId));
      // (its type in the latest version that has it: a part can have been made another type)
      const latest = [...found].reverse().find((part) => part !== undefined);
      const type = typeOf(latest, field);
      const partModel = type ? getModel(definitions, type) : undefined;
      const key = `${path}[${partId}]`;
      const entity = partModel?.kind === "Entity";
      // (an annotated value has no head of its own: its value and what is said of it are rows of the field)
      const headless = field.kind === "annotatedValue";
      if (!headless) {
        rows.push({
          key,
          kind: "head",
          depth: place.depth,
          field,
          model,
          first: position === 0,
          entity,
          trail: place.trail,
          ancestors: place.ancestors,
          cells: found.map((value, index) => ({ value, mark: mark(found, index, samePart) })),
        });
      }
      if (partModel && !entity) {
        alignObject(definitions, found, partModel, {
          depth: headless ? place.depth : place.depth + 1,
          path: key,
          trail: headless
            ? [...place.trail, fieldStep]
            : [...place.trail, fieldStep, { kind: "item", type: type ?? "", label: labelOf(latest) }],
          ancestors: headless ? place.ancestors : [...place.ancestors, key],
        }, rows);
      }
    });
  }
}

// (the label of an item is not one of its model's fields, but it is a part of what was written: the first row)
const LABEL: FieldDefinition = {
  name: "label",
  key: "label",
  kind: "literal",
  type: { type: "str" },
  validators: [],
  description: null,
  dbField: false,
  readOnly: false,
  required: false,
  nullable: true,
};

/** The rows of the versions (oldest first) of an item of `type` */
export function align(definitions: ModelDefinitions, type: string, versions: unknown[]): AlignedRow[] {
  const found = getModel(definitions, type);
  if (!found) return [];
  const model = found.fields.some((field) => field.key === "label")
    ? found
    : { ...found, fields: [LABEL, ...found.fields] };
  const rows: AlignedRow[] = [];
  alignObject(definitions, versions, model, { depth: 0, path: "", trail: [], ancestors: [] }, rows);
  return rows;
}

/** What a change of one version into another changes, as rows: those that differ, but not those inside a part that
 * is added or removed as a whole (the part says it) */
export function changedRows(definitions: ModelDefinitions, type: string, from: unknown, to: unknown): AlignedRow[] {
  const reported = new Set<string>();
  return align(definitions, type, [from, to]).filter((row) => {
    const changed = row.cells[1]!.mark;
    if (changed === "same" || changed === "absent") return false;
    if (row.ancestors.some((key) => reported.has(key))) return false;
    if (row.kind === "head" && changed !== "changed") reported.add(row.key);
    return true;
  });
}
