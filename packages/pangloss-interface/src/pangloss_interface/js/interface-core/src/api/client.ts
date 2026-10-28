/**
 * A client for the REST API (see docs/api.md).
 */
export interface ApiClientOptions {
  /** Where the API is, as seen by whoever makes the request (`/api` in a browser) */
  baseUrl: string;
  /** The `fetch` to use: on the server, one that passes on the cookies of the request */
  fetch?: typeof globalThis.fetch;
}

/** Values of a query string; those that are `undefined` (or empty) are left out */
export type QueryParams = Record<string, string | number | boolean | string[] | undefined>;

export interface ApiClient {
  readonly baseUrl: string;
  get<T>(path: string, query?: QueryParams): Promise<T>;
  post<T>(path: string, body: unknown): Promise<T>;
}

/** A response that was not a success: the status, and what the API said was wrong */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(`${status} ${detail}`);
    this.name = "ApiError";
  }
}

export function queryString(query: QueryParams = {}): string {
  const parameters = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    for (const item of Array.isArray(value) ? value : [value]) {
      if (item !== undefined && item !== "") parameters.append(key, String(item));
    }
  }
  const text = parameters.toString();
  return text ? `?${text}` : "";
}

// FastAPI answers `{"detail": "..."}`, or a list of problems for a 422
async function detailOf(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (body.detail !== undefined) return JSON.stringify(body.detail);
  } catch {
    // (not JSON)
  }
  return response.statusText;
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const doFetch = options.fetch ?? globalThis.fetch;
  async function request<T>(path: string, init: RequestInit): Promise<T> {
    const response = await doFetch(`${options.baseUrl}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init.headers },
      credentials: "include",
    });
    if (!response.ok) {
      throw new ApiError(response.status, await detailOf(response));
    }
    return (await response.json()) as T;
  }
  return {
    baseUrl: options.baseUrl,
    get: (path, query) => request(`${path}${queryString(query)}`, {}),
    post: (path, body) =>
      request(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
  };
}
