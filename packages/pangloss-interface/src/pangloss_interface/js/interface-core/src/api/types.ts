/**
 * The shapes the API answers with. The JSON is `camelCase`.
 */
import type { Creator } from "../types";
import type { DegreeStep } from "../types/models";

/** A page of a list of things, as every list of the API is */
export interface Page<T> {
  results: T[];
  count: number;
  page: number;
  pageSize: number;
  nextPage: number | null;
  previousPage: number | null;
  /** True if a word of the search had more hits than were looked at: there are more results than `count` */
  truncated?: boolean;
  /** How many things refer to each item of the page, by id, if it was asked for (`useCounts`) */
  useCounts?: Record<string, number> | null;
}

/**
 * A node that another is nested in (`meta.path`: `pangloss_models.context`). A path runs from the head of the
 * document down to what holds the node, so its first entry is the head; the node itself is never in it.
 */
export interface PathEntry {
  kind: "document" | "entity" | "space" | "reified" | "conjunction" | "embedded";
  type: string;
  id: string;
  /** The relation of this node through which the next of the path, or the node itself, is held (its Python name) */
  field: string;
  /**
   * (of a space, and only where one was entered on it: its field marked `Degree()`) how far what it holds is taken
   * to be so. Absent otherwise: the class's default (`ModelDefinition.degree`) is not written here
   */
  degree?: DegreeStep;
}

/** Whether an item can be deleted (`checkDeletable`), and if not why */
export interface Deletable {
  deletable: boolean;
  /** (if not) why, in a sentence */
  reason: string | null;
  /** (an entity that is referred to) up to ten of what refers to it */
  referencedBy: { id: string; type: string; label: string }[];
  referenceCount: number;
}

/** A Document or Entity in a list: enough to show and link to it */
export interface Summary {
  id: string;
  type: string;
  label: string;
  /** (the list has only these parts of the meta of an item) */
  meta?: {
    /** The types of the semantic spaces it is in, outermost first (those of its path) */
    semanticSpaces?: string[];
    /** (of an item that is inside another document: the nodes it is nested in, from the head down) */
    path?: PathEntry[] | null;
    isHeadNode?: boolean;
    /** (of an item that is inside another document: the document it is in) */
    headNodeType?: string | null;
    headNodeId?: string | null;
    /** (of a document that is reviewed, or inside one: the status of the head) */
    reviewStatus?: string | null;
  };
}

export interface ItemMeta {
  version: number;
  published: boolean;
  reviewStatus: string | null;
  /** Those who made it, in order: people, then a toolchain if one did */
  createdBy: Creator[];
  /** The admin who wrote it in the name of those, if it was not written by its creator */
  uploadedBy?: string | null;
  createdWhen: string;
  updatedBy: string | null;
  updatedWhen: string | null;
  /** The label of the head node (a head node's is its own) */
  headNodeLabel?: string | null;
  /** The types of the semantic spaces it is in, outermost first (those of its path) */
  semanticSpaces?: string[];
  /** The nodes it is nested in, from the head down (empty for a head; absent in data stored before the path) */
  path?: PathEntry[] | null;
  [key: string]: unknown;
}

/**
 * One Document or Entity in full. What else it has depends on its model (see
 * `ModelDefinition.fields`), so the rest is not typed.
 */
export interface HeadView {
  id: string;
  type: string;
  label?: string;
  meta: ItemMeta;
  /**
   * An entity read with a limit on what refers to it (`getItem` with `incomingLimit`): how many there are in each
   * incoming field, by its key (the field itself has the first of them; `getIncoming` reads the rest). `null`: read
   * with none of it (`incomingLimit: 0`), which `getIncomingFields` reads apart. Absent: read whole
   */
  incomingCounts?: Record<string, number> | null;
  [field: string]: unknown;
}

/** What refers to an entity, the first of each incoming field at once (`getIncomingFields`) */
export interface IncomingFields {
  limit: number;
  /** How many there are in each incoming field that has any, by its key */
  counts: Record<string, number>;
  /** The first `limit` of each, by its key, as they are in that field of the entity */
  fields: Record<string, Record<string, unknown>[]>;
}

/** Some of what refers to an entity by one relation (`getIncoming`) */
export interface IncomingPage {
  /** The key of the incoming field */
  field: string;
  /** How many there are in all */
  count: number;
  page: number;
  pageSize: number;
  /** As they are in that field of the entity */
  results: Record<string, unknown>[];
}

