/**
 * The search form back from a pattern: `whereToForm` turns the `where` that `compileSearch` makes (which is what a
 * stored pattern holds) into the form's state again, so that a saved pattern can be edited in the form. What the form
 * cannot show is `null`, never a form with part of the pattern. See implementation_docs/search-form.md.
 */
import type { ModelDefinitions } from "../types";
import {
  extraRowsOf,
  flagsOf,
  incomingSourcesOf,
  nodeWhere,
  operatorsOf,
  searchFieldsOf,
  searchKindOf,
  semanticSpacesOf,
  spaceChoicesOf,
  targetsEntities,
} from "./searchForm";
import type {
  ExtraRow,
  FieldSearch,
  IncomingSearch,
  NodeSearch,
  PickedEntity,
  SearchField,
  SearchOperator,
  SomewhereSearch,
} from "./searchForm";
import { ancestry } from "./typeChoices";

type Where = Record<string, unknown>;

const isObject = (value: unknown): value is Where =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const isStrings = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === "string");

// (a value that a box of the form holds: a text, a number, a yes or no)
const isPlain = (value: unknown) => typeof value === "string" || typeof value === "number" || typeof value === "boolean";

/** Where a node of the form is: what it may hold depends on it */
interface Place {
  type: string;
  root: boolean;
  alternative: boolean;
  /** The semantic spaces it can be inside (`spaceChoicesOf` the relation to it); all of them, if not given */
  spaces?: string[];
}

/** One condition of a `where`: one key and its value, and whether it was in the `where` itself or in its `$all` */
interface Part {
  where: Where;
  first: boolean;
}

/**
 * The conditions a `where` puts together, in order: each key of its own (`first`: the first condition on that key),
 * then each of its `$all` (those on a key that was taken already), as `combineWhere` made it
 */
function partsOf(where: Where): Part[] | null {
  const parts: Part[] = [];
  for (const [key, value] of Object.entries(where)) {
    if (key !== "$all") parts.push({ where: { [key]: value }, first: true });
  }
  const rest = where.$all;
  if (rest === undefined) return parts;
  if (!Array.isArray(rest) || !rest.every((each) => isObject(each) && Object.keys(each).length > 0)) return null;
  for (const each of rest as Where[]) parts.push({ where: each, first: false });
  return parts;
}

/**
 * The conditions of a `where` with every `$all` taken apart, at any depth: what holds when all of them do. Its own
 * keys first, then those of its `$all`, in the order `combineWhere` put them there (whatever the order of the keys)
 */
function flatParts(where: Where): Where[] | null {
  const parts: Where[] = [];
  for (const [key, value] of Object.entries(where)) {
    if (key !== "$all") parts.push({ [key]: value });
  }
  if (where.$all === undefined) return parts;
  if (!Array.isArray(where.$all)) return null;
  for (const each of where.$all) {
    if (!isObject(each)) return null;
    const inner = flatParts(each);
    if (!inner) return null;
    parts.push(...inner);
  }
  return parts;
}

// (the one key of a condition, and its value)
const single = (part: Where): [string, unknown] => Object.entries(part)[0]!;

/** An entity picked in the form, from its id: its type if the relation can point at only one, and no label yet */
const picked = (id: string, targets: string[]): PickedEntity => ({
  type: targets.length === 1 ? targets[0]! : "",
  id,
  label: "",
});

/** The type a relation's nested form is of: one that can be searched, at or above or below one of the targets */
function fitsTargets(definitions: ModelDefinitions, type: string, targets: string[]): boolean {
  if (!searchKindOf(definitions, type)) return false;
  const above = ancestry(definitions, type);
  return targets.some((target) => above.includes(target) || ancestry(definitions, target).includes(type));
}

const VALUE_OPS = new Set<SearchOperator>(["contains", "starts_with", "eq", "gt", "gte", "lt", "lte"]);

