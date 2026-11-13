// @vitest-environment happy-dom
import { afterEach, expect, test, vi } from "vitest";
import { ApiError, keepSessionAlive, withSessionRenewal } from "./client";
import type { ApiClient } from "./client";

// A client whose access cookie has run out: everything is refused until a refresh succeeds (or a login, by `logIn`)
function expiredClient(refreshWorks: boolean) {
  let fresh = false;
  const calls: string[] = [];
  const answer = async (path: string) => {
    calls.push(path);
    if (path === "/users/session/refresh") {
      if (!refreshWorks) throw new ApiError(401, "Invalid or expired refresh token");
      fresh = true;
      return { message: "success", expires_in: 1800 };
    }
    if (!fresh) throw new ApiError(401, "Not logged in");
    return { ok: path };
  };
  const client = {
    baseUrl: "/api",
    get: (path: string) => answer(path),
    post: (path: string) => answer(path),
    put: (path: string) => answer(path),
    patch: (path: string) => answer(path),
    postForm: (path: string) => answer(path),
    delete: (path: string) => answer(path),
  } as unknown as ApiClient;
  return { client, calls, logIn: () => (fresh = true) };
}

afterEach(() => {
  vi.useRealTimers();
});

test("a request refused because the access cookie ran out gets a new one and is sent again, unseen", async () => {
  const { client, calls } = expiredClient(true);
  const lost = vi.fn(async () => false);
  const renewing = withSessionRenewal(client, { lost });
  expect(await renewing.post("/Person", {})).toEqual({ ok: "/Person" });
  expect(calls).toEqual(["/Person", "/users/session/refresh", "/Person"]);
  expect(lost).not.toHaveBeenCalled();
});

test("requests refused together share one renewal", async () => {
  const { client, calls } = expiredClient(true);
  const renewing = withSessionRenewal(client, { lost: async () => false });
  await Promise.all([renewing.get("/a"), renewing.get("/b"), renewing.get("/c")]);
  expect(calls.filter((path) => path === "/users/session/refresh")).toHaveLength(1);
});

test("when no new cookie can be had, the person is asked once to log in, and the requests wait and go on", async () => {
  const { client, calls, logIn } = expiredClient(false);
  let answer: (yes: boolean) => void = () => {};
  const lost = vi.fn(
    () =>
      new Promise<boolean>((resolve) => {
        answer = resolve;
      }),
  );
  const renewing = withSessionRenewal(client, { lost });
  const both = Promise.all([renewing.put("/Person/1", {}), renewing.delete("/Person/2")]);
  await vi.waitFor(() => expect(lost).toHaveBeenCalledTimes(1));
  logIn();
  answer(true);
  expect(await both).toEqual([{ ok: "/Person/1" }, { ok: "/Person/2" }]);
  expect(calls.filter((path) => path === "/Person/1")).toHaveLength(2);
});

test("declined, the request fails with its 401", async () => {
  const { client } = expiredClient(false);
  const renewing = withSessionRenewal(client, { lost: async () => false });
  await expect(renewing.post("/Person", {})).rejects.toMatchObject({ status: 401 });
});

test("the 401s of logging in, renewing and asking who is logged in are answers, and are not renewed", async () => {
  const { client, calls } = expiredClient(true);
  const lost = vi.fn(async () => true);
  const renewing = withSessionRenewal(client, { lost });
  await expect(renewing.get("/users/me")).rejects.toMatchObject({ status: 401 });
  await expect(renewing.postForm("/users/session", { username: "a", password: "b" })).rejects.toMatchObject({
    status: 401,
  });
  expect(calls).toEqual(["/users/me", "/users/session"]);
  expect(lost).not.toHaveBeenCalled();
});

test("other errors are passed on as they are", async () => {
  const client = { baseUrl: "/api", get: async () => Promise.reject(new ApiError(404, "Not found")) } as unknown as ApiClient;
  const lost = vi.fn(async () => true);
  await expect(withSessionRenewal(client, { lost }).get("/Person/x")).rejects.toMatchObject({ status: 404 });
  expect(lost).not.toHaveBeenCalled();
});

test("kept alive, the cookie is renewed at once and again at three quarters of its life, until stopped", async () => {
  vi.useFakeTimers();
  const renew = vi.fn(async () => 100);
  const stop = keepSessionAlive(renew);
  await vi.advanceTimersByTimeAsync(0);
  expect(renew).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(74_000);
  expect(renew).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1_000);
  expect(renew).toHaveBeenCalledTimes(2);
  stop();
  await vi.advanceTimersByTimeAsync(200_000);
  expect(renew).toHaveBeenCalledTimes(2);
});
