import type { ApiClient, QueryParams } from "@pangloss/interface-core";

// What the routes of pangloss_vectors send (pangloss_vectors/api.py), and the one route of pangloss_admin this module
// calls (it may not import another module's files: its own small call)

/** "excluded": the item's class has no vectors (`VectorsMeta(include=False)`), and never will */
export type SimilarStatus = "ok" | "pending" | "rebuild_due" | "excluded";

/** One item found: its reference view, as a list gives it, with the cosine of the two vectors */
export interface SimilarResult {
  id: string;
  type: string;
  label: string;
  similarity: number;
  meta?: {
    isHeadNode?: boolean;
    headNodeId?: string | null;
    headNodeType?: string | null;
  } | null;
}

export interface SimilarAnswer {
  status: SimilarStatus;
  /** Nearest first */
  results: SimilarResult[];
  /** The names of the profiles, `default` first */
  profiles: string[];
  /** The classes a search can be narrowed to (`VectorsMeta(searchable=True)`) */
  groups: string[];
}

export interface PartStatus {
  part: string;
  dimension: number;
  signature: string;
  generation: number | null;
  builtAt: string | null;
  count: number;
  stale: number;
  rebuildDue: boolean;
  reasons: string[];
  /** Why the backend cannot build it, if it cannot */
  unavailable: string | null;
}

export interface ProfileStatus {
  profile: string;
  weights: Record<string, number>;
  dimension: number;
  generation: number | null;
  builtAt: string | null;
  count: number;
  rebuildDue: boolean;
  reasons: string[];
}

export interface VectorsStatus {
  rebuildDue: boolean;
  /** The rebuild running now, whoever started it (the admin job, or `pangloss vectors rebuild`) */
  rebuilding: { by: string; since: string } | null;
  parts: PartStatus[];
  profiles: ProfileStatus[];
}

// (the client's base is `/api`)
export const getSimilar = (api: ApiClient, path: string, query: QueryParams): Promise<SimilarAnswer> =>
  api.get(path, query);

export const getStatus = (api: ApiClient): Promise<VectorsStatus> => api.get("/vectors/status");

/** The job of pangloss_admin that rebuilds every part (`POST /api/admin/jobs`) */
export const startRebuild = (api: ApiClient): Promise<unknown> =>
  api.post("/admin/jobs", { kind: "vectors_rebuild", options: { part: "all" } });
