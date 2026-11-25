import type { ApiClient } from "@pangloss/interface-core";

// What the routes of pangloss_derived for derived documents send and take (pangloss_derived/api.py)

export interface Source {
  id: string;
  type: string;
  label: string;
  headId?: string | null;
  headType?: string | null;
  headLabel?: string | null;
}

/** Why a document is there */
export interface Why {
  id: string;
  type: string;
  rule: string;
  key?: string | null;
  context: string[];
  /** How the derivation holds, by the walk (`pangloss_derived.status`); none when its justification is gone */
  status?: string | null;
  sources: Source[];
  hiddenSources: number;
  /** A person made it their own */
  converted: boolean;
  convertedBy?: string | null;
  convertedAt?: string | null;
  /** The derivation it was made from still holds */
  holds: boolean;
  /** The classes it can be made into (a derived document that is still one) */
  convertsTo: string[];
}

export interface ConvertForm {
  type: string;
  id: string;
  version: number;
  initial: Record<string, unknown>;
  sources: { targetId: string; targetType: string; targetLabel?: string | null }[];
  derivedBy?: string | null;
  derivedContext: string[];
}

export interface Summary {
  id: string;
  type: string;
  label: string;
}

export const getWhy = (api: ApiClient, type: string, id: string) =>
  api.get<Why>(`/derived/document/${encodeURIComponent(type)}/${encodeURIComponent(id)}`);

/** Of a document made from a derived one: take off what its derivation passed through. Gives why it is there now */
export const clearContext = (api: ApiClient, type: string, id: string) =>
  api.post<Why>(`/derived/document/${encodeURIComponent(type)}/${encodeURIComponent(id)}/clear-context`);

/** A document derived from a document or from a part of it (`GET /api/NAME/{id}/cited?unprotected=true`) */
export interface DerivedFromRow {
  target: string;
  targetLabel: string | null;
  /** The derived document (null if `hidden`: the reader may not see it) */
  id: string | null;
  type: string | null;
  label: string | null;
  hidden: boolean;
}

export const getDerivedFrom = (api: ApiClient, type: string, id: string) =>
  api.get<DerivedFromRow[]>(`/${encodeURIComponent(type)}/${encodeURIComponent(id)}/cited`, { unprotected: "true" });

export const getConvertForm = (api: ApiClient, type: string, id: string, to: string) =>
  api.get<ConvertForm>(
    `/derived/convert/${encodeURIComponent(type)}/${encodeURIComponent(id)}/${encodeURIComponent(to)}`,
  );

export const convertDocument = (
  api: ApiClient,
  model: string,
  id: string,
  to: string,
  version: number,
  data: Record<string, unknown>,
) => api.post<Summary>("/derived/convert", { model, id, to, version, data });
