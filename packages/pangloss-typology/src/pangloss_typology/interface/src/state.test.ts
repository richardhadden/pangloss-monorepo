// @vitest-environment happy-dom
import type { ApiClient } from "@pangloss/interface-core";
import { ApiError } from "@pangloss/interface-core";
import { createRoot, flush } from "solid-js";
import { afterEach, expect, test, vi } from "vitest";
import type { TreeNode } from "./api";
import { createTypeTree } from "./state";
import type { TreeSource } from "./state";
import { findNode, parentOf } from "./tree";

const leaf = (id: string, label = id): TreeNode => ({ id, label, children: [] });
const TREE: TreeNode[] = [{ id: "clerk", label: "Clerk", children: [leaf("secretary", "Secretary")] }, leaf("advisor", "Advisor")];
const MOVED: TreeNode[] = [
  { id: "clerk", label: "Clerk", children: [leaf("advisor", "Advisor"), leaf("secretary", "Secretary")] },
];

/** A feed the test pushes trees into; it ends when its signal is aborted */
function controlledFeed() {
  const queue: TreeNode[][] = [];
  let wake: (() => void) | undefined;
  const opened: AbortSignal[] = [];
  const open = (signal: AbortSignal): TreeSource => {
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
    push(nodes: TreeNode[]) {
      queue.push(nodes);
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

function fakeApi(write: () => Promise<unknown>): ApiClient {
  return {
    baseUrl: "/api",
    get: vi.fn() as never,
    post: vi.fn(write) as never,
    put: vi.fn() as never,
    patch: vi.fn(write) as never,
    postForm: vi.fn() as never,
    delete: vi.fn() as never,
  };
}

let cleanup: (() => void) | undefined;
afterEach(() => cleanup?.());

function start(write: () => Promise<unknown> = async () => ({})) {
  const feed = controlledFeed();
  const api = fakeApi(write);
  let made!: ReturnType<typeof createTypeTree>;
  createRoot((dispose) => {
    made = createTypeTree({ type: "RoleType", feed: feed.open, api });
    cleanup = dispose;
  });
  return { ...made, feed, api };
}

test("the tree is loading until the feed sends it, and follows it", async () => {
  const { tree, feed } = start();
  expect(tree.state).toBe("loading");
  feed.push(TREE);
  await settle();
  expect(tree.state).toBe("ready");
  expect(tree.nodes.map((n) => n.id)).toEqual(["clerk", "advisor"]);
  feed.push(MOVED);
  await settle();
  expect(tree.nodes.map((n) => n.id)).toEqual(["clerk"]);
});

test("leaving the page closes the feed", async () => {
  const { feed } = start();
  await settle();
  expect(feed.opened).toHaveLength(1);
  cleanup?.();
  cleanup = undefined;
  expect(feed.opened[0]!.aborted).toBe(true);
});

test("a move is shown at once, and kept until the feed has it", async () => {
  let answer!: (value: unknown) => void;
  const { tree, feed, move, api } = start(() => new Promise((resolve) => (answer = resolve)));
  feed.push(TREE);
  await settle();
  const moving = move("advisor", "clerk");
  await settle();
  expect(api.post).toHaveBeenCalledWith("/typology/RoleType/advisor/move", { to: "clerk" });
  expect(parentOf(tree.nodes, "advisor")?.id).toBe("clerk");
  answer({});
  await settle();
  // (the feed has not brought it yet: still where it was dropped)
  expect(parentOf(tree.nodes, "advisor")?.id).toBe("clerk");
  feed.push(MOVED);
  await moving;
  await settle();
  expect(parentOf(tree.nodes, "advisor")?.id).toBe("clerk");
});

test("a move the server refuses is undone, and its promise rejects with why", async () => {
  const { tree, feed, move } = start(async () => {
    throw new ApiError(409, "A type cannot be moved below itself");
  });
  feed.push(TREE);
  await settle();
  await expect(move("advisor", "clerk")).rejects.toThrow(ApiError);
  await settle();
  expect(parentOf(tree.nodes, "advisor")).toBeUndefined();
});

test("a new label is shown at once, sent, and kept until the feed has it", async () => {
  const { tree, feed, rename, api } = start();
  feed.push(TREE);
  await settle();
  const renaming = rename("secretary", "Scribe");
  await settle();
  expect(api.patch).toHaveBeenCalledWith("/typology/RoleType/secretary", { label: "Scribe" });
  expect(findNode(tree.nodes, "secretary")?.label).toBe("Scribe");
  feed.push([{ id: "clerk", label: "Clerk", children: [leaf("secretary", "Scribe")] }, leaf("advisor", "Advisor")]);
  await renaming;
  await settle();
  expect(findNode(tree.nodes, "secretary")?.label).toBe("Scribe");
});

test("a label the server refuses is undone", async () => {
  const { tree, feed, rename } = start(async () => {
    throw new ApiError(422, "A label is needed");
  });
  feed.push(TREE);
  await settle();
  await expect(rename("secretary", "Scribe")).rejects.toThrow(ApiError);
  await settle();
  expect(findNode(tree.nodes, "secretary")?.label).toBe("Secretary");
});

test("a new type is shown once the API has made it, and kept until the feed has it", async () => {
  const { tree, feed, add, api } = start(async () => ({
    id: "scribe",
    label: "Scribe",
    labels: {},
    description: null,
    is_concrete: false,
    supertype: "clerk",
  }));
  feed.push(TREE);
  await settle();
  const made = await add({ label: "Scribe", supertype: "clerk" });
  expect(api.post).toHaveBeenCalledWith("/typology/RoleType", { label: "Scribe", supertype: "clerk" });
  expect(made.id).toBe("scribe");
  await settle();
  expect(parentOf(tree.nodes, "scribe")?.id).toBe("clerk");
  feed.push([{ id: "clerk", label: "Clerk", children: [leaf("scribe", "Scribe"), leaf("secretary", "Secretary")] }]);
  await settle();
  expect(parentOf(tree.nodes, "scribe")?.id).toBe("clerk");
});

test("a new type the API refuses rejects, and nothing is shown", async () => {
  const { tree, feed, add } = start(async () => {
    throw new ApiError(404, "There is no RoleType x");
  });
  feed.push(TREE);
  await settle();
  await expect(add({ label: "Scribe", supertype: "x" })).rejects.toThrow(ApiError);
  await settle();
  expect(findNode(tree.nodes, "scribe")).toBeUndefined();
});
