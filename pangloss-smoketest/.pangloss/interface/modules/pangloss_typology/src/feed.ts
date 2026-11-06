import { createApiClient } from "@pangloss/interface-core";
import { getRequestEvent, respond } from "@solidjs/web";
import { live } from "@solidjs/web/server-functions";
import { getTree } from "./api";
import { pollTree } from "./poll";

/**
 * The hierarchy of a typology as it changes, while the page that asked is open: a `live()` server function. The
 * generator runs on the interface's server, which asks the API (`PANGLOSS_API_URL`) with the cookies of the request
 * that opened the stream (someone logged in may see unpublished types), every `PANGLOSS_TYPOLOGY_POLL_MS` (3000) ms,
 * and sends the tree when it changed. Closing the stream (the page is left) aborts the request, and the loop ends.
 */
export const treeFeed = live(async function* (type: string) {
  "use server";
  if (typeof type !== "string" || type === "" || type.length > 200) {
    throw respond({ detail: "a typology is needed" }, { status: 400 });
  }
  const event = getRequestEvent();
  const cookie = event?.request.headers.get("cookie");
  const base = process.env.PANGLOSS_API_URL || "http://127.0.0.1:8000";
  const client = createApiClient({
    baseUrl: `${base}/api`,
    fetch: cookie ? (url, init) => fetch(url, { ...init, headers: { ...init?.headers, cookie } }) : undefined,
  });
  yield* pollTree({
    fetchTree: () => getTree(client, type),
    every: Number(process.env.PANGLOSS_TYPOLOGY_POLL_MS) || 3000,
    signal: event?.request.signal,
  });
});
