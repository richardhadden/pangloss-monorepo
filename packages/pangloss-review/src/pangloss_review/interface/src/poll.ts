import { ApiError, pause } from "@pangloss/interface-core";
import type { ReviewDetail } from "./api";

/** What the feed sends: the review of a document, or that it has none (not reviewed, or not for this reader) */
export type Snapshot = ({ reviewable: true } & ReviewDetail) | { reviewable: false };

/**
 * Asks for the review every `every` ms and yields it when it is not what was yielded last, until `signal` is aborted.
 * A document with no review (a 404: not reviewed; a 401 on the first ask: not logged in) is one `{ reviewable: false }`,
 * and the end. A 401 later (the access cookie ran out while the page was open) is thrown, so that the browser
 * reconnects, having refreshed its cookies; so is anything else that goes wrong (the API is down).
 */
export async function* pollReview(options: {
  fetchDetail: () => Promise<ReviewDetail>;
  every: number;
  signal?: AbortSignal;
  wait?: (ms: number, signal?: AbortSignal) => Promise<void>;
}): AsyncGenerator<Snapshot> {
  const wait = options.wait ?? pause;
  let last: string | undefined;
  while (!options.signal?.aborted) {
    let detail: ReviewDetail;
    try {
      detail = await options.fetchDetail();
    } catch (error) {
      const status = error instanceof ApiError ? error.status : 0;
      if (status === 404 || (status === 401 && last === undefined)) {
        yield { reviewable: false };
        return;
      }
      throw error;
    }
    const snapshot: Snapshot = { reviewable: true, ...detail };
    const text = JSON.stringify(snapshot);
    if (text !== last) {
      last = text;
      yield snapshot;
    }
    await wait(options.every, options.signal);
  }
}
