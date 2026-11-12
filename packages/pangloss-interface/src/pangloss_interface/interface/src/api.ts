import type { ApiClient } from "@pangloss/interface-core";

// What the merge routes of the API send and take (packages/pangloss-api/src/pangloss_api/routes/merges.py;
// the results are those of `pangloss_models.merging`, with camelCase keys)

export type MergeState = "proposed" | "rejected" | "stale" | "running" | "done" | "undone";

export const MERGE_STATES: readonly MergeState[] = ["proposed", "rejected", "stale", "running", "done", "undone"];

/** A document or entity named in a result */
export interface HeadRef {
  id: string;
  type: string;
  label?: string | null;
}

export type Values = Record<string, unknown>;

export interface MergeRecord {
  id: string;
  survivor: string;
  absorbed: string;
  state: MergeState;
  /** Who carried it out, and when (ISO) */
  by?: string | null;
  when?: string | null;
  /** The class of the survivor after the merge, and before it */
  survivorType?: string | null;
  survivorTypeBefore?: string | null;
  absorbedType?: string | null;
  survivorLabel?: string | null;
  absorbedLabel?: string | null;
  /** The versions of the two that a proposal was made from */
  survivorVersion?: number | null;
  absorbedVersion?: number | null;
  heads: number;
  moved: number;
  dropped: number;
  undoneBy?: string | null;
  undoneWhen?: string | null;
  proposedBy?: string | null;
  proposedWhen?: string | null;
  note?: string | null;
  /** The fields a proposal chose for the survivor */
  values?: Values | null;
  rejectedBy?: string | null;
  rejectedWhen?: string | null;
  reason?: string | null;
  undoProposedBy?: string | null;
  undoProposedWhen?: string | null;
  undoNote?: string | null;
  undoRejectedBy?: string | null;
  undoRejectedReason?: string | null;
}

export interface MergePreview {
  survivor: string;
  absorbed: string;
  /** The class the survivor would have */
  survivorType?: string | null;
  possible: boolean;
  /** Why it cannot be made */
  refused: string[];
  /** How many documents and entities it would write */
  heads: number;
  limit: number;
  /** More than the limit: for an admin only */
  large: boolean;
  /** How many refer to each, by their type */
  referToSurvivor: Record<string, number>;
  referToAbsorbed: Record<string, number>;
  /** Documents that name both in one relation (they will name the survivor once), and in different relations */
  collapsed: HeadRef[];
  both: HeadRef[];
  /** References that stay on the absorbed entity (`KeepOnMerge()`) */
  kept: number;
  /** The fields the survivor would have, as an update takes them */
  values?: Values | null;
}

export interface MergeResult {
  merge: MergeRecord;
  collapsed: HeadRef[];
  both: HeadRef[];
  kept: number;
  late: number;
}

/** A reference an undo could not put back */
export interface Unmatched {
  reason: string;
  source?: string;
  sourceType?: string;
  head?: string;
  field?: string;
  [key: string]: unknown;
}

export interface UnmergeResult {
  merge: MergeRecord;
  restored: number;
  heads: number;
  unmatched: Unmatched[];
  /** Written to the survivor since the merge: they stay on it */
  madeSince: HeadRef[];
  fieldsRestored: boolean;
  /** The survivor's fields before the merge, where they were not put back */
  draft?: Values | null;
  draftType?: string | null;
  draftReason?: string | null;
}

export interface Permissions {
  /** Merges, and undoes a merge, without anyone else */
  direct: boolean;
  /** May make a merge over the limit */
  large: boolean;
  limit: number;
}

export interface MergeList {
  results: MergeRecord[];
  count: number;
  page: number;
  pageSize: number;
}

export interface MergeBody {
  absorb: string;
  values?: Values;
  asClass?: string;
  versionInto?: number;
  versionAbsorb?: number;
  note?: string;
}

const entity = (type: string, id: string) => `/${encodeURIComponent(type)}/${encodeURIComponent(id)}`;
const merge = (id: string) => `/merges/${encodeURIComponent(id)}`;

export const getPermissions = (api: ApiClient): Promise<Permissions> => api.get("/merges/permissions");

/** What merging `absorb` into the entity would do; nothing is written */
export const previewMerge = (
  api: ApiClient,
  type: string,
  id: string,
  body: { absorb: string; asClass?: string },
): Promise<MergePreview> => api.post(`${entity(type, id)}/merge/preview`, body);

export const mergeEntities = (api: ApiClient, type: string, id: string, body: MergeBody): Promise<MergeResult> =>
  api.post(`${entity(type, id)}/merge`, body);

export const proposeMerge = (api: ApiClient, type: string, id: string, body: MergeBody): Promise<MergeRecord> =>
  api.post(`${entity(type, id)}/merge/propose`, body);

/** The merges the entity is part of, the latest first */
export const mergesOf = (api: ApiClient, type: string, id: string): Promise<MergeRecord[]> =>
  api.get<{ merges: MergeRecord[] }>(`${entity(type, id)}/merges`).then((answer) => answer.merges);

export const listMerges = (
  api: ApiClient,
  options: { states?: string[]; open?: boolean; page?: number; pageSize?: number },
): Promise<MergeList> =>
  api.get("/merges", {
    state: options.states,
    open: options.open ? true : undefined,
    page: options.page,
    page_size: options.pageSize,
  });

export const getMerge = (api: ApiClient, id: string): Promise<MergeRecord> => api.get(merge(id));

/** Carries out a proposal: with the fields proposed, or with those given and the versions they were decided on */
export const verifyMerge = (api: ApiClient, id: string, body?: Omit<MergeBody, "absorb" | "note">): Promise<MergeResult> =>
  api.post(`${merge(id)}/verify`, body ?? {});

export const rejectMerge = (api: ApiClient, id: string, reason: string): Promise<MergeRecord> =>
  api.post(`${merge(id)}/reject`, { reason: reason || null });

/** Undoes a merge, or (`dryRun`) says what undoing it would do */
export const undoMerge = (
  api: ApiClient,
  id: string,
  options: { dryRun?: boolean; confirmMigrated?: boolean } = {},
): Promise<UnmergeResult> => api.post(`${merge(id)}/undo`, options);

export const proposeUndo = (api: ApiClient, id: string, note: string): Promise<MergeRecord> =>
  api.post(`${merge(id)}/undo/propose`, { note: note || null });

export const rejectUndo = (api: ApiClient, id: string, reason: string): Promise<MergeRecord> =>
  api.post(`${merge(id)}/undo/reject`, { reason: reason || null });

/** Where the pages are */
export const compareHref = (type: string, survivor: string, absorbed: string) =>
  `/${encodeURIComponent(type)}/${encodeURIComponent(survivor)}/merge/${encodeURIComponent(absorbed)}`;
export const mergeHref = (id: string) => `/merges/${encodeURIComponent(id)}`;
export const itemHref = (type: string, id: string) => `/${encodeURIComponent(type)}/${encodeURIComponent(id)}`;

/** Whether a merge stands: made, and not undone */
export const stands = (record: MergeRecord) => record.state === "done" || record.state === "running";

/** Whether it waits for someone: proposed, or proposed to be undone */
export const waits = (record: MergeRecord) =>
  record.state === "proposed" || (stands(record) && !!record.undoProposedBy);