/** One condition on a field, as the form has it (without `not`), from its value in the `where`; `null` if the form has none such */
function conditionOf(definitions: ModelDefinitions, place: Place, field: SearchField, value: unknown): FieldSearch | null {
  if (!isObject(value)) return null;
  const { through, ...rest } = value;
  const ops = operatorsOf(definitions, field);
  const targets = field.targets ?? [];
  let search: FieldSearch | null = null;
  const keys = Object.keys(rest);
  if (through !== undefined && (field.operators !== "relation" || !isStrings(through) || through.length === 0)) return null;
  if (keys.length === 0) {
    // (a relation that must pass through wrappers, and nothing else yet)
    if (through === undefined) return null;
    search = targetsEntities(definitions, field) ? { op: "any", entities: [] } : { op: "match" };
  } else if (keys.includes("type")) {
    if (keys.some((key) => key !== "type" && key !== "where")) return null;
    const type = rest.type;
    if (typeof type !== "string" || !fitsTargets(definitions, type, targets)) return null;
    const inner = rest.where === undefined ? {} : rest.where;
    if (!isObject(inner)) return null;
    const node = nodeOf(definitions, { type, root: false, alternative: false, spaces: spaceChoicesOf(definitions, place.type, field.name) }, inner);
    if (!node) return null;
    search = { op: "match", node };
  } else if (keys.length === 1) {
    const [key, given] = single(rest);
    if (VALUE_OPS.has(key as SearchOperator) && isPlain(given)) search = { op: key as SearchOperator, value: given };
    else if (key === "between" && Array.isArray(given) && given.length === 2 && given.every(isPlain)) {
      search = { op: "between", value: [...given] };
    } else if (key === "in" && Array.isArray(given) && given.length > 0 && given.every(isPlain)) {
      search = { op: "in", value: [...given] };
    } else if (key === "exists" && given === true) search = { op: "exists" };
    else if (key === "exists" && given === false && through === undefined) search = { op: "missing" };
    else if (key === "is_any" && isStrings(given) && given.length > 0) {
      search = { op: "any", entities: given.map((id) => picked(id, targets)) };
    } else if (key === "is" && typeof given === "string") search = { op: "all", entities: [picked(given, targets)] };
  }
  if (!search || !ops.includes(search.op)) return null;
  if (through !== undefined) search.through = [...(through as string[])];
  return search;
}

/** A condition on a field that wants what does not hold: the body of a `$not`, whose conditions are all on `field` */
function negatedOf(definitions: ModelDefinitions, place: Place, field: SearchField, parts: Where[]): FieldSearch | null {
  if (parts.length === 1) {
    const search = conditionOf(definitions, place, field, parts[0]![field.name]);
    return search && { ...search, not: true };
  }
  // (several: all of some entities, a condition for each, as `all` makes them)
  const each = parts.map((part) => conditionOf(definitions, place, field, part[field.name]));
  if (each.some((search) => search?.op !== "all")) return null;
  const through = JSON.stringify(each[0]!.through ?? null);
  if (each.some((search) => JSON.stringify(search!.through ?? null) !== through)) return null;
  const search: FieldSearch = { op: "all", not: true, entities: each.flatMap((one) => one!.entities ?? []) };
  if (each[0]!.through) search.through = each[0]!.through;
  return search;
}

/** What a document mentions (`$mentions`), from the condition's value */
function mentionOf(value: unknown): FieldSearch | null {
  if (!isObject(value) || Object.keys(value).length !== 1) return null;
  const [key, given] = single(value);
  if (key === "is_any" && isStrings(given) && given.length > 0) {
    return { op: "any", entities: given.map((id) => picked(id, [])) };
  }
  if (key === "is" && typeof given === "string") return { op: "all", entities: [picked(given, [])] };
  return null;
}

/** Something that refers to an entity of `place.type` (an item of `$incoming`) */
function incomingOf(definitions: ModelDefinitions, place: Place, pattern: unknown): IncomingSearch | null {
  if (!isObject(pattern) || Object.keys(pattern).some((key) => !["type", "field", "where"].includes(key))) return null;
  const { type, field, where } = pattern;
  if (typeof type !== "string" || (field !== undefined && typeof field !== "string")) return null;
  const sources = incomingSourcesOf(definitions, place.type);
  if (!sources.some((source) => source.model === type && (field === undefined || source.field === field))) return null;
  const inner = where === undefined ? {} : where;
  if (!isObject(inner)) return null;
  const node = nodeOf(definitions, { type, root: false, alternative: false }, inner);
  if (!node) return null;
  return field === undefined ? { node } : { field, node };
}

