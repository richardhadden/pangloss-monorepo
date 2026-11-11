import { afterEach, expect, test, vi } from "vitest";
import { createRequestApiClient, serverApiUrl } from "./requestClient";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function fetching() {
  const calls: { url: string; headers: Record<string, string> }[] = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    calls.push({ url: String(url), headers: { ...(init?.headers as Record<string, string>) } });
    return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
  });
  return calls;
}

test("the server asks the API where PANGLOSS_API_URL says it is, or on this machine", () => {
  vi.stubEnv("PANGLOSS_API_URL", "");
  expect(serverApiUrl()).toBe("http://127.0.0.1:8000");
  vi.stubEnv("PANGLOSS_API_URL", "http://api.example:9000");
  expect(serverApiUrl()).toBe("http://api.example:9000");
});

test("the cookies of the request being answered are passed on to the API", async () => {
  vi.stubEnv("PANGLOSS_API_URL", "http://api.example:9000");
  const calls = fetching();
  const request = new Request("http://interface.example/Person", { headers: { cookie: "access=abc" } });
  await createRequestApiClient(request).get("/Person");
  expect(calls).toHaveLength(1);
  expect(calls[0]!.url).toBe("http://api.example:9000/api/Person");
  expect(calls[0]!.headers.cookie).toBe("access=abc");
});

test("a request with no cookies, or no request, asks as nobody", async () => {
  vi.stubEnv("PANGLOSS_API_URL", "http://api.example:9000");
  const calls = fetching();
  await createRequestApiClient(new Request("http://interface.example/")).get("/Person");
  await createRequestApiClient().get("/Person");
  expect(calls).toHaveLength(2);
  expect(calls.map((call) => call.headers.cookie)).toEqual([undefined, undefined]);
});
