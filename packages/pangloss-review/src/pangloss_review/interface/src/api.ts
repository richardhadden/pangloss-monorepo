import type { ApiClient, Creator } from "@pangloss/interface-core";

// What `/api/review` of pangloss-review sends and takes (packages/pangloss-review/src/pangloss_review/status.py)

export type ReviewStatus = "unchecked" | "errors_found" | "published";

export const STATUSES: readonly ReviewStatus[] = ["unchecked", "errors_found", "published"];

export interface Comment {
  id: string;
  username: string;
  /** ISO time */
  at: string;
  text: string;
  /** The part of the document it is about (a nested document), and what that was called when it was made */
  targetId?: string | null;
  targetLabel?: string | null;
  resolved: boolean;
  resolvedBy?: string | null;
  resolvedAt?: string | null;
}

export interface ReviewDetail {
  id: string;
  type: string;
  label: string | null;
  status: ReviewStatus;
  published: boolean;
  createdBy: Creator[];
  lastEditedBy: string | null;
  reviewedBy?: string | null;
  reviewedAt?: string | null;
  /** Who is to review it (anyone may all the same) */
  assignedTo?: string | null;
  assignedBy?: string | null;
  openComments: number;
  comments: Comment[];
}

const one = (id: string) => `/review/${encodeURIComponent(id)}`;

/** The state and every comment (the resolved ones too: the panel filters them) */
export const getReview = (api: ApiClient, id: string): Promise<ReviewDetail> =>
  api.get(one(id), { resolved: true });

/** Change the status (`published` publishes); the answer is the state, with the open comments only */
export const setReviewStatus = (api: ApiClient, id: string, status: ReviewStatus): Promise<ReviewDetail> =>
  api.post(`${one(id)}/status`, { status });

/** A comment on the document, or (`targetId`) on a part of it */
export const addComment = (api: ApiClient, id: string, text: string, targetId?: string): Promise<Comment> =>
  api.post(`${one(id)}/comments`, targetId ? { text, targetId } : { text });

/** The classes whose documents are reviewed */
export const getReviewableTypes = (api: ApiClient): Promise<string[]> => api.get("/review/types");

export interface QueueItem {
  id: string;
  type: string;
  label: string | null;
  status: ReviewStatus;
  createdBy: Creator[];
  changedWhen: string | null;
  reviewedBy?: string | null;
  assignedTo?: string | null;
  openComments: number;
}

export interface Queue {
  results: QueueItem[];
  count: number;
  page: number;
  pageSize: number;
  nextPage: number | null;
  previousPage: number | null;
}

/** The documents in a status (and of a class, and those below it), the oldest change first */
export const getQueue = (
  api: ApiClient,
  options: { status: ReviewStatus; type?: string; assignedTo?: string; q?: string; page?: number; pageSize?: number },
): Promise<Queue> =>
  api.get("/review/queue", {
    status: options.status,
    type: options.type || undefined,
    q: options.q || undefined,
    assigned_to: options.assignedTo || undefined,
    page: options.page,
    page_size: options.pageSize,
  });

export const resolveComment = (api: ApiClient, id: string, commentId: string): Promise<Comment> =>
  api.post(`${one(id)}/comments/${encodeURIComponent(commentId)}/resolve`);

// --- whose tasks -----------------------------------------------------------------------------------------------------

/** Give a document to a user to review, or (null) to no one: anyone may take one for themselves, an admin gives it to anyone */
export const assignReview = (api: ApiClient, id: string, username: string | null): Promise<ReviewDetail> =>
  api.post(`${one(id)}/assign`, { username });

export interface TaskCounts {
  documents: number;
  reconciliations: number;
  identifications: number;
}

/** How many tasks there are of each kind, of everyone or (`assignedTo`: `me`, a username, `none`) of some */
export const getTaskCounts = (api: ApiClient, assignedTo?: string): Promise<TaskCounts> =>
  api.get("/review/tasks/summary", { assigned_to: assignedTo || undefined });

// --- parts of documents that are tasks ---------------------------------------------------------------------------

/** An item, as a chip shows it */
export interface Ref {
  type: string;
  id: string;
  label?: string | null;
}

interface Page<T> {
  results: T[];
  count: number;
  page: number;
  pageSize: number;
  nextPage: number | null;
  previousPage: number | null;
}

/** An unreconciled mention: what the source calls it, the entity type it would be, and where it is */
export interface Mention {
  id: string;
  label: string;
  unreconciledType: string;
  uris: string[];
  /** The document it is directly in, and the head of that */
  holder: Ref;
  head: Ref;
  assignedTo?: string | null;
  /** (of one asked for by its id) The entities that have one of its URIs as their own: who it is, if the URIs are right */
  known?: Ref[];
}

export interface SimilarMention extends Mention {
  /** It names a URI this one names: the same, whatever it is called */
  sameUri?: boolean;
  /** How alike the labels are, from 0 to 1 */
  score: number;
  /** The same label, but for case, accents and spacing */
  exact: boolean;
}

