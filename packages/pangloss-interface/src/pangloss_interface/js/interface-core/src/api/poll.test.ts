import { expect, test } from "vitest";
import { pause, pollChanges } from "./poll";

test("only an answer that has changed is sent on, and each wait is as long as asked", async () => {
  const answers = [["a"], ["a"], ["a", "b"], ["a", "b"]];
  const abort = new AbortController();
  const seen: string[][] = [];
  const waits: number[] = [];
  for await (const answer of pollChanges({
    read: async () => answers.shift() as string[],
    every: 3000,
    signal: abort.signal,
    wait: async (ms) => {
      waits.push(ms);
      if (answers.length === 0) abort.abort();
    },
  })) {
    seen.push(answer);
  }
  expect(seen).toEqual([["a"], ["a", "b"]]);
  expect(waits).toEqual([3000, 3000, 3000, 3000]);
});

test("a failed read is thrown, so that the browser connects again", async () => {
  const feed = pollChanges({ read: () => Promise.reject(new Error("no")), every: 0 });
  await expect(feed.next()).rejects.toThrow("no");
});

test("an aborted poll asks nothing", async () => {
  const abort = new AbortController();
  abort.abort();
  let asked = 0;
  const seen: number[] = [];
  for await (const answer of pollChanges({ read: async () => ++asked, every: 1, signal: abort.signal })) seen.push(answer);
  expect(asked).toBe(0);
  expect(seen).toEqual([]);
});

test("a pause ends when its time is up", async () => {
  const started = Date.now();
  await pause(20);
  expect(Date.now() - started).toBeGreaterThanOrEqual(15);
});

test("a pause ends at once when it is aborted, or was already", async () => {
  const abort = new AbortController();
  const started = Date.now();
  const waiting = pause(60_000, abort.signal);
  abort.abort();
  await waiting;
  await pause(60_000, abort.signal);
  expect(Date.now() - started).toBeLessThan(1000);
});
