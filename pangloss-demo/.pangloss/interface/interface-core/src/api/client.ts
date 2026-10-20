/**
 * A client for the REST API (see docs/api.md). Only the shape is here so far.
 */
export interface ApiClientOptions {
  /** Where the API is, as seen by whoever makes the request (`/api` in a browser) */
  baseUrl: string;
  /** The `fetch` to use: on the server, one that passes on the cookies of the request */
  fetch?: typeof globalThis.fetch;
}

export interface ApiClient {
  readonly baseUrl: string;
  get<T>(path: string): Promise<T>;
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const doFetch = options.fetch ?? globalThis.fetch;
  return {
    baseUrl: options.baseUrl,
    async get<T>(path: string): Promise<T> {
      const response = await doFetch(`${options.baseUrl}${path}`, {
        headers: { Accept: "application/json" },
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
      return (await response.json()) as T;
    },
  };
}
