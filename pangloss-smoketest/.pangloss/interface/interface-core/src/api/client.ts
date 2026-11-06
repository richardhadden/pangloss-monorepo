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

/** What else a write can say: headers, such as `If-Match` (the version an update is based on) */
export interface WriteOptions {
  headers?: Record<string, string>;
}

export interface ApiClient {
  readonly baseUrl: string;
  get<T>(path: string, query?: QueryParams): Promise<T>;
  post<T>(path: string, body?: unknown, options?: WriteOptions): Promise<T>;
  put<T>(path: string, body?: unknown, options?: WriteOptions): Promise<T>;
  patch<T>(path: string, body?: unknown, options?: WriteOptions): Promise<T>;
  /** A form, as a browser sends one (`application/x-www-form-urlencoded`), which logging in wants */
  postForm<T>(path: string, fields: Record<string, string>): Promise<T>;
  delete<T>(path: string): Promise<T>;
}

/** A response that was not a success: the status, and what the API said was wrong */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    /** (what else the answer said, such as `currentVersion` of a 412) */
    readonly body?: Record<string, unknown>,
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
async function detailOf(response: Response): Promise<{ detail: string; body?: Record<string, unknown> }> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return { detail: body.detail, body };
    if (body.detail !== undefined) return { detail: JSON.stringify(body.detail), body };
    return { detail: response.statusText, body };
  } catch {
    // (not JSON)
  }
  return { detail: response.statusText };
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
      const { detail, body } = await detailOf(response);
      throw new ApiError(response.status, detail, body);
    }
    // (an answer with no content, such as a 204)
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }
  return {
    baseUrl: options.baseUrl,
    get: (path, query) => request(`${path}${queryString(query)}`, {}),
    post: (path, body, options) =>
      request(path, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...options?.headers },
        body: body === undefined ? undefined : JSON.stringify(body),
      }),
    put: (path, body, options) =>
      request(path, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...options?.headers },
        body: body === undefined ? undefined : JSON.stringify(body),
      }),
    patch: (path, body, options) =>
      request(path, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...options?.headers },
        body: body === undefined ? undefined : JSON.stringify(body),
      }),
    postForm: (path, fields) =>
      request(path, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams(fields).toString(),
      }),
    delete: (path) => request(path, { method: "DELETE" }),
  };
}

/**
 * What was wrong with a write, one line each. A 422 has a list of problems (`loc` and `msg`
 * each); anything else has a text. The location is joined with `›`, without the `body` the
 * API puts first.
 */
export function problemsOf(error: ApiError): string[] {
  try {
    const detail = JSON.parse(error.detail) as unknown;
    if (Array.isArray(detail)) {
      return detail.map((problem: { loc?: unknown[]; msg?: unknown }) => {
        const where = (problem.loc ?? []).filter((part) => part !== "body").join(" › ");
        const msg = typeof problem.msg === "string" ? problem.msg : JSON.stringify(problem);
        return where ? `${where}: ${msg}` : msg;
      });
    }
  } catch {
    // (a text, not JSON)
  }
  return [error.detail];
}
