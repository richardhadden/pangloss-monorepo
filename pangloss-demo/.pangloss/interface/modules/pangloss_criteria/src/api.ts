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
  /** Why it is no longer evaluated (its criteria no longer fit the models): the path in the pattern, then the reason */
  broken: string | null;
  /** The migration that made it so (`app.name`); `null` when the worker found it so without one */
  brokenSince?: string | null;
  page: number;
  pageSize: number;
  candidates: Candidate[];
  /** The criteria: its own, or (a place that is the same one as another) those of the place of its mark that holds them */
  criteria?: Criteria | null;
  /** How many places of its document share its mark (`sameOne`); 1 without one */
  places?: number;
  /** The shared description it cites (or the place of its mark that holds the criteria cites), whose criteria hold too */
  shared?: Shared | null;
}

/** A shared description (a `Description`): its label and its criteria, which every mention that cites it has too */
export interface Shared {
  id: string;
  label: string;
  criteria: Criteria;
}

/**
 * What criteria would find, never one of `named` (the entities the document being edited names). With `description`
 * (the id of a shared description the mention cites), what that one's criteria and these find together: `criteria`
 * are then the mention's own, and may have no condition
 */
export function preview(api: ApiClient, criteria: Criteria, named: string[], description?: string | null): Promise<Preview> {
  return api.post<Preview>("/criteria/preview", description ? { criteria, named, description } : { criteria, named });
}

/** A shared description as the list of them gives it: how many mentions cite it */
export interface SharedListed extends Shared {
  mentions: number;
}

export interface SharedPage {
  count: number;
  page: number;
  pageSize: number;
  results: SharedListed[];
}

/** The shared descriptions of one of `types` (or a class below one), whose label has `q` in it, a page at a time */
export function sharedDescriptions(api: ApiClient, types: string[], q = "", page = 1, pageSize = 25): Promise<SharedPage> {
  return api.get<SharedPage>("/criteria/shared", { types: types.join(","), q: q || undefined, page, page_size: pageSize });
}

/** A mention that cites a shared description: its wording, its own conditions, and the document it is in */
export interface Mention {
  id: string;
  wording: string | null;
  /** Its own conditions, which hold beside the shared ones; `null`: none */
  criteria: Criteria | null;
  head: { id: string; type: string; label: string | null };
}

export interface MentionsPage {
  count: number;
  page: number;
  pageSize: number;
  results: Mention[];
}

/** The mentions that cite the shared description `id`, a page at a time */
export function descriptionMentions(api: ApiClient, id: string, page = 1, pageSize = 25): Promise<MentionsPage> {
  return api.get<MentionsPage>(`/criteria/shared/${encodeURIComponent(id)}/mentions`, { page, page_size: pageSize });
}

/** The documents a reference chip shows */
export interface DocumentRef {
  id: string;
  type: string;
  label: string | null;
}

/** Mentions in other documents with exactly these criteria: how many documents, and the first of them (20) */
export interface Similar {
  count: number;
  documents: DocumentRef[];
}

/**
 * The documents other than `except` (the one being edited) that hold a mention with exactly these criteria (and
 * cite `description`, or none)
 */
export function similarCriteria(
  api: ApiClient,
  criteria: Criteria,
  description: string | null,
  except: string | null,
): Promise<Similar> {
  return api.post<Similar>("/criteria/similar", { type: criteria.type, where: criteria.where ?? {}, description, except });
}

/** What making criteria a shared description did: the description, the documents now citing it, and those it could not change */
export interface ShareResult {
  description: DocumentRef;
  /** How many documents now cite it */
  updated: number;
  failed: { head: DocumentRef; detail: string }[];
}

/**
 * Makes a shared description of `criteria`, called `label`, and makes every mention with exactly these criteria cite
 * it: each of their documents is written again (a new version). A 422 says why it was not done (too many documents)
 */
export function shareCriteria(api: ApiClient, label: string, criteria: Criteria, except: string | null = null): Promise<ShareResult> {
  // (`except`: the document open in the form, which cites it when it is saved, and is not written here)
  return api.post<ShareResult>("/criteria/share", { label, type: criteria.type, where: criteria.where ?? {}, except });
}

/** A page of the candidates of the description `id` (the id of its `MatchesCriteria`), by label */
export function candidatesPage(api: ApiClient, id: string, page = 1, pageSize = 25): Promise<CandidatesPage> {
  return api.get<CandidatesPage>(`/criteria/${encodeURIComponent(id)}/candidates`, { page, page_size: pageSize });
}

/** A description that is out of date, as the page of them lists it (`GET /api/criteria/broken`) */
export interface BrokenDescription {
  /** The id of the description (its `MatchesCriteria`) */
  id: string;
  wording: string | null;
  criteria: Criteria | null;
  broken: string;
  brokenSince: string | null;
  /** The document it is in */
  head: { id: string; type: string; label: string | null };
}

export interface BrokenPage {
  count: number;
  page: number;
  pageSize: number;
  results: BrokenDescription[];
}

/** A page of the descriptions that are out of date, by the label of the document each is in (someone logged in) */
export function brokenDescriptions(api: ApiClient, page = 1, pageSize = 25): Promise<BrokenPage> {
  return api.get<BrokenPage>("/criteria/broken", { page, page_size: pageSize });
}

/** The address of an entity's page */
export function hrefOf(entity: { type: string; id: string }): string {
  return `/${encodeURIComponent(entity.type)}/${encodeURIComponent(entity.id)}`;
}

/** Where a description is edited: the form of its document, which scrolls to it and lights it up (`?show=`) */
export function formOf(description: { id: string; head: { type: string; id: string } }): string {
  return `/${encodeURIComponent(description.head.type)}/${encodeURIComponent(description.head.id)}/edit?show=${encodeURIComponent(description.id)}`;
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