/** A document somewhere inside (an item of `$somewhere`): the form offers documents; any type that can be searched is shown */
function somewhereOf(definitions: ModelDefinitions, pattern: unknown): SomewhereSearch | null {
  if (!isObject(pattern) || Object.keys(pattern).some((key) => key !== "type" && key !== "where")) return null;
  const { type, where } = pattern;
  if (typeof type !== "string" || !searchKindOf(definitions, type)) return null;
  const inner = where === undefined ? {} : where;
  if (!isObject(inner)) return null;
  const node = nodeOf(definitions, { type, root: false, alternative: false }, inner);
  return node && { node };
}

// (the rows of a node in the order `nodeWhere` writes them: the place of each kind of condition)
const FIELDS = 0;
const MENTIONS = 1;
const NOT_INCOMING = 2;
const INCOMING = 3;
const NOT_SOMEWHERE = 4;
const SOMEWHERE = 5;
const ANY_OF = 6;
const SPACES = 7;
const FLAGS = 8;

/** A condition of a node's `where`, read: what row of the form it is, and what it puts there */
type Read =
  | { at: typeof FIELDS; field: string; search: FieldSearch; key: string }
  | { at: typeof MENTIONS; search: FieldSearch; key: string }
  | { at: typeof NOT_INCOMING | typeof INCOMING; incoming: IncomingSearch[] }
  | { at: typeof NOT_SOMEWHERE | typeof SOMEWHERE; somewhere: SomewhereSearch[] }
  | { at: typeof ANY_OF; group: NodeSearch[] }
  | { at: typeof SPACES; spaces: string[] }
  | { at: typeof FLAGS; flag: string; value: boolean };

/** One condition of a node, read as the row it is, by its key; `null` if the form has no such row there */
function readPart(definitions: ModelDefinitions, place: Place, part: Where, rows: ExtraRow[]): Read | null {
  if (Object.keys(part).length !== 1) return null;
  const [key, value] = single(part);
  const fields = searchFieldsOf(definitions, place.type);
  const field = fields.find((each) => each.name === key);
  if (field) {
    const search = conditionOf(definitions, place, field, value);
    return search && { at: FIELDS, field: key, search, key };
  }
  switch (key) {
    case "$not": {
      if (!isObject(value)) return null;
      const body = flatParts(value);
      if (!body || body.length === 0) return null;
      const keys = new Set(body.map((each) => Object.keys(each)[0]!));
      if (keys.size !== 1) return null;
      const inner = [...keys][0]!;
      const negated = fields.find((each) => each.name === inner);
      if (negated) {
        const search = negatedOf(definitions, place, negated, body);
        return search && { at: FIELDS, field: inner, search, key };
      }
      if (inner === "$mentions" && rows.includes("mentions")) {
        const read = body.map((each) => mentionOf(each.$mentions));
        if (read.some((each) => !each)) return null;
        if (read.length === 1) return { at: MENTIONS, search: { ...read[0]!, not: true }, key };
        if (read.some((each) => each!.op !== "all")) return null;
        return { at: MENTIONS, search: { op: "all", not: true, entities: read.flatMap((each) => each!.entities!) }, key };
      }
      const patterns = body.length === 1 ? body[0]![inner] : undefined;
      if (!Array.isArray(patterns) || patterns.length !== 1) return null;
      if (inner === "$incoming" && rows.includes("incoming")) {
        const incoming = incomingOf(definitions, place, patterns[0]);
        return incoming && { at: NOT_INCOMING, incoming: [{ ...incoming, not: true }] };
      }
      if (inner === "$somewhere" && rows.includes("somewhere")) {
        const somewhere = somewhereOf(definitions, patterns[0]);
        return somewhere && { at: NOT_SOMEWHERE, somewhere: [{ ...somewhere, not: true }] };
      }
      return null;
    }
    case "$mentions": {
      const search = rows.includes("mentions") ? mentionOf(value) : null;
      return search && { at: MENTIONS, search, key };
    }
    case "$incoming": {
      if (!rows.includes("incoming") || !Array.isArray(value) || value.length === 0) return null;
      const incoming = value.map((pattern) => incomingOf(definitions, place, pattern));
      return incoming.every((each) => each) ? { at: INCOMING, incoming: incoming as IncomingSearch[] } : null;
    }
    case "$somewhere": {
      if (!rows.includes("somewhere") || !Array.isArray(value) || value.length === 0) return null;
      const somewhere = value.map((pattern) => somewhereOf(definitions, pattern));
      return somewhere.every((each) => each) ? { at: SOMEWHERE, somewhere: somewhere as SomewhereSearch[] } : null;
    }
    case "$any_of": {
      if (!rows.includes("anyOf") || !Array.isArray(value) || value.length === 0) return null;
      const group = value.map((each) => (isObject(each) ? alternativeOf(definitions, place, each) : null));
      return group.every((each) => each) ? { at: ANY_OF, group: group as NodeSearch[] } : null;
    }
    case "$spaces": {
      const choices = place.spaces ?? semanticSpacesOf(definitions);
      if (!rows.includes("spaces") || !isStrings(value) || value.length === 0) return null;
      return value.every((space) => choices.includes(space)) ? { at: SPACES, spaces: [...value] } : null;
    }
    default:
      if (place.root && !place.alternative && flagsOf(definitions, place.type).includes(key) && typeof value === "boolean") {
        return { at: FLAGS, flag: key, value };
      }
      return null;
  }
}