export interface Reconciled {
  id: string;
  entity: Ref;
  head: Ref;
  urisAdded: string[];
  /** URIs that another entity has, so that this one was not given them */
  urisTaken: string[];
  /** How many other mentions are being reconciled in the background */
  queued: number;
}

const mention = (id: string) => `/review/unreconciled/${encodeURIComponent(id)}`;

export const getMentions = (
  api: ApiClient,
  options: { type?: string; q?: string; assignedTo?: string; page?: number; pageSize?: number },
): Promise<Page<Mention>> =>
  api.get("/review/unreconciled", {
    type: options.type || undefined,
    q: options.q || undefined,
    assigned_to: options.assignedTo || undefined,
    page: options.page,
    page_size: options.pageSize,
  });

/** The entity types that may be left unreconciled */
export const getMentionTypes = (api: ApiClient): Promise<string[]> => api.get("/review/unreconciled/types");

/** One mention as it is saved (a 404 for one that is not: reconciled already, or not yet saved) */
export const getMention = (api: ApiClient, id: string): Promise<Mention> => api.get(mention(id));

export const getSimilarMentions = (api: ApiClient, id: string): Promise<SimilarMention[]> =>
  api.get(`${mention(id)}/similar`);

/** The identifications a toolchain suggested that name a URI of the mention: of the same person */
export const getSuggestionsOfMention = (api: ApiClient, id: string): Promise<Suggestion[]> =>
  api.get(`${mention(id)}/suggestions`);

/**
 * Put the entity in the place of the mention; the others (`also`), and the suggestions that name its URI
 * (`suggestions`, confirmed as the entity), are done in the background. `inForm`: the form of its document holds the
 * change and saves it, so the document is not written (the entity is given the URIs, and what is in other documents
 * is done)
 */
export const reconcileMention = (
  api: ApiClient,
  id: string,
  entity: Ref,
  also: string[],
  inForm = false,
  suggestions: string[] = [],
): Promise<Reconciled> =>
  api.post(`${mention(id)}/reconcile`, { entity: { type: entity.type, id: entity.id }, also, inForm, suggestions });

export interface Candidate extends Ref {
  /** How likely, in per cent, among alternatives */
  percent?: number | null;
}

/** An identification that a toolchain suggested, for a person to confirm */
export interface Suggestion {
  id: string;
  /** Its class: `IdentificationByToolchain`, or a project's subclass of it */
  type: string;
  /** The class it becomes when it is confirmed (absent: `Identification`) */
  becomes?: string;
  identifiedBy?: string | null;
  toolchainVersion?: string | null;
  uris: string[];
  candidates: Candidate[];
  holder: Ref;
  head: Ref;
  assignedTo?: string | null;
  /** (of one asked for by its id) The entities that have one of its URIs as their own */
  known?: Ref[];
  /** (of one that is like another) It names a URI the other names: the same person, whoever its candidates are */
  sameUri?: boolean;
}

const suggestion = (id: string) => `/review/identifications/${encodeURIComponent(id)}`;

export const getSuggestions = (
  api: ApiClient,
  options: { assignedTo?: string; page?: number; pageSize?: number },
): Promise<Page<Suggestion>> =>
  api.get("/review/identifications", {
    assigned_to: options.assignedTo || undefined,
    page: options.page,
    page_size: options.pageSize,
  });

export const getSuggestion = (api: ApiClient, id: string): Promise<Suggestion> => api.get(suggestion(id));

/** Other suggestions of the same candidates, each about as likely */
export const getSimilarSuggestions = (api: ApiClient, id: string): Promise<Suggestion[]> =>
  api.get(`${suggestion(id)}/similar`);

/** The unreconciled mentions that name a URI of the suggestion: of the same person */
export const getMentionsOfSuggestion = (api: ApiClient, id: string): Promise<Mention[]> =>
  api.get(`${suggestion(id)}/mentions`);

/**
 * For a suggestion confirmed in a form (it is confirmed when the form is saved): give the others (`also`, in other
 * documents) the identification the form holds (`target`), and reconcile the mentions that name its URI (`mentions`)
 * with the one entity it is of (`entity`), now and in the background. Gives how many are being done
 */
export const giveIdentification = (
  api: ApiClient,
  id: string,
  also: string[],
  target: unknown,
  mentions: string[] = [],
  entity?: Ref,
): Promise<{ queued: number }> =>
  api.post(`${suggestion(id)}/give`, {
    also,
    target,
    mentions,
    entity: entity ? { type: entity.type, id: entity.id } : null,
  });

/** Everyone's username (for an admin's choice of whose tasks to see): `GET /api/users/directory` */
export const getUsernames = (api: ApiClient): Promise<{ username: string; kind?: string }[]> =>
  api.get("/users/directory");
