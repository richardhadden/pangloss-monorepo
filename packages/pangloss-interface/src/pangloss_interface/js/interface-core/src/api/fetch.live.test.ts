/**
 * Against a running API with the demo data (`pangloss dev` in pangloss-demo): skipped unless
 * `PANGLOSS_LIVE_API` names it, for example
 *
 *     PANGLOSS_LIVE_API=http://127.0.0.1:8000 npm test --workspace interface-core
 */
import { describe, expect, test } from "vitest";
import { ApiError, createApiClient } from "./client";
import { autocomplete, getCurrentUser, getItem, listItems, searchItems } from "./fetch";

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
});