/** One alternative of a group (`$any_of`): a node of the same type, with nothing in it the form would leave out */
function alternativeOf(definitions: ModelDefinitions, place: Place, where: Where): NodeSearch | null {
  if (Object.keys(where).length === 0) return null;
  return nodeOf(definitions, { ...place, alternative: true }, where);
}

// (mentions that more of them can follow (all of several entities, each a condition), or not)
const mentionsKind = (search: FieldSearch): "any" | "all" => (search.op === "all" && !search.not ? "all" : "any");

/** The form of a node from its `where`; `null` if anything in it is not something the form makes */
function nodeOf(definitions: ModelDefinitions, place: Place, where: Where): NodeSearch | null {
  const parts = partsOf(where);
  if (!parts) return null;
  const rows = extraRowsOf(definitions, place.type, place);
  const reads: { read: Read; first: boolean }[] = [];
  // (a condition in `$all` that cannot be where it is in the order `nodeWhere` writes them (after one of a later row,
  // or apart from the rest of its field's) is an alternative of a group of one, which `nodeWhere` writes as itself;
  // one of several keys can only be that)
  let reached = FIELDS;
  const fieldsLeft = new Set<string>();
  let lastField: string | undefined;
  let mentions: "any" | "all" | undefined;
  for (const part of parts) {
    const read = Object.keys(part.where).length === 1 ? readPart(definitions, place, part.where, rows) : null;
    if (part.first) {
      if (!read) return null;
      reads.push({ read, first: true });
      if (read.at === MENTIONS) mentions = mentionsKind(read.search);
      continue;
    }
    let inOrder = read !== null && read.at >= reached;
    if (read?.at === FIELDS) {
      inOrder = inOrder && !fieldsLeft.has(read.field);
      if (inOrder && lastField !== undefined && lastField !== read.field) fieldsLeft.add(lastField);
    }
    // (a document's mentions are one condition: more than one of them is all of several entities)
    if (read?.at === MENTIONS && mentions !== undefined) {
      inOrder = inOrder && mentions === "all" && mentionsKind(read.search) === "all";
    }
    if (read?.at === INCOMING || read?.at === SOMEWHERE || read?.at === SPACES) {
      inOrder = inOrder && !reads.some((each) => each.read.at === read.at);
    }
    if (!inOrder && rows.includes("anyOf")) {
      const alone = alternativeOf(definitions, place, part.where);
      if (alone) {
        reads.push({ read: { at: ANY_OF, group: [alone] }, first: false });
        reached = ANY_OF;
        continue;
      }
    }
    if (!read) return null;
    reads.push({ read, first: false });
    reached = Math.max(reached, read.at);
    if (read.at === FIELDS) lastField = read.field;
    if (read.at === MENTIONS && mentions === undefined) mentions = mentionsKind(read.search);
  }
  return assemble(place.type, reads);
}

