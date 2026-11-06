import type { TreeNode } from "./api";

/** Waits `ms`, or until `signal` is aborted */
export function pause(ms: number, signal?: AbortSignal): Promise<void> {
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

/**
 * Asks for the tree every `every` ms and yields it when it is not what was yielded last, until `signal` is aborted.
 * What goes wrong (the API is down, the access cookie ran out) is thrown, so that the browser connects again.
 */
export async function* pollTree(options: {
  fetchTree: () => Promise<TreeNode[]>;
  every: number;
  signal?: AbortSignal;
  wait?: (ms: number, signal?: AbortSignal) => Promise<void>;
}): AsyncGenerator<TreeNode[]> {
  const wait = options.wait ?? pause;
  let last: string | undefined;
  while (!options.signal?.aborted) {
    const nodes = await options.fetchTree();
    const text = JSON.stringify(nodes);
    if (text !== last) {
      last = text;
      yield nodes;
    }
    await wait(options.every, options.signal);
  }
}
