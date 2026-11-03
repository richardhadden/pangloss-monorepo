import type { ApiClient } from "@pangloss/interface-core";
import { action, createOptimisticStore, onCleanup, until } from "solid-js";
import { addComment, resolveComment, setReviewStatus } from "./api";
import type { Comment, ReviewStatus } from "./api";
import type { Snapshot } from "./poll";

/** A comment as the panel shows it: `pending` while it is being sent (shown at once, before the feed brings it) */
export type ShownComment = Comment & { pending?: boolean };

/** The review of a document as the button and the panel read it */
export interface ReviewView {
  id: string;
  /** `loading` until the feed's first snapshot; `none` for a document that has no review (shows nothing) */
  state: "loading" | "none" | "ready";
  status: ReviewStatus;
  published: boolean;
  reviewedBy: string | null;
  reviewedAt: string | null;
  openComments: number;
  /** Every comment, the resolved ones too, oldest first */
  comments: ShownComment[];
}

/** How long a write waits for the feed to bring it back before it lets the optimistic version go */
export const ACKNOWLEDGE_TIMEOUT = 15_000;

export function emptyView(id: string, state: ReviewView["state"] = "loading"): ReviewView {
  return {
    id,
    state,
    status: "unchecked",
    published: false,
    reviewedBy: null,
    reviewedAt: null,
    openComments: 0,
    comments: [],
  };
}

/** A snapshot of the feed as the view */
export function viewOf(id: string, snapshot: Snapshot): ReviewView {
  if (!snapshot.reviewable) return emptyView(id, "none");
  return {
    id,
    state: "ready",
    status: snapshot.status,
    published: snapshot.published,
    reviewedBy: snapshot.reviewedBy ?? null,
    reviewedAt: snapshot.reviewedAt ?? null,
    openComments: snapshot.openComments,
    comments: [...snapshot.comments].sort((a, b) => a.at.localeCompare(b.at)),
  };
}

/** The comments to show: the open ones, or all */
export function visibleComments(comments: readonly ShownComment[], showResolved: boolean): ShownComment[] {
  return showResolved ? [...comments] : comments.filter((c) => !c.resolved);
}

/** A source of snapshots, as `reviewFeed(id)` gives (`onstatus` is the connection's, set by the live source) */
export type FeedSource = AsyncIterable<Snapshot> & {
  onstatus?: (state: "connected" | "reconnecting" | "closed", error?: unknown) => void;
};

/**
 * The review of the document `id`, from the feed, and what can be done to it. Each write goes to the review API, is
 * shown at once (optimistically), and is kept until the feed brings it back (or `ACKNOWLEDGE_TIMEOUT` has passed: the
 * next snapshot will have it). A write that the API refuses is undone, and its promise rejects. Make it in a
 * component (once for each document: one connection), and call the writes from event handlers.
 */
export function createReview(options: {
  id: string;
  /** Opens the feed (`invoke(reviewFeed, { signal }, id)`); the signal is aborted when the page no longer needs it */
  feed: (signal: AbortSignal) => FeedSource;
  api: ApiClient;
  /** The username of the reader, for their own comments */
  me: () => string | undefined;
}) {
  const { id, api } = options;
  let cancelPrevious: (() => void) | undefined;
  const [review, setReview] = createOptimisticStore<ReviewView>(
    async function* () {
      // (one connection: a run that replaces another closes it first, and leaving the page closes it; a generator
      // waiting for the next snapshot cannot be stopped from outside, so the feed is aborted, which ends it)
      cancelPrevious?.();
      const abort = new AbortController();
      cancelPrevious = () => abort.abort();
      onCleanup(() => abort.abort());
      const source = options.feed(abort.signal);
      // (a reconnect is usually an access cookie that ran out while the page was open: the browser asks for a new one,
      // which the next try of the server function sends)
      source.onstatus = (state) => {
        if (state === "reconnecting") void api.post("/users/session/refresh").catch(() => undefined);
      };
      try {
        for await (const snapshot of source) yield viewOf(id, snapshot);
      } catch (error) {
        if (!abort.signal.aborted) throw error;
      }
    },
    emptyView(id),
    { seedLoadingValue: true },
  );

  // (the feed's acknowledgement: a timeout is not a failure, as the write was made)
  function* acknowledged(predicate: () => boolean) {
    try {
      yield until(predicate, { timeout: ACKNOWLEDGE_TIMEOUT });
    } catch {
      // (the next snapshot brings it)
    }
  }

  const changeStatus = action(function* (status: ReviewStatus) {
    setReview((draft) => {
      draft.status = status;
      draft.published = status === "checked";
    });
    yield setReviewStatus(api, id, status);
    yield* acknowledged(() => review.status === status);
  });

  const comment = action(function* (text: string) {
    const pendingId = `pending-${Math.random().toString(36).slice(2)}`;
    setReview((draft) => {
      draft.comments.push({
        id: pendingId,
        username: options.me() ?? "",
        at: new Date().toISOString(),
        text,
        resolved: false,
        pending: true,
      });
      draft.openComments += 1;
    });
    const made = (yield addComment(api, id, text)) as Comment;
    yield* acknowledged(() => review.comments.some((c) => c.id === made.id));
    return made;
  });

  const resolve = action(function* (commentId: string) {
    setReview((draft) => {
      const found = draft.comments.find((c) => c.id === commentId);
      if (found && !found.resolved) {
        found.resolved = true;
        found.resolvedBy = options.me() ?? null;
        draft.openComments = Math.max(0, draft.openComments - 1);
      }
    });
    yield resolveComment(api, id, commentId);
    yield* acknowledged(() => review.comments.some((c) => c.id === commentId && c.resolved));
  });

  return { review, changeStatus, comment, resolve };
}
