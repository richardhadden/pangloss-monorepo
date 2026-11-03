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

export const addComment = (api: ApiClient, id: string, text: string): Promise<Comment> =>
  api.post(`${one(id)}/comments`, { text });

export const resolveComment = (api: ApiClient, id: string, commentId: string): Promise<Comment> =>
  api.post(`${one(id)}/comments/${encodeURIComponent(commentId)}/resolve`);
