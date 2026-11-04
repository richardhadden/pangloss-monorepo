import type { ApiClient } from "@pangloss/interface-core";

// What `/api/<Model>/{id}/history` of pangloss-history sends and takes (packages/pangloss-history/src/pangloss_history/api.py)

export type Operation = "create" | "update" | "delete" | "undelete" | "restore" | "baseline";

/** The operations that made a version with content (a delete or an undelete changes none) */
export const CONTENT_OPERATIONS: readonly Operation[] = ["create", "update", "restore", "baseline"];

export const hasContent = (op: Operation) => CONTENT_OPERATIONS.includes(op);

/** A field of the head node that differs from the version before (`count`: how many changes are under it) */
export interface FieldChange {
  key: string;
  kind: "added" | "removed" | "changed";
  count: number;
}

export interface VersionRecord {
  seq: number;
  version: number;
  op: Operation;
  who: string;
  /** ISO time */
  at: string;
  schemaPosition: Record<string, string>;
  restoredFrom: number | null;
  /** With `summary`: the label then, and what differs from the version recorded before it */
  label?: string | null;
  changes?: FieldChange[];
}

export interface Listing {
  id: string;
  model: string;
  versions: VersionRecord[];
  /** The version in the graph now (null if it is deleted) */
  currentVersion: number | null;
  /** The versions up to it that were not recorded */
  missing: number[];
}

/** What could not be upgraded to the models of now, or does not fit them */
export interface Problem {
  kind: string;
  message: string;
  path?: string | null;
  oldValue?: unknown;
  migration?: string | null;
  blocking: boolean;
}

export type Content = Record<string, unknown>;

export interface Version extends VersionRecord {
  /** In the read form (as the item's page reads an item), the entities with their labels now */
  content: Content;
  upgraded: boolean;
  problems: Problem[];
}

export interface Contents {
  id: string;
  model: string;
  currentVersion: number | null;
  versions: Version[];
}

const base = (type: string, id: string) => `/${encodeURIComponent(type)}/${encodeURIComponent(id)}/history`;

/** The versions, each with what changed in it (a 404 if nothing is recorded of the item) */
export const getHistory = (api: ApiClient, type: string, id: string): Promise<Listing> =>
  api.get(base(type, id), { summary: true });

/** One version, upgraded to the models of now, in the read form */
export const getVersion = (api: ApiClient, type: string, id: string, version: number): Promise<Version> =>
  api.get(`${base(type, id)}/${version}`, { view: true });

/** Every version with content, in the read form */
export const getContents = (api: ApiClient, type: string, id: string): Promise<Contents> =>
  api.get(`${base(type, id)}/contents`);

export interface Restored {
  id: string;
  version: number;
  restoredFrom: number;
}

/** Writes the version again, as a new one, if the item is still at `current` (a 412 if it is not) */
export const restoreVersion = (
  api: ApiClient,
  type: string,
  id: string,
  version: number,
  current: number,
): Promise<Restored> =>
  api.post(`${base(type, id)}/${version}/restore`, undefined, { headers: { "If-Match": `"${current}"` } });
