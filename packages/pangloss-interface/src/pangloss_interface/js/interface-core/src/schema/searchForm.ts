/**
 * The search form of a list: what it holds (a `NodeSearch`, kept in the address of the list as JSON), the fields
 * and operators it offers for a type (from the exported `searchPatterns`), and the pattern of `POST /api/search` it
 * stands for (`compileSearch`). See docs/search-form.md.
 */
import type { FieldType, ModelDefinitions, SearchFieldDefinition } from "../types";

/** An entity picked in the form: its label is kept so the form can be shown again from the address */
export interface PickedEntity {
  type: string;
  id: string;
  label: string;
}

export type SearchOperator =
  | "contains"
  | "starts_with"
  | "eq"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "between"
  | "in"
  | "any"
  | "all"
  | "match"
  | "exists"
  | "missing";

/** The condition on one field (or on what a document mentions) */
export interface FieldSearch {
  op: SearchOperator;
  /** It is what does not hold that is wanted */
  not?: boolean;
  /** A text, a number, a date; `[from, to]` for `between`; the values chosen for `in` */
  value?: unknown;
  /** For `any` and `all` */
  entities?: PickedEntity[];
  /** For `match`: what the field points at (its `type` is chosen from the field's targets) */
  node?: NodeSearch;
}

/** Something that refers to the entity searched: a node of `node.type`, by its relation `field` (or any) */
export interface IncomingSearch {
  field?: string;
  not?: boolean;
  node: NodeSearch;
}

/** The form for a node: the root (the type of the list), or what a relation points at */
export interface NodeSearch {
  type: string;
  fields?: Record<string, FieldSearch>;
  /** Documents (the root only): entities anywhere in the document (`any` or `all`) */
  mentions?: FieldSearch;
  /** Entities: what refers to them */
  incoming?: IncomingSearch[];
}

export type SearchOperators = SearchFieldDefinition["operators"];

/** A field the form offers for a type: its name, its operators, the type of its values, what it can point at */
export interface SearchField {
  name: string;
  operators: SearchOperators;
  value?: FieldType;
  targets?: string[];
}

/** What the search of a type is about: a document, an entity, an embedded object (or nothing: no pattern) */
export function searchKindOf(definitions: ModelDefinitions, type: string) {
  return definitions.searchPatterns?.[type]?.kind;
}

/**
 * The fields of a type that can be searched, in the order of the model: `label` first (but for an embedded object,
 * which has none), then those of its search pattern.
 */
export function searchFieldsOf(definitions: ModelDefinitions, type: string): SearchField[] {
  const pattern = definitions.searchPatterns?.[type];
  if (!pattern) return [];
  const label: SearchField[] =
    pattern.kind === "embedded" ? [] : [{ name: "label", operators: "text", value: { type: "str" } }];
  return [
    ...label,
    ...Object.entries(pattern.fields).map(([name, field]) => ({ name, ...field })),
  ];
}

/** Whether every target of a relation is an entity (they are then picked, rather than described) */
export function targetsEntities(definitions: ModelDefinitions, field: SearchField): boolean {
  const targets = field.targets ?? [];
  return targets.length > 0 && targets.every((type) => searchKindOf(definitions, type) === "entity");
}

/** The operators a field offers, the first being the one it starts with */
export function operatorsOf(definitions: ModelDefinitions, field: SearchField): SearchOperator[] {
  switch (field.operators) {
    case "text":
      return ["contains", "starts_with", "eq", "exists", "missing"];
    case "compare":
      return ["eq", "gt", "gte", "lt", "lte", "between", "exists", "missing"];
    case "choice":
      return ["in", "exists", "missing"];
    case "items":
      return ["contains", "exists", "missing"];
    case "relation":
      return targetsEntities(definitions, field)
        ? ["any", "all", "match", "exists", "missing"]
        : ["match", "exists", "missing"];
  }
}

/**
 * The things that can refer to an entity of `type` (from the model's `incoming`): a type and its relation, each once,
 * of those types that can be searched (not an embedded object: its relation is not one of a document's)
 */
export function incomingSourcesOf(
  definitions: ModelDefinitions,
  type: string,
): { model: string; field: string }[] {
  const seen = new Set<string>();
  const found: { model: string; field: string }[] = [];
  for (const incoming of definitions.models[type]?.incoming ?? []) {
    for (const source of incoming.sources) {
      const kind = searchKindOf(definitions, source.model);
      if (kind !== "document" && kind !== "entity") continue;
      const key = `${source.model}.${source.field}`;
      if (seen.has(key)) continue;
      seen.add(key);
      found.push({ model: source.model, field: source.field });
    }
  }
  return found.sort((a, b) => a.model.localeCompare(b.model) || a.field.localeCompare(b.field));
}

