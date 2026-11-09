import { expect, test } from "vitest";
import type { Job, JobKind, Jobs } from "./api";
import { defaultOptions, formatSize, kindIsActive } from "./jobs";
import { pollJobs } from "./poll";

const job = (kind: string, state: Job["state"]) => ({ kind, state }) as Job;

test("a kind is active while a job of it is queued or running", () => {
  expect(kindIsActive([job("a", "running")], "a")).toBe(true);
  expect(kindIsActive([job("a", "queued")], "a")).toBe(true);
  expect(kindIsActive([job("a", "running")], "b")).toBe(false);
  expect(kindIsActive([job("a", "finished"), job("a", "interrupted")], "a")).toBe(false);
});

test("the form starts from each option's default", () => {
  const kind: JobKind = {
    name: "k",
    options: [
      { name: "format", type: "choice", default: "nq", values: ["nq", "trig"] },
      { name: "deep", type: "flag", default: false },
    ],
  };
  expect(defaultOptions(kind)).toEqual({ format: "nq", deep: false });
});

test("sizes are readable", () => {
  expect(formatSize(500)).toBe("500 B");
  expect(formatSize(1500)).toBe("1.5 KB");
  expect(formatSize(88_000_000)).toBe("88.0 MB");
  expect(formatSize(2_400_000_000)).toBe("2.4 GB");
});

test("the poll yields only what has changed, and throws an error so that the browser connects again", async () => {
  const empty: Jobs = { kinds: [], jobs: [] };
  const other: Jobs = { kinds: [{ name: "k", options: [] }], jobs: [] };
  const answers: (Jobs | Error)[] = [empty, empty, other, new Error("gone")];
  let asked = 0;
  const waits: number[] = [];
  const got: Jobs[] = [];
  let thrown: unknown;
  try {
    for await (const jobs of pollJobs({
      fetchJobs: async () => {
        const answer = answers[asked++]!;
        if (answer instanceof Error) throw answer;
        return answer;
      },
      every: 1000,
      wait: async (ms) => void waits.push(ms),
    }))
      got.push(jobs);
  } catch (error) {
    thrown = error;
  }
  expect(got).toEqual([empty, other]);
  expect(waits).toEqual([1000, 1000, 1000]);
  expect((thrown as Error).message).toBe("gone");
});
