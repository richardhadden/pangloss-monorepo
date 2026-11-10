import { createRoot } from "solid-js";
import { expect, test } from "vitest";
import type { ApiClient, LiveSource } from "../api";
import { createFeedReader } from "./liveFeed";

const tick = () => new Promise((resolve) => setTimeout(resolve));

/** Feeds that say what they are given and then wait, as a live one does, until they are aborted */
function feeds<T>(answers: T[]) {
  const opened: { signal: AbortSignal; source: LiveSource<T> }[] = [];
  const open = (signal: AbortSignal): LiveSource<T> => {
    const source: LiveSource<T> = {
      async *[Symbol.asyncIterator]() {
        for (const answer of answers) yield answer;
        await new Promise<void>((_, reject) => signal.addEventListener("abort", () => reject(new Error("aborted"))));
      },
    };
    opened.push({ signal, source });
    return source;
  };
  return { open, opened };
}

function client() {
  const posted: string[] = [];
  const api = { post: async (path: string) => void posted.push(path) } as unknown as ApiClient;
  return { api, posted };
}

/** Reads a run of the reader into a list, in a root (which is "the page") */
function follow<T>(read: () => AsyncGenerator<T>) {
  const got: T[] = [];
  let failed: unknown;
  let finished = false;
  const dispose = createRoot((dispose) => {
    void (async () => {
      try {
        for await (const answer of read()) got.push(answer);
      } catch (error) {
        failed = error;
      }
      finished = true;
    })();
    return dispose;
  });
  return { got, dispose, failed: () => failed, finished: () => finished };
}

test("what the feed says is passed on, and leaving the page closes the feed without an error", async () => {
  const { open, opened } = feeds([1, 2]);
  const run = follow(createFeedReader(open, client().api));
  await tick();
  expect(run.got).toEqual([1, 2]);
  expect(opened).toHaveLength(1);
  expect(opened[0]!.signal.aborted).toBe(false);
  run.dispose();
  await tick();
  expect(opened[0]!.signal.aborted).toBe(true);
  expect(run.finished()).toBe(true);
  expect(run.failed()).toBeUndefined();
});

test("a run that replaces another closes the other's connection first", async () => {
  const { open, opened } = feeds(["a"]);
  const read = createFeedReader(open, client().api);
  const first = follow(read);
  await tick();
  const second = follow(read);
  await tick();
  expect(opened).toHaveLength(2);
  expect(opened[0]!.signal.aborted).toBe(true);
  expect(opened[1]!.signal.aborted).toBe(false);
  expect(first.finished()).toBe(true);
  expect(second.got).toEqual(["a"]);
  second.dispose();
  first.dispose();
});

test("a feed that fails while it is wanted throws, so that the page can say so", async () => {
  const open = (): LiveSource<number> => ({
    async *[Symbol.asyncIterator]() {
      yield 1;
      throw new Error("the API is down");
    },
  });
  const run = follow(createFeedReader(open, client().api));
  await tick();
  expect(run.got).toEqual([1]);
  expect((run.failed() as Error).message).toBe("the API is down");
  run.dispose();
});

test("a reconnect asks for a new access cookie, and nothing else does", async () => {
  const { open, opened } = feeds([1]);
  const { api, posted } = client();
  const run = follow(createFeedReader(open, api));
  await tick();
  opened[0]!.source.onstatus?.("connected");
  expect(posted).toEqual([]);
  opened[0]!.source.onstatus?.("reconnecting");
  await tick();
  expect(posted).toEqual(["/users/session/refresh"]);
  run.dispose();
});