/** The body of a create or an update: the fields of the model, as the edit view has them */
export type ItemBody = Record<string, unknown>;

export interface ListParams {
  /** Searches the labels */
  q?: string;
  /** Searches more */
  deep?: boolean;
  /** Only what something refers to */
  usedOnly?: boolean;
  /** With how many things refer to each item of the page */
  useCounts?: boolean;
  page?: number;
  pageSize?: number;
}

export interface AutocompleteParams {
  /** What was typed: without it, the entities of the types most used */
  q?: string;
  /** The entity types to look in (all, if none) */
  types?: string[];
  page?: number;
  pageSize?: number;
}

/** The keys of a `where` that are not fields (`SearchKey` in `pangloss_models.search`) */
export type SearchKey =
  | "$all"
  | "$any_of"
  | "$not"
  | "$any"
  | "$mentions"
  | "$somewhere"
  | "$incoming"
  | "$spaces";

/**
 * The conditions of a field of a search pattern, one for each kind of field (the classes of
 * `pangloss_models.search_where`: `Text`, `Compare`, `Choice`, `Items`, `Rel`, `AnyRel`). The project's
 * own `LetterWhere` and the like, in the generated models, are made of these.
 */
export interface TextCondition {
  eq?: string | null;
  ne?: string | null;
  in?: string[];
  exists?: boolean;
  contains?: string;
  starts_with?: string;
}

/** A number, a `Decimal`, a date or a datetime (dates as ISO strings) */
export interface CompareCondition<T> {
  eq?: T | null;
  ne?: T | null;
  in?: T[];
  exists?: boolean;
  gt?: T;
  gte?: T;
  lt?: T;
  lte?: T;
  between?: [T, T];
}

/** A `bool`, or an enum (by its values) */
export interface ChoiceCondition<T> {
  eq?: T | null;
  ne?: T | null;
  in?: T[];
  exists?: boolean;
}

/** A list of literals */
export interface ItemsCondition<T> {
  contains?: T;
  contains_any?: T[];
  contains_all?: T[];
  exists?: boolean;
}

/** What an edge has to be: the name of its edge model, and a `where` of that model's fields */
export interface EdgeCondition {
  type: string;
  where?: Record<string, unknown>;
}

/** A wrapper a relation passes through, of which more is asked: its own values, and the edge that leaves it */
export interface ThroughStep {
  type: string;
  where?: Record<string, unknown>;
  edge?: EdgeCondition;
}

/** A place of the way of a relation: an edge model (`where`: its properties) or a wrapper (`where`: its own values and relations) */
export interface ViaItem {
  type: string;
  where?: Record<string, unknown>;
}

/** A relation, or an embedded object: by id, whether it has any, the wrappers it passes through (by name, or with
 * what is asked of one), what the edge that reaches what it points at has to be, and the edges and wrappers its way
 * meets, in order (`via`) */
export interface RelationCondition {
  is?: string;
  is_any?: string[];
  exists?: boolean;
  through?: (string | ThroughStep)[];
  edge?: EdgeCondition;
  via?: ViaItem[];
}

/** `$any` and `$mentions`: any relation (`contains` and `starts_with` are of the label), and a pattern */
export interface AnyRelationCondition extends RelationCondition {
  contains?: string;
  starts_with?: string;
  type?: string;
  where?: Record<string, unknown>;
}

/** A pattern for a node of another type: in `$somewhere`, and (with `field`, `through` and `via`, the way from it to
 * the entity) in `$incoming` */
export interface NodePattern {
  type: string;
  where?: Record<string, unknown>;
  field?: string;
  through?: string[];
  via?: ViaItem[];
}

export interface SearchOrder<F extends string = string> {
  field: F;
  direction?: "asc" | "desc";
}

/** A search pattern; see implementation_docs/structured-search.md. (`SearchOf<"Letter">`, in the generated models, is one typed by the model.) */
export interface SearchPattern {
  type: string;
  where?: Record<string, unknown>;
  orderBy?: SearchOrder[];
  /** The wrappers (semantic spaces, conjunctions, reified relations) no relation of the search passes through */
  excludeWrappers?: string[];
  /** Only what something refers to */
  usedOnly?: boolean;
  /** With how many things refer to each item of the page */
  useCounts?: boolean;
  page?: number;
  pageSize?: number;
}

export interface User {
  username: string;
  email: string;
  fullName: string | null;
  admin: boolean;
  [key: string]: unknown;
}
