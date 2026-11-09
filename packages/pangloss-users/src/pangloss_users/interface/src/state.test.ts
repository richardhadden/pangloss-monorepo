// @vitest-environment happy-dom
import type { ApiClient } from "@pangloss/interface-core";
import { createRoot, flush } from "solid-js";
import { expect, test, vi } from "vitest";
import type { AccessToken, User } from "./api";
import { createTokensAdmin, createUsersAdmin } from "./state";
import type { FeedSource } from "./state";

function controlledFeed<T>() {
  const queue: T[][] = [];
  let wake: (() => void) | undefined;
  const open = (signal: AbortSignal): FeedSource<T[]> => {
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
    push(items: T[]) {
      queue.push(items);
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

const ann: User = { username: "ann", email: "ann@example.com", admin: false, disabled: false };
const zed: User = { username: "zed", email: "zed@example.com", admin: false, disabled: false };

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

const fakeApi = (write: () => Promise<unknown>) =>
  ({ baseUrl: "/api", get: vi.fn(), post: vi.fn(write), put: vi.fn(write), patch: vi.fn(write), delete: vi.fn(write) }) as unknown as ApiClient;

function users(write: () => Promise<unknown>) {
  const feed = controlledFeed<User>();
  let dispose!: () => void;
  const admin = createRoot((end) => {
    dispose = end;
    return createUsersAdmin({ feed: feed.open, api: fakeApi(write) });
  });
  return { admin, feed, dispose };
}

test("a change is shown at once and kept until the feed brings it", async () => {
  const request = deferred<User>();
  const { admin, feed, dispose } = users(() => request.promise);
  feed.push([ann]);
  await settle();

  const done = admin.setDisabled("ann", true);
  flush();
  expect(admin.view.items[0]!.disabled).toBe(true);

  request.resolve({ ...ann, disabled: true });
  await settle();
  // (the request is done; the feed has not said so)
  expect(admin.view.items[0]!.disabled).toBe(true);

  feed.push([{ ...ann, disabled: true }]);
  await done;
  await settle();
  expect(admin.view.items[0]!.disabled).toBe(true);
  dispose();
});

test("a change the API refuses is undone", async () => {
  const request = deferred<User>();
  const { admin, feed, dispose } = users(() => request.promise);
  feed.push([ann]);
  await settle();

  const done = admin.update("ann", { email: "taken@example.com" });
  flush();
  expect(admin.view.items[0]!.email).toBe("taken@example.com");

  request.reject(new Error("taken"));
  await expect(done).rejects.toThrow("taken");
  await settle();
  expect(admin.view.items[0]!.email).toBe("ann@example.com");
  dispose();
});

test("a new user is shown at once in order, without the password, and goes if refused", async () => {
  const request = deferred<User>();
  const { admin, feed, dispose } = users(() => request.promise);
  feed.push([ann, zed]);
  await settle();

  const accepted = vi.fn();
  const done = admin.add(
    { username: "bob", email: "bob@example.com", password: "secret", fullName: null, admin: false },
    accepted,
  );
  flush();
  expect(admin.view.items.map((user) => user.username)).toEqual(["ann", "bob", "zed"]);
  expect(admin.view.items[1]!.pending).toBe(true);
  expect(admin.view.items[1]).not.toHaveProperty("password");

  request.reject(new Error("exists"));
  await expect(done).rejects.toThrow("exists");
  await settle();
  expect(accepted).not.toHaveBeenCalled();
  expect(admin.view.items.map((user) => user.username)).toEqual(["ann", "zed"]);
  dispose();
});

test("a revoked token goes at once and comes back if refused", async () => {
  const token: AccessToken = { id: "t1", name: "script", scope: "write", createdWhen: "2026-11-09T00:00:00Z" };
  const request = deferred<void>();
  const feed = controlledFeed<AccessToken>();
  let dispose!: () => void;
  const tokens = createRoot((end) => {
    dispose = end;
    return createTokensAdmin({ username: "ann", feed: feed.open, api: fakeApi(() => request.promise) });
  });
  feed.push([token]);
  await settle();

  const done = tokens.revoke("t1");
  flush();
  expect(tokens.view.items).toHaveLength(0);

  request.reject(new Error("no"));
  await expect(done).rejects.toThrow("no");
  await settle();
  expect(tokens.view.items.map((item) => item.id)).toEqual(["t1"]);
  dispose();
});
