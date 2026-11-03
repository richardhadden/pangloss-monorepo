// @vitest-environment happy-dom
import {
  ApiError,
  ApiProvider,
  ModelsProvider,
  SessionProvider,
  ToastsProvider,
  useToasts,
} from "@pangloss/interface-core";
import type { ApiClient, ConsoleActionProps, ModelDefinition, User } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { For } from "solid-js";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { ReviewDetail } from "../api";
import type { Snapshot } from "../poll";

// (the feed is the test's: it pushes the snapshots the server would send)
const feeds: { id: string; push: (s: Snapshot) => void; closed: boolean }[] = [];
// (`invoke` passes the signal on, as `live` ends its iteration when it is aborted)
vi.mock("@solidjs/web/server-functions", () => ({
  invoke: (fn: (...args: unknown[]) => unknown, options: { signal: AbortSignal }, ...args: unknown[]) =>
    fn(...args, options.signal),
}));
vi.mock("../feed", () => ({
  reviewFeed: (id: string, signal: AbortSignal) => {
    const queue: Snapshot[] = [];
    let wake: (() => void) | undefined;
    const feed = {
      id,
      closed: false,
      push(snapshot: Snapshot) {
        queue.push(snapshot);
        wake?.();
      },
    };
    feeds.push(feed);
    signal.addEventListener("abort", () => {
      feed.closed = true;
      wake?.();
    });
    return {
      async *[Symbol.asyncIterator]() {
        while (!signal.aborted) {
          if (queue.length === 0) await new Promise<void>((resolve) => (wake = resolve));
          while (queue.length && !signal.aborted) yield queue.shift()!;
        }
      },
    };
  },
}));

const { default: ReviewAction } = await import("./ReviewAction");

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

const model = (kind: ModelDefinition["kind"]) => ({ name: "Letter", kind }) as ModelDefinition;
const me = { username: "me", email: "m@example.org", fullName: null, admin: false } as User;

const settle = async () => {
  for (let i = 0; i < 6; i++) await new Promise((resolve) => setTimeout(resolve));
};

function client(post: ApiClient["post"] = vi.fn(async () => ({})) as never): ApiClient {
  return {
    baseUrl: "/api",
    // (the document, read for its parts when the panel opens)
    get: vi.fn(async () => ({ id: "d1", type: "Letter", label: "A letter" })) as never,
    post,
    put: vi.fn() as never,
    patch: vi.fn() as never,
    postForm: vi.fn() as never,
    delete: vi.fn() as never,
  };
}

function ShownToasts() {
  const toasts = useToasts();
  return (
    <ul>
      <For each={toasts?.toasts() ?? []}>
        {(toast) => <li data-testid="toast" data-tone={toast.tone}>{toast.message}</li>}
      </For>
    </ul>
  );
}

let dispose: (() => void) | undefined;
beforeEach(() => {
  feeds.length = 0;
});
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

// (`user: null` is no one logged in)
function show(props: Partial<ConsoleActionProps> = {}, user: User | null = me, api = client()) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <SessionProvider user={() => user ?? undefined}>
        <ApiProvider client={api}>
          <ModelsProvider definitions={{ models: {}, enums: {} }}>
          <ToastsProvider>
            <ReviewAction type="Letter" id="d1" model={model("Document")} page="item" {...props} />
            <ShownToasts />
          </ToastsProvider>
          </ModelsProvider>
        </ApiProvider>
      </SessionProvider>
    ),
    container,
  );
  return api;
}

const reviewButton = () => document.querySelector<HTMLElement>('[data-testid="review-button"]');
const count = () => document.querySelector('[data-testid="review-count"]')?.textContent;
const panel = () => document.querySelector<HTMLElement>('[data-testid="review-panel"]');

test("nothing until the feed says; then a flag for the status, and the number of open comments", async () => {
  show();
  await settle();
  expect(feeds.map((f) => f.id)).toEqual(["d1"]);
  expect(reviewButton()).toBeNull();
  feeds[0]!.push(detail({ status: "errors_found", openComments: 2 }));
  await settle();
  expect(reviewButton()?.dataset.status).toBe("errors_found");
  expect(count()).toBe("2");
  const button = reviewButton()!.closest("button")!;
  expect(button.getAttribute("aria-label")).toBe("Review: Errors found, open comments: 2");
  expect(button.getAttribute("aria-pressed")).toBe("false");
});

