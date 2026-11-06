import { createApiClient } from "@pangloss/interface-core";
import { getRequestEvent, respond } from "@solidjs/web";
import { live } from "@solidjs/web/server-functions";
import { getReview } from "./api";
import { pollReview } from "./poll";

/**
 * The review of a document as it changes, while the page that asked is open: a `live()` server function. The
 * generator runs on the interface's server, which asks the API (`PANGLOSS_API_URL`) with the cookies of the request
 * that opened the stream, every `PANGLOSS_REVIEW_POLL_MS` (3000) ms, and sends a snapshot when it changed. Closing
 * the stream (the page is left) aborts the request, and the loop ends.
 */
export const reviewFeed = live(async function* (id: string) {
  "use server";
  if (typeof id !== "string" || id === "" || id.length > 2000) {
    throw respond({ detail: "an id is needed" }, { status: 400 });
  }
  const event = getRequestEvent();
  const cookie = event?.request.headers.get("cookie");
  const base = process.env.PANGLOSS_API_URL || "http://127.0.0.1:8000";
  const client = createApiClient({
    baseUrl: `${base}/api`,
    fetch: cookie ? (url, init) => fetch(url, { ...init, headers: { ...init?.headers, cookie } }) : undefined,
  });
  yield* pollReview({
    fetchDetail: () => getReview(client, id),
    every: Number(process.env.PANGLOSS_REVIEW_POLL_MS) || 3000,
    signal: event?.request.signal,
  });
});
