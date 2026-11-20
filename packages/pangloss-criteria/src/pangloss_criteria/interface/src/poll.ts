import { ApiError, pause } from "@pangloss/interface-core";
import type { CandidatesPage } from "./api";

/** What the feed of a description sends: its first candidates and how it stands, or `null` (no description the reader sees) */
export type Snapshot = CandidatesPage | null;

/** Whether the description has its result: evaluated since its document was last written (or no longer evaluated) */
export function settled(page: CandidatesPage): boolean {
  return page.broken !== null || (!page.pending && page.evaluatedWhen !== null);
}

/**
 * Asks for the candidates of a description every `every` ms and yields what it says when it is not what was yielded
 * last, until the description has its result (`settled`), which is the last yielded, or `signal` is aborted. So a
 * card that is drawn once its candidates are found asks once. A description the reader cannot see (a 404) is one
 * `null`, and the end; anything else that goes wrong is thrown, so that the browser connects again
 */
export async function* pollCandidates(options: {
  read: () => Promise<CandidatesPage>;
  every: number;
  signal?: AbortSignal;
  wait?: (ms: number, signal?: AbortSignal) => Promise<void>;
}): AsyncGenerator<Snapshot> {
  const wait = options.wait ?? pause;
  let last: string | undefined;
  while (!options.signal?.aborted) {
    let page: CandidatesPage;
    try {
      page = await options.read();
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        yield null;
        return;
      }
      throw error;
    }
    const text = JSON.stringify(page);
    if (text !== last) {
      last = text;
      yield page;
    }
    if (settled(page)) return;
    await wait(options.every, options.signal);
  }
}
