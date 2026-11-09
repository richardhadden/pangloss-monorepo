import type { Jobs } from "./api";

function pause(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal?.aborted) return resolve();
    const done = () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", done);
      resolve();
    };
    const timer = setTimeout(done, ms);
    signal?.addEventListener("abort", done, { once: true });
  });
}

/** Asks every `every` ms and yields what it is told when that has changed, until `signal` is aborted. An error is thrown, so that the browser connects again */
export async function* pollJobs(options: {
  fetchJobs: () => Promise<Jobs>;
  every: number;
  signal?: AbortSignal;
  wait?: (ms: number, signal?: AbortSignal) => Promise<void>;
}): AsyncGenerator<Jobs> {
  const wait = options.wait ?? pause;
  let last: string | undefined;
  while (!options.signal?.aborted) {
    const jobs = await options.fetchJobs();
    const text = JSON.stringify(jobs);
    if (text !== last) {
      last = text;
      yield jobs;
    }
    await wait(options.every, options.signal);
  }
}