/** The node from its conditions, read: each row in the order the form writes them, so that it compiles as it was */
function assemble(type: string, reads: { read: Read; first: boolean }[]): NodeSearch {
  const node: NodeSearch = { type };
  // (the fields: the one that has the first `$not`, then those with no condition in `$all`, then the rest in their
  // order there; on each, its conditions not in `$all`, then those that are)
  const byField = new Map<string, { first: FieldSearch[]; rest: FieldSearch[]; owner: boolean }>();
  for (const { read, first } of reads) {
    if (read.at !== FIELDS) continue;
    const entry = byField.get(read.field) ?? { first: [], rest: [], owner: false };
    (first ? entry.first : entry.rest).push(read.search);
    if (first && read.key === "$not") entry.owner = true;
    byField.set(read.field, entry);
  }
  const names = [...byField.keys()];
  const order = [
    ...names.filter((name) => byField.get(name)!.owner && byField.get(name)!.rest.length === 0),
    ...names.filter((name) => !byField.get(name)!.owner && byField.get(name)!.rest.length === 0),
    ...reads.flatMap(({ read, first }) => (read.at === FIELDS && !first ? [read.field] : [])),
  ].filter((name, at, all) => all.indexOf(name) === at);
  if (order.length > 0) {
    node.fields = {};
    for (const name of order) {
      const entry = byField.get(name)!;
      const [main, ...and] = [...entry.first, ...entry.rest];
      node.fields[name] = and.length > 0 ? { ...main!, and } : main!;
    }
  }
  const mentions = reads.filter(({ read }) => read.at === MENTIONS).map(({ read }) => (read as { search: FieldSearch }).search);
  if (mentions.length > 0) {
    const [main, ...more] = mentions;
    node.mentions = more.length > 0 ? { ...main!, entities: mentions.flatMap((each) => each.entities ?? []) } : main!;
  }
  const incoming = [NOT_INCOMING, INCOMING].flatMap((at) =>
    reads.flatMap(({ read }) => (read.at === at ? (read as { incoming: IncomingSearch[] }).incoming : [])),
  );
  if (incoming.length > 0) node.incoming = incoming;
  const somewhere = [NOT_SOMEWHERE, SOMEWHERE].flatMap((at) =>
    reads.flatMap(({ read }) => (read.at === at ? (read as { somewhere: SomewhereSearch[] }).somewhere : [])),
  );
  if (somewhere.length > 0) node.somewhere = somewhere;
  // (the groups: those not in `$all` first, then those in it, in their order)
  const groups = [true, false].flatMap((wanted) =>
    reads.flatMap(({ read, first }) => (read.at === ANY_OF && first === wanted ? [read.group] : [])),
  );
  if (groups.length > 0) node.anyOf = groups;
  const spaces = reads.find(({ read }) => read.at === SPACES)?.read as { spaces: string[] } | undefined;
  if (spaces) node.spaces = spaces.spaces;
  const flags = reads.filter(({ read }) => read.at === FLAGS).map(({ read }) => read as { flag: string; value: boolean });
  if (flags.length > 0) node.flags = Object.fromEntries(flags.map((each) => [each.flag, each.value]));
  return node;
}

// --- what a `where` means, to check what was read ---------------------------------------------------------------------

/** A `where` as what it means: its conditions, each written one way, in a sorted list (the order of an `$all` and the
 * placing of a condition in it or not change nothing) */
function meaning(where: Where): string[] | null {
  const parts = flatParts(where);
  if (!parts) return null;
  const said: string[] = [];
  for (const part of parts) {
    const [key, value] = single(part);
    const one = conditionMeaning(key, value);
    if (one === null) return null;
    said.push(one);
  }
  return said.sort();
}

function conditionMeaning(key: string, value: unknown): string | null {
  if (key === "$not") {
    const inner = isObject(value) ? meaning(value) : null;
    return inner && JSON.stringify(["$not", inner]);
  }
  if (key === "$any_of") {
    if (!Array.isArray(value)) return null;
    const each = value.map((one) => (isObject(one) ? meaning(one) : null));
    return each.every((one) => one) ? JSON.stringify(["$any_of", each]) : null;
  }
  return JSON.stringify([key, valueMeaning(value)]);
}