test("what another user does reaches the button and the open panel while the page is open", async () => {
  show();
  await settle();
  feeds[0]!.push(detail());
  await settle();
  expect(count()).toBeUndefined();
  expect(reviewButton()!.closest("button")!.getAttribute("aria-label")).toBe("Review: Unchecked");
  reviewButton()!.closest("button")!.click();
  await settle();
  expect(panel()?.dataset.open).toBe("true");
  feeds[0]!.push(
    detail({
      status: "checked",
      published: true,
      openComments: 1,
      comments: [{ id: "c1", username: "bob", at: "2026-11-03T10:00:00Z", text: "Fine by me", resolved: false }],
    }),
  );
  await settle();
  expect(reviewButton()?.dataset.status).toBe("checked");
  expect(count()).toBe("1");
  expect(panel()!.textContent).toContain("Fine by me");
});

test("a document that has no review shows nothing", async () => {
  show();
  await settle();
  feeds[0]!.push({ reviewable: false });
  await settle();
  expect(reviewButton()).toBeNull();
  expect(panel()).toBeNull();
});

test("nor does an entity, or a reader who is not logged in (and no feed is opened)", async () => {
  show({ model: model("Entity") });
  await settle();
  expect(feeds).toHaveLength(0);
  dispose?.();
  show({}, null);
  await settle();
  expect(feeds).toHaveLength(0);
  expect(reviewButton()).toBeNull();
});

test("a status change the API refuses is undone, and said in a red toast", async () => {
  const post = vi.fn(async () => {
    throw new ApiError(403, "me created or last edited this document, and cannot check it");
  });
  show({}, me, client(post as never));
  await settle();
  feeds[0]!.push(detail());
  await settle();
  reviewButton()!.closest("button")!.click();
  await settle();
  [...panel()!.querySelectorAll("button")].find((b) => b.textContent === "Checked")!.click();
  await settle();
  // (one connection still: the write does not open another)
  expect(feeds).toHaveLength(1);
  expect(post).toHaveBeenCalledWith("/review/d1/status", { status: "checked" });
  expect(reviewButton()?.dataset.status).toBe("unchecked");
  const toast = document.querySelector<HTMLElement>('[data-testid="toast"]');
  expect(toast?.dataset.tone).toBe("error");
  expect(toast?.textContent).toBe(
    "The status was not changed: me created or last edited this document, and cannot check it",
  );
});

test("leaving the page closes the feed", async () => {
  show();
  await settle();
  feeds[0]!.push(detail());
  await settle();
  dispose?.();
  dispose = undefined;
  await settle();
  expect(feeds[0]!.closed).toBe(true);
});

test("a comment sent from the panel is the reader's at once, and stays when the feed brings it", async () => {
  const made = { id: "c9", username: "me", at: "2026-11-03T12:00:00Z", text: "Spelling", resolved: false };
  const post = vi.fn(async () => made);
  show({}, me, client(post as never));
  await settle();
  feeds[0]!.push(detail());
  await settle();
  reviewButton()!.closest("button")!.click();
  await settle();
  const box = panel()!.querySelector("textarea")!;
  box.value = "Spelling";
  box.dispatchEvent(new Event("input", { bubbles: true }));
  await settle();
  [...panel()!.querySelectorAll("button")].find((b) => b.textContent === "Send")!.click();
  await settle();
  expect(post).toHaveBeenCalledWith("/review/d1/comments", { text: "Spelling" });
  const bubble = () => panel()!.querySelector<HTMLElement>('[data-testid="review-comment"]');
  expect(bubble()?.dataset.mine).toBe("true");
  expect(document.querySelector('[data-testid="toast"]')).toBeNull();
  feeds[0]!.push(detail({ openComments: 1, comments: [made] }));
  await settle();
  expect(bubble()?.textContent).toContain("Resolve");
  expect(count()).toBe("1");
  expect(box.value).toBe("");
});
