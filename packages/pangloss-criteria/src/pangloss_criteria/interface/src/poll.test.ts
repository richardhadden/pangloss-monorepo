import { ApiError } from "@pangloss/interface-core";
import { expect, test } from "vitest";
import type { CandidatesPage } from "./api";
import { pollCandidates } from "./poll";

const page = (more: Partial<CandidatesPage>): CandidatesPage => ({
  count: 0,
  tooBroad: false,
  pending: true,
  evaluatedWhen: null,
  broken: null,
  page: 1,
  pageSize: 5,
  candidates: [],
  ...more,
});

async function all<T>(source: AsyncGenerator<T>): Promise<T[]> {
  const seen: T[] = [];
  for await (const each of source) seen.push(each);
  return seen;
}

test("it asks until the description has its result, which is the last it says; the same answer is said once", async () => {
  const answers = [
    page({}),
    page({}),
    page({ pending: false, evaluatedWhen: "2026-11-19T10:00:00Z", count: 1 }),
    page({ count: 99 }),
  ];
  let asked = 0;
  const seen = await all(pollCandidates({ read: async () => answers[asked++]!, every: 1000, wait: async () => undefined }));
  expect(asked).toBe(3);
  expect(seen).toEqual([answers[0], answers[2]]);
});

test("one that is no longer evaluated has its result too", async () => {
  const seen = await all(pollCandidates({ read: async () => page({ broken: "a field has gone" }), every: 1, wait: async () => undefined }));
  expect(seen).toHaveLength(1);
});

test("a description the reader cannot see is one null; another failure is thrown", async () => {
  const gone = await all(pollCandidates({ read: () => Promise.reject(new ApiError(404, "no")), every: 1 }));
  expect(gone).toEqual([null]);
  await expect(all(pollCandidates({ read: () => Promise.reject(new ApiError(502, "down")), every: 1 }))).rejects.toThrow("502");
});
