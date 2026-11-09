import { createApiClient } from "@pangloss/interface-core";
import { getRequestEvent } from "@solidjs/web";
import { live } from "@solidjs/web/server-functions";
import { getJobs } from "./api";
import { pollJobs } from "./poll";

/**
 * The jobs as they change, while the page is open. The generator runs on the interface's server and asks the API with
 * the cookies of the request that opened the stream, so the API's own check for an admin applies to each caller, every
 * `PANGLOSS_ADMIN_POLL_MS` (1000) ms. What it reads is a few small files: no load on the database.
 */
export const jobsFeed = live(async function* () {
  "use server";
  const event = getRequestEvent();
  const cookie = event?.request.headers.get("cookie");
  const base = process.env.PANGLOSS_API_URL || "http://127.0.0.1:8000";
  const client = createApiClient({
    baseUrl: `${base}/api`,
    fetch: cookie ? (url, init) => fetch(url, { ...init, headers: { ...init?.headers, cookie } }) : undefined,
  });
  yield* pollJobs({
    fetchJobs: () => getJobs(client),
    every: Number(process.env.PANGLOSS_ADMIN_POLL_MS) || 1000,
    signal: event?.request.signal,
  });
});