type Where = Record<string, unknown>;

const given = (value: unknown) =>
  value !== undefined && value !== null && !(typeof value === "string" && value.trim() === "");

/**
 * Puts conditions together into one `where`: each key once, and what would be a key twice (two conditions on the same
 * field, or two `$not`s) in an `$all`
 */
export function combineWhere(parts: Where[]): Where {
  const where: Where = {};
  const rest: Where[] = [];
  for (const part of parts) {
    if (Object.keys(part).some((key) => key in where)) rest.push(part);
    else Object.assign(where, part);
  }
  if (rest.length > 0) where.$all = [...((where.$all as Where[] | undefined) ?? []), ...rest];
  return where;
}

const negated = (parts: Where[], not: boolean | undefined): Where[] =>
  not && parts.length > 0 ? [{ $not: combineWhere(parts) }] : parts;

/** The conditions of one field (none, if it is not complete) */
function fieldParts(name: string, search: FieldSearch): Where[] {
  const on = (condition: unknown): Where => ({ [name]: condition });
  const value = search.value;
  switch (search.op) {
    case "contains":
    case "starts_with":
    case "eq":
    case "gt":
    case "gte":
    case "lt":
    case "lte":
      return given(value) ? [on({ [search.op]: value })] : [];
    case "between": {
      const [from, to] = Array.isArray(value) ? value : [];
      if (given(from) && given(to)) return [on({ between: [from, to] })];
      if (given(from)) return [on({ gte: from })];
      if (given(to)) return [on({ lte: to })];
      return [];
    }
    case "in":
      return Array.isArray(value) && value.length > 0 ? [on({ in: value })] : [];
    case "exists":
      return [on({ exists: true })];
    case "missing":
      return [on({ exists: false })];
    case "any": {
      const ids = (search.entities ?? []).map((entity) => entity.id);
      return ids.length > 0 ? [on({ is_any: ids })] : [];
    }
    case "all":
      return (search.entities ?? []).map((entity) => on({ is: entity.id }));
    case "match": {
      if (!search.node?.type) return [];
      const where = nodeWhere(search.node);
      return [on(Object.keys(where).length > 0 ? { type: search.node.type, where } : { type: search.node.type })];
    }
  }
}

/** The `where` of a node of the form (`{}`: it has no condition) */
export function nodeWhere(node: NodeSearch): Where {
  const parts: Where[] = [];
  for (const [name, search] of Object.entries(node.fields ?? {})) {
    parts.push(...negated(fieldParts(name, search), search.not));
  }
  if (node.mentions) {
    const mentioned = fieldParts("$mentions", node.mentions);
    parts.push(...negated(mentioned, node.mentions.not));
  }
  const referring: Where[] = [];
  for (const incoming of node.incoming ?? []) {
    if (!incoming.node?.type) continue;
    const where = nodeWhere(incoming.node);
    const pattern: Where = { type: incoming.node.type };
    if (incoming.field) pattern.field = incoming.field;
    if (Object.keys(where).length > 0) pattern.where = where;
    if (incoming.not) parts.push({ $not: { $incoming: [pattern] } });
    else referring.push(pattern);
  }
  if (referring.length > 0) parts.push({ $incoming: referring });
  return combineWhere(parts);
}

/**
 * The `where` of `POST /api/search` that the form stands for, with each word of `q` (the text box) a condition on the
 * label; `undefined` if the form has no condition (then the list is the ordinary one, which searches the text index)
 */
export function compileSearch(form: NodeSearch | undefined, q = ""): Where | undefined {
  if (!form) return undefined;
  const where = nodeWhere(form);
  if (Object.keys(where).length === 0) return undefined;
  const words = q.split(/\s+/).filter((word) => word !== "");
  return combineWhere([where, ...words.map((word) => ({ label: { contains: word } }))]);
}

/** The form as it is kept in the address (`undefined`: none, or one with nothing in it) */
export function encodeSearchForm(form: NodeSearch | undefined): string | undefined {
  if (!form) return undefined;
  const empty =
    Object.keys(form.fields ?? {}).length === 0 && !form.mentions && (form.incoming ?? []).length === 0;
  return empty ? undefined : JSON.stringify(form);
}

/** The form from the address (`undefined` if there is none, it cannot be read, or it is of another type) */
export function decodeSearchForm(text: string | undefined, type: string): NodeSearch | undefined {
  if (!text) return undefined;
  try {
    const form = JSON.parse(text) as unknown;
    if (typeof form !== "object" || form === null || Array.isArray(form)) return undefined;
    return (form as NodeSearch).type === type ? (form as NodeSearch) : undefined;
  } catch {
    return undefined;
  }
}