// (a value as JSON with its keys sorted, and a pattern's `where` (of a relation, `$incoming`, `$somewhere`) by what it means)
function valueMeaning(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(valueMeaning);
  if (!isObject(value)) return value;
  const out: Record<string, unknown> = {};
  for (const key of Object.keys(value).sort()) {
    if (key === "where" && isObject(value.where)) {
      if (Object.keys(value.where).length > 0) out.where = meaning(value.where);
    } else out[key] = valueMeaning(value[key]);
  }
  return out;
}

/**
 * The search form that stands for `where` (what `compileSearch` makes, and a stored pattern holds), for a search of
 * `type`: what `compileSearch` turns into the same `where`. `null` if the form cannot show it all: an operator or a key
 * the form does not make, a field the type does not have (or cannot be searched by), a `through` with conditions, a
 * condition on an edge. An entity picked has its id only, and no label (`label: ""`), and a type only where its
 * relation can point at one type: `withLabels` fills them in. The order of results is not part of a `where`, and is
 * not in the form.
 */
export function whereToForm(definitions: ModelDefinitions, type: string, where: Record<string, unknown> | null | undefined): NodeSearch | null {
  if (!searchKindOf(definitions, type)) return null;
  if (where === null || where === undefined) return { type };
  if (!isObject(where)) return null;
  const form = nodeOf(definitions, { type, root: true, alternative: false }, where);
  if (!form) return null;
  // (what the form stands for means what was given, or something was not read as it is: then the form cannot show it)
  const given = meaning(where);
  return given && JSON.stringify(meaning(nodeWhere(form))) === JSON.stringify(given) ? form : null;
}

/** Every entity picked in a form (fields, mentions, at any depth), each id once: what `/api/references` is asked about */
export function pickedIds(form: NodeSearch): string[] {
  const ids = new Set<string>();
  const walk = (node: NodeSearch) => {
    for (const search of Object.values(node.fields ?? {})) fieldWalk(search);
    if (node.mentions) fieldWalk(node.mentions);
    for (const each of node.incoming ?? []) walk(each.node);
    for (const each of node.somewhere ?? []) walk(each.node);
    for (const group of node.anyOf ?? []) group.forEach(walk);
  };
  const fieldWalk = (search: FieldSearch) => {
    for (const entity of search.entities ?? []) ids.add(entity.id);
    if (search.node) walk(search.node);
    (search.and ?? []).forEach(fieldWalk);
  };
  walk(form);
  return [...ids];
}

/**
 * The form with the type and label of each entity picked, from what `/api/references` says of them (`found`). One it
 * does not find keeps `label: ""`: the pattern names an entity that has been deleted. A new form; `form` is not changed.
 */
export function withLabels(form: NodeSearch, found: { id: string; type: string; label: string }[]): NodeSearch {
  const there = new Map(found.map((each) => [each.id, each]));
  const entity = (picked: PickedEntity): PickedEntity => {
    const summary = there.get(picked.id);
    return summary ? { type: summary.type, id: picked.id, label: summary.label } : { ...picked, label: "" };
  };
  const field = (search: FieldSearch): FieldSearch => {
    const out: FieldSearch = { ...search };
    if (search.entities) out.entities = search.entities.map(entity);
    if (search.node) out.node = node(search.node);
    if (search.and) out.and = search.and.map(field);
    return out;
  };
  const node = (given: NodeSearch): NodeSearch => {
    const out: NodeSearch = { ...given };
    if (given.fields) out.fields = Object.fromEntries(Object.entries(given.fields).map(([name, search]) => [name, field(search)]));
    if (given.mentions) out.mentions = field(given.mentions);
    if (given.incoming) out.incoming = given.incoming.map((each) => ({ ...each, node: node(each.node) }));
    if (given.somewhere) out.somewhere = given.somewhere.map((each) => ({ ...each, node: node(each.node) }));
    if (given.anyOf) out.anyOf = given.anyOf.map((group) => group.map(node));
    return out;
  };
  return node(form);
}
