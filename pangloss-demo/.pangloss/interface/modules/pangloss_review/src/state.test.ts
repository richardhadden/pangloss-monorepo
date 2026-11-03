// @vitest-environment happy-dom
import type { ApiClient } from "@pangloss/interface-core";
import { ApiError } from "@pangloss/interface-core";
import { createRoot, flush } from "solid-js";
import { afterEach, expect, test, vi } from "vitest";
import type { Comment, ReviewDetail } from "./api";
import type { Snapshot } from "./poll";
import { createReview, viewOf, visibleComments } from "./state";
import type { FeedSource } from "./state";

const comment = (id: string, username: string, at: string, more: Partial<Comment> = {}): Comment => ({
  id,
  username,
  at,
  text: `text of ${id}`,
  resolved: false,
  ...more,
});

const detail = (more: Partial<ReviewDetail> = {}): Snapshot => ({
  reviewable: true,
  id: "d1",
  type: "Letter",
  label: "A letter",
  status: "unchecked",
  published: false,
  createdBy: "ann",
  lastEditedBy: "ann",
  openComments: 0,
  comments: [],
  ...more,
});

/** A feed the test pushes snapshots into; it ends when its signal is aborted */
function controlledFeed() {
  const queue: Snapshot[] = [];
  let wake: (() => void) | undefined;
  const opened: AbortSignal[] = [];
  const open = (signal: AbortSignal): FeedSource => {
    opened.push(signal);
    signal.addEventListener("abort", () => wake?.());
    return {
      async *[Symbol.asyncIterator]() {
        while (!signal.aborted) {
          if (queue.length === 0) await new Promise<void>((resolve) => (wake = resolve));
          while (queue.length && !signal.aborted) yield queue.shift()!;
        }
      },
    };
  };
  return {
    open,
    opened,
    push(snapshot: Snapshot) {
      queue.push(snapshot);
      wake?.();
    },
  };
}

const settle = async () => {
  for (let i = 0; i < 5; i++) {
    await new Promise((resolve) => setTimeout(resolve));
    flush();
  }
};

function fakeApi(post: (path: string, body?: unknown) => Promise<unknown>): ApiClient {
  return {
    baseUrl: "/api",
    get: vi.fn() as never,
    post: vi.fn(post) as never,
    put: vi.fn() as never,
    patch: vi.fn() as never,
    postForm: vi.fn() as never,
    delete: vi.fn() as never,
  };
}

let cleanup: (() => void) | undefined;
afterEach(() => cleanup?.());

function start(post: (path: string, body?: unknown) => Promise<unknown>) {
  const feed = controlledFeed();
  const api = fakeApi(post);
  let made!: ReturnType<typeof createReview>;
  createRoot((dispose) => {
    made = createReview({ id: "d1", feed: feed.open, api, me: () => "me" });
    cleanup = dispose;
  });
  return { ...made, feed, api };
}

test("a snapshot as the view: the comments oldest first; no review is 'none'", () => {
  const view = viewOf(
    "d1",
    detail({ comments: [comment("b", "x", "2026-01-02T00:00:00Z"), comment("a", "y", "2026-01-01T00:00:00Z")] }),
  );
  expect(view.state).toBe("ready");
  expect(view.comments.map((c) => c.id)).toEqual(["a", "b"]);
  expect(viewOf("d1", { reviewable: false }).state).toBe("none");
});

test("the resolved comments are shown only when asked for", () => {
  const all = [comment("a", "x", "1"), comment("b", "x", "2", { resolved: true })];
  expect(visibleComments(all, false).map((c) => c.id)).toEqual(["a"]);
  expect(visibleComments(all, true).map((c) => c.id)).toEqual(["a", "b"]);
});

test("the view is loading until the feed says, and follows it", async () => {
  const { review, feed } = start(async () => ({}));
  expect(review.state).toBe("loading");
  feed.push(detail({ openComments: 1, comments: [comment("a", "ann", "1")] }));
  await settle();
  expect(review.state).toBe("ready");
  expect(review.openComments).toBe(1);
  feed.push(detail({ status: "checked", published: true }));
  await settle();
  expect(review.status).toBe("checked");
  expect(review.comments).toHaveLength(0);
});

test("a comment is shown at once, as being sent, and then as the feed brings it", async () => {
  let answer!: (value: Comment) => void;
  const { review, feed, comment: send, api } = start(
    () => new Promise((resolve) => (answer = resolve as (value: Comment) => void)),
  );
  feed.push(detail());
  await settle();
  const sent = send("Looks wrong");
  await settle();
  expect(api.post).toHaveBeenCalledWith("/review/d1/comments", { text: "Looks wrong" });
  expect(review.comments).toHaveLength(1);
  expect(review.comments[0]).toMatchObject({ text: "Looks wrong", username: "me", pending: true });
  expect(review.openComments).toBe(1);
  const made = comment("c1", "me", "2026-01-01T00:00:00Z", { text: "Looks wrong" });
  answer(made);
  await settle();
  feed.push(detail({ openComments: 1, comments: [made] }));
  await sent;
  await settle();
  expect(review.comments.map((c) => [c.id, c.pending ?? false])).toEqual([["c1", false]]);
});

test("a status change is shown at once, and undone if the API refuses it", async () => {
  const { review, feed, changeStatus } = start(async () => {
    throw new ApiError(403, "ann created or last edited this document, and cannot check it");
  });
  feed.push(detail());
  await settle();
  const refused = changeStatus("checked").catch((error: unknown) => error);
  await settle();
  expect(await refused).toMatchObject({ status: 403 });
  await settle();
  expect(review.status).toBe("unchecked");
  expect(review.published).toBe(false);
});

test("a status change that the API makes is kept as the feed confirms it", async () => {
  const { review, feed, changeStatus, api } = start(async () => detail({ status: "errors_found" }));
  feed.push(detail());
  await settle();
  const changing = changeStatus("errors_found");
  await settle();
  expect(review.status).toBe("errors_found");
  expect(api.post).toHaveBeenCalledWith("/review/d1/status", { status: "errors_found" });
  feed.push(detail({ status: "errors_found" }));
  await changing;
  await settle();
  expect(review.status).toBe("errors_found");
});

test("resolving a comment hides it from the open ones at once", async () => {
  const open = comment("a", "ann", "1");
  const { review, feed, resolve } = start(async () => ({ ...open, resolved: true }));
  feed.push(detail({ openComments: 1, comments: [open] }));
  await settle();
  const resolving = resolve("a");
  await settle();
  expect(review.comments[0]!.resolved).toBe(true);
  expect(review.openComments).toBe(0);
  feed.push(detail({ openComments: 0, comments: [{ ...open, resolved: true, resolvedBy: "me" }] }));
  await resolving;
  await settle();
  expect(review.comments[0]).toMatchObject({ resolved: true, resolvedBy: "me" });
});

test("one connection, for all the writes; closed when the owner goes", async () => {
  const { feed, changeStatus, comment: send } = start(async () => comment("c1", "me", "1"));
  feed.push(detail());
  await settle();
  const writes = Promise.all([changeStatus("errors_found"), send("x")]);
  await settle();
  feed.push(detail({ status: "errors_found", openComments: 1, comments: [comment("c1", "me", "1")] }));
  await writes;
  await settle();
  expect(feed.opened).toHaveLength(1);
  expect(feed.opened[0]!.aborted).toBe(false);
  cleanup?.();
  cleanup = undefined;
  expect(feed.opened[0]!.aborted).toBe(true);
});
