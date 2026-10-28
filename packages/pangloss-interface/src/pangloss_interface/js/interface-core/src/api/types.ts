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
  [field: string]: unknown;
}

export interface ListParams {
  /** Searches the labels */
  q?: string;
  /** Searches more */
  deep?: boolean;
  page?: number;
  pageSize?: number;
}

export interface AutocompleteParams {
  q: string;
  /** The entity types to look in (all, if none) */
  types?: string[];
  page?: number;
  pageSize?: number;
}

/** A search pattern; see docs/structured-search.md */
export interface SearchPattern {
  type: string;
  where?: Record<string, unknown>;
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
