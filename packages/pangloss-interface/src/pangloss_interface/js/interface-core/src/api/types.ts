/**
 * The shapes the API answers with. The JSON is `camelCase`.
 */

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

/** A Document or Entity in a list: enough to show and link to it */
/**
 * Where an item is, in the semantic spaces of its document: one entry for each space it is
 * in, outermost first (`Negative`, then `Subjunctive`), and `#rootcontext` for a run of
 * documents that are not in a space. `contents` are the documents on the path.
 */
export interface ContextLabel {
  type: string;
  id?: string;
  contents?: ContextLabel[];
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

export interface Summary {
  id: string;
  type: string;
  label: string;
  /** (the list has only these parts of the meta of an item) */
  meta?: {
    semanticSpaces?: string[];
    contextLabels?: ContextLabel[] | null;
    isHeadNode?: boolean;
    /** (of an item that is inside another document: the document it is in) */
    headNodeType?: string | null;
    headNodeId?: string | null;
  };
}

export interface ItemMeta {
  version: number;
  published: boolean;
  reviewStatus: string | null;
  createdBy: string | null;
  createdWhen: string;
  updatedBy: string | null;
  updatedWhen: string | null;
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

/** A relation, or an embedded object: by id, whether it has any, the wrappers it passes through */
export interface RelationCondition {
  is?: string;
  is_any?: string[];
  exists?: boolean;
  through?: string[];
}

/** `$any` and `$mentions`: any relation (`contains` and `starts_with` are of the label), and a pattern */
export interface AnyRelationCondition extends RelationCondition {
  contains?: string;
  starts_with?: string;
  type?: string;
  where?: Record<string, unknown>;
}

/** A pattern for a node of another type: in `$somewhere`, and (with `field`) in `$incoming` */
export interface NodePattern {
  type: string;
  where?: Record<string, unknown>;
  field?: string;
  through?: string[];
}

export interface SearchOrder<F extends string = string> {
  field: F;
  direction?: "asc" | "desc";
}

/** A search pattern; see docs/structured-search.md. (`SearchOf<"Letter">`, in the generated models, is one typed by the model.) */
export interface SearchPattern {
  type: string;
  where?: Record<string, unknown>;
  orderBy?: SearchOrder[];
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
