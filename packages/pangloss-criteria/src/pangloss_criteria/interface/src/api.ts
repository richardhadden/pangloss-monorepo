import type { ApiClient } from "@pangloss/interface-core";

/** How many candidates a card shows before "and N more" (and a preview gives) */
export const SHOWN = 5;

/** Criteria as a description stores them: a pattern of structured search (`POST /api/search`'s `type` and `where`) */
export interface Criteria {
  type: string;
  where?: Record<string, unknown> | null;
}

/** An entity that criteria find, as a chip shows it */
export interface Candidate {
  type: string;
  id: string;
  label: string | null;
}

/** What criteria would find if a description with them were saved now (`POST /api/criteria/preview`) */
export interface Preview {
  count: number;
  /** The first of them by label (five) */
  candidates: Candidate[];
  /** They find more than a description links */
  tooBroad: boolean;
}

/** A page of the linked candidates of a saved description (`GET /api/criteria/{id}/candidates`) */
export interface CandidatesPage {
  count: number;
  tooBroad: boolean;
  /** Its document has been written since the worker last worked it: the result may change */
  pending: boolean;
  evaluatedWhen: string | null;
  broken: string | null;
  page: number;
  pageSize: number;
  candidates: Candidate[];
  /** The criteria: its own, or (a place that is the same one as another) those of the place of its mark that holds them */
  criteria?: Criteria | null;
  /** How many places of its document share its mark (`sameOne`); 1 without one */
  places?: number;
}

/** What criteria would find, never one of `named` (the entities the document being edited names) */
export function preview(api: ApiClient, criteria: Criteria, named: string[]): Promise<Preview> {
  return api.post<Preview>("/criteria/preview", { criteria, named });
}

/** A page of the candidates of the description `id` (the id of its `MatchesCriteria`), by label */
export function candidatesPage(api: ApiClient, id: string, page = 1, pageSize = 25): Promise<CandidatesPage> {
  return api.get<CandidatesPage>(`/criteria/${encodeURIComponent(id)}/candidates`, { page, page_size: pageSize });
}

/** The address of an entity's page */
export function hrefOf(entity: { type: string; id: string }): string {
  return `/${encodeURIComponent(entity.type)}/${encodeURIComponent(entity.id)}`;
}

/** A description resolved (`POST /api/criteria/{id}/resolve`): its document, written again with the entity in its place */
export interface Resolved {
  head: { type: string; id: string; label: string | null };
  entity: { type: string; id: string; label: string | null };
  /** The version of the document that this made */
  version: number;
}

/**
 * "This is…": `entity` takes the place of the description `id` in its document, which the server writes again as an
 * update (based on the version it reads now). It need not be a candidate; the field must take it
 */
export function resolveDescription(api: ApiClient, id: string, entity: { type: string; id: string }): Promise<Resolved> {
  return api.post<Resolved>(`/criteria/${encodeURIComponent(id)}/resolve`, { entity: { type: entity.type, id: entity.id } });
}

/** What went wrong, as the API said it */
export const reasonOf = (error: unknown): string =>
  typeof error === "object" && error !== null && "detail" in error && typeof error.detail === "string"
    ? error.detail
    : error instanceof Error
      ? error.message
      : String(error);
