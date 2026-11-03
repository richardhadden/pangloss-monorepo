import type { ApiClient } from "@pangloss/interface-core";

// What `/api/review` of pangloss-review sends and takes (packages/pangloss-review/src/pangloss_review/status.py)

export type ReviewStatus = "unchecked" | "errors_found" | "checked";

export const STATUSES: readonly ReviewStatus[] = ["unchecked", "errors_found", "checked"];

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
  createdBy: string | null;
  lastEditedBy: string | null;
  reviewedBy?: string | null;
  reviewedAt?: string | null;
  openComments: number;
  comments: Comment[];
}

const one = (id: string) => `/review/${encodeURIComponent(id)}`;

/** The state and every comment (the resolved ones too: the panel filters them) */
export const getReview = (api: ApiClient, id: string): Promise<ReviewDetail> =>
  api.get(one(id), { resolved: true });

/** Change the status (`checked` publishes); the answer is the state, with the open comments only */
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
  createdBy: string | null;
  changedWhen: string | null;
  reviewedBy?: string | null;
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
  options: { status: ReviewStatus; type?: string; page?: number; pageSize?: number },
): Promise<Queue> =>
  api.get("/review/queue", {
    status: options.status,
    type: options.type || undefined,
    page: options.page,
    page_size: options.pageSize,
  });

export const resolveComment = (api: ApiClient, id: string, commentId: string): Promise<Comment> =>
  api.post(`${one(id)}/comments/${encodeURIComponent(commentId)}/resolve`);
