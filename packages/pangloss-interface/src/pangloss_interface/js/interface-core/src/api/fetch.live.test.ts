/**
 * Against a running API with the demo data (`pangloss dev` in pangloss-demo): skipped unless
 * `PANGLOSS_LIVE_API` names it, for example
 *
 *     PANGLOSS_LIVE_API=http://127.0.0.1:8000 npm test --workspace interface-core
 */
import { describe, expect, test } from "vitest";
import { ApiError, createApiClient } from "./client";
import {
  autocomplete,
  getCurrentUser,
  getItem,
  listItems,
  logIn,
  logOut,
  searchItems,
} from "./fetch";

const base = process.env.PANGLOSS_LIVE_API;

describe.skipIf(!base)("the demo API", () => {
  const client = createApiClient({ baseUrl: `${base}/api` });

  test("a list, paged, and an item from it", async () => {
    const first = await listItems(client, "Place", { pageSize: 2 });
    expect(first.results).toHaveLength(2);
    expect(first.count).toBeGreaterThanOrEqual(2);
    expect(first.nextPage).toBe(2);
    const item = await getItem(client, "Place", first.results[0]!.id);
    expect(item).toMatchObject({ id: first.results[0]!.id, type: "Place", label: first.results[0]!.label });
    expect(item.meta.version).toBeGreaterThanOrEqual(1);
  });

  test("the list finds by label", async () => {
    const found = await listItems(client, "Place", { q: "rome" });
    expect(found.results.map((r) => r.label)).toContain("Rome");
  });

  test("an abstract type is listed, with the items of its subtypes", async () => {
    const statements = await listItems(client, "Statement", { pageSize: 5 });
    expect(statements.count).toBeGreaterThan(0);
    expect(statements.results.every((r) => r.type !== "Statement")).toBe(true);
  });

  test("autocomplete and search answer pages", async () => {
    expect((await autocomplete(client, { q: "rom", types: ["Place"] })).results.length).toBeGreaterThan(0);
    expect((await searchItems(client, { type: "Place", where: {} })).count).toBeGreaterThan(0);
  });

  test("a bad id is a 422 and an unknown one a 404; no one is logged in", async () => {
    await expect(getItem(client, "Place", "nope")).rejects.toMatchObject({ status: 422 });
    await expect(getItem(client, "Place", "00000000-0000-7000-8000-000000000000")).rejects.toBeInstanceOf(ApiError);
    expect(await getCurrentUser(client)).toBeUndefined();
  });

  // Node's fetch keeps no cookies: this one does, as a browser would
  function clientWithCookies() {
    const jar = new Map<string, string>();
    const withCookies: typeof fetch = async (url, init) => {
      const cookie = [...jar].map(([name, value]) => `${name}=${value}`).join("; ");
      const response = await fetch(url, {
        ...init,
        headers: { ...(init?.headers as Record<string, string>), ...(cookie ? { cookie } : {}) },
      });
      for (const line of response.headers.getSetCookie()) {
        const [pair = "", ...attributes] = line.split(";");
        const [name = "", value = ""] = pair.split("=");
        const gone = attributes.some((a) => /max-age=0/i.test(a)) || value === "" || value === '""';
        if (gone) jar.delete(name.trim());
        else jar.set(name.trim(), value.trim());
      }
      return response;
    };
    return { client: createApiClient({ baseUrl: `${base}/api`, fetch: withCookies }), jar };
  }

  test("logging in puts the session in cookies, which then are who you are; logging out ends it", async () => {
    const { client: browser, jar } = clientWithCookies();
    expect(await getCurrentUser(browser)).toBeUndefined();
    await expect(logIn(browser, "demo", "wrong password")).rejects.toMatchObject({ status: 401 });
    await logIn(browser, "demo", "demo-password");
    expect([...jar.keys()].sort()).toEqual(["pangloss_access", "pangloss_refresh"]);
    expect(await getCurrentUser(browser)).toMatchObject({ username: "demo" });
    // (the access cookie lost, the refresh cookie still there: a new one is asked for)
    jar.delete("pangloss_access");
    expect(await getCurrentUser(browser)).toBeUndefined();
    expect(await getCurrentUser(browser, { refresh: true })).toMatchObject({ username: "demo" });
    expect(jar.has("pangloss_access")).toBe(true);
    await logOut(browser);
    expect(jar.size).toBe(0);
    expect(await getCurrentUser(browser, { refresh: true })).toBeUndefined();
  });
});
