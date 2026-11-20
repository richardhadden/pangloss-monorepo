import { createRequestApiClient } from "@pangloss/interface-core";
import { getRequestEvent, respond } from "@solidjs/web";
import { live } from "@solidjs/web/server-functions";
import { candidatesPage, SHOWN } from "./api";
import { pollCandidates } from "./poll";

/**
 * The first candidates of a description and how it stands, until the worker has given it its result: a `live()`
 * server function. The generator runs on the interface's server, which asks the API (`PANGLOSS_API_URL`) with the
 * cookies of the request that opened the stream, every `PANGLOSS_CRITERIA_POLL_MS` (2000) ms, and ends when the
 * description is evaluated (`pollCandidates`). Closing the stream (the page is left) aborts the request.
 */
export const candidatesFeed = live(async function* (id: string) {
  "use server";
  if (typeof id !== "string" || id === "" || id.length > 200) {
    throw respond({ detail: "an id is needed" }, { status: 400 });
  }
  const event = getRequestEvent();
  const client = createRequestApiClient(event?.request);
  yield* pollCandidates({
    read: () => candidatesPage(client, id, 1, SHOWN),
    every: Number(process.env.PANGLOSS_CRITERIA_POLL_MS) || 2000,
    signal: event?.request.signal,
  });
});
