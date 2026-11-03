/**
 * The search form of a list: what it holds (a `NodeSearch`, kept in the address of the list as JSON), the fields
 * and operators it offers for a type (from the exported `searchPatterns`), and the pattern of `POST /api/search` it
 * stands for (`compileSearch`). See docs/search-form.md.
 */
import type { FieldType, ModelDefinitions, RelationOption, SearchFieldDefinition } from "../types";

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
  /** A relation: the wrappers (semantic spaces, conjunctions, reified relations) it must pass through */
  through?: string[];
  /** More conditions on the same field, each of which must hold too */
  and?: FieldSearch[];
}

/** A document of some type anywhere in the document searched (`$somewhere`) */
export interface SomewhereSearch {
  not?: boolean;
  node: NodeSearch;
}

/** What the results are ordered by: a field (`date.sort_day` for one of an embedded object) */
export interface OrderSearch {
  field: string;
  direction?: "asc" | "desc";
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
  /** Documents (the root only): documents of other types that are somewhere in them */
  somewhere?: SomewhereSearch[];
  /** Groups of alternatives: of each group, at least one has to hold (`$any_of`) */
  anyOf?: NodeSearch[][];
  /** A document that a relation points at: the semantic spaces it is inside (`$spaces`) */
  spaces?: string[];
  /** The root: what the results are ordered by */
  order?: OrderSearch[];
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

const WRAPPER_KINDS = new Set(["semanticSpace", "conjunction", "reifiedRelation", "reifiedRelationDocument"]);

/**
 * The wrappers a relation of `type` can pass through on the way to what it points at (`Negative`, a conjunction, a
 * reified relation), by the options of the model's field: what `through` can name
 */
export function wrappersOf(definitions: ModelDefinitions, type: string, field: string): string[] {
  const found = new Set<string>();
  const walk = (options: RelationOption[]) => {
    for (const option of options) {
      if (!WRAPPER_KINDS.has(option.kind) || !("type" in option)) continue;
      found.add(option.type);
      if ("params" in option) for (const parameter of Object.values(option.params)) walk(parameter.options);
    }
  };
  const definition = definitions.models[type]?.fields.find((each) => each.name === field);
  if (definition?.kind === "relation") walk(definition.options);
  return [...found].sort();
}

/** The semantic spaces of the project (what `$spaces` can name) */
export function semanticSpacesOf(definitions: ModelDefinitions): string[] {
  return Object.values(definitions.models)
    .filter((model) => model.kind === "SemanticSpace" && !model.abstract)
    .map((model) => model.name)
    .sort();
}

/** What a search of `type` can be ordered by (`label`, a field, `date.sort_day` for one of an embedded object) */
export function orderFieldsOf(definitions: ModelDefinitions, type: string): string[] {
  return definitions.searchPatterns?.[type]?.orderBy ?? [];
}

/** The types of document that can be searched for inside a document (`$somewhere`) */
export function documentTypesOf(definitions: ModelDefinitions): string[] {
  return Object.entries(definitions.searchPatterns ?? {})
    .filter(([, pattern]) => pattern.kind === "document")
    .map(([type]) => type)
    .sort();
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

/** The conditions of one field, with those `and`-ed to it (none, if none is complete) */
function fieldParts(name: string, search: FieldSearch): Where[] {
  return [search, ...(search.and ?? [])].flatMap((each) => negated(conditionParts(name, each), each.not));
}

/** The conditions of one condition on a field (none, if it is not complete) */
function conditionParts(name: string, search: FieldSearch): Where[] {
  const through = (search.through ?? []).length > 0 ? { through: search.through } : {};
  const on = (condition: unknown): Where => ({
    [name]: typeof condition === "object" && condition !== null ? { ...(condition as Where), ...through } : condition,
  });
  // (a relation that must pass through wrappers, but has nothing else yet: one that does)
  const onlyThrough = (): Where[] => ("through" in through ? [{ [name]: through }] : []);
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
      return [{ [name]: { exists: false } }];
    case "any": {
      const ids = (search.entities ?? []).map((entity) => entity.id);
      return ids.length > 0 ? [on({ is_any: ids })] : onlyThrough();
    }
    case "all": {
      const all = (search.entities ?? []).map((entity) => on({ is: entity.id }));
      return all.length > 0 ? all : onlyThrough();
    }
    case "match": {
      if (!search.node?.type) return onlyThrough();
      const where = nodeWhere(search.node);
      return [on(Object.keys(where).length > 0 ? { type: search.node.type, where } : { type: search.node.type })];
    }
  }
}

/** The `where` of a node of the form (`{}`: it has no condition) */
export function nodeWhere(node: NodeSearch): Where {
  const parts: Where[] = [];
  for (const [name, search] of Object.entries(node.fields ?? {})) {
    parts.push(...fieldParts(name, search));
  }
  if (node.mentions) {
    parts.push(...fieldParts("$mentions", node.mentions));
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
  const contained: Where[] = [];
  for (const somewhere of node.somewhere ?? []) {
    if (!somewhere.node?.type) continue;
    const where = nodeWhere(somewhere.node);
    const pattern: Where = { type: somewhere.node.type };
    if (Object.keys(where).length > 0) pattern.where = where;
    if (somewhere.not) parts.push({ $not: { $somewhere: [pattern] } });
    else contained.push(pattern);
  }
  if (contained.length > 0) parts.push({ $somewhere: contained });
  for (const group of node.anyOf ?? []) {
    // (an alternative with nothing in it is left out: it would let everything through)
    const alternatives = group.map(nodeWhere).filter((where) => Object.keys(where).length > 0);
    if (alternatives.length === 1) parts.push(alternatives[0]!);
    else if (alternatives.length > 1) parts.push({ $any_of: alternatives });
  }
  if ((node.spaces ?? []).length > 0) parts.push({ $spaces: node.spaces });
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

/** What the results are to be ordered by (the fields chosen, in order), as the API takes it */
export function compileOrder(form: NodeSearch | undefined): { field: string; direction: "asc" | "desc" }[] {
  return (form?.order ?? [])
    .filter((order) => order.field)
    .map((order) => ({ field: order.field, direction: order.direction ?? "asc" }));
}

/**
 * The body of `POST /api/search` that the form stands for (without the type and the page): its `where` (with the words
 * of `q`) and its order; `undefined` if it has neither a condition nor an order (the list is then the ordinary one)
 */
export function compileRequest(
  form: NodeSearch | undefined,
  q = "",
): { where: Where; orderBy?: { field: string; direction: "asc" | "desc" }[] } | undefined {
  const order = compileOrder(form);
  const where = compileSearch(form, q);
  if (!where && order.length === 0) return undefined;
  const words = q.split(/\s+/).filter((word) => word !== "");
  const request: { where: Where; orderBy?: typeof order } = {
    where: where ?? combineWhere(words.map((word) => ({ label: { contains: word } }))),
  };
  if (order.length > 0) request.orderBy = order;
  return request;
}

/** The form as it is kept in the address (`undefined`: none, or one with nothing in it) */
export function encodeSearchForm(form: NodeSearch | undefined): string | undefined {
  if (!form) return undefined;
  const empty =
    Object.keys(form.fields ?? {}).length === 0 &&
    !form.mentions &&
    (form.incoming ?? []).length === 0 &&
    (form.somewhere ?? []).length === 0 &&
    (form.anyOf ?? []).length === 0 &&
    (form.order ?? []).length === 0;
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
