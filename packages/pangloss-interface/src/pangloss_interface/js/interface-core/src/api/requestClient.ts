import { createApiClient } from "./client";
import type { ApiClient } from "./client";

/** Where the interface's server finds the API: `PANGLOSS_API_URL`, which `pangloss interface dev` and `serve` set */
export function serverApiUrl(): string {
  // (through `globalThis`: a module that has no types of Node is checked with this file too)
  const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
  return env?.PANGLOSS_API_URL || "http://127.0.0.1:8000";
}

/**
 * A client of the API for code that runs on the interface's server (a render, a `live()` feed): it asks the API
 * directly, and passes on the cookies of `request` (the one being answered: `getRequestEvent()?.request`), so that
 * the API answers as it would the person who asked.
 */
export function createRequestApiClient(request?: Request): ApiClient {
  const cookie = request?.headers.get("cookie");
  return createApiClient({
    baseUrl: `${serverApiUrl()}/api`,
    fetch: cookie ? (url, init) => fetch(url, { ...init, headers: { ...init?.headers, cookie } }) : undefined,
  });
}
