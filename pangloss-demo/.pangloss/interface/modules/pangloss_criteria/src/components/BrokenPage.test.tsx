// @vitest-environment happy-dom
import { afterEach, expect, test, vi } from "vitest";
import type { BrokenDescription, BrokenPage } from "../api";
import { button, byTestId, cleanUp, click, fakeApi, MARIE, show } from "../testing";
import BrokenAdminSection from "./BrokenAdminSection";
import { BROKEN_PAGE_SIZE, BrokenList } from "./BrokenPage";

afterEach(cleanUp);

const SIGHTING = "00000000-0000-0000-0000-0000000000b1";

const description = (n: number, extra: Partial<BrokenDescription> = {}): BrokenDescription => ({
  id: `00000000-0000-0000-0000-0000000000${String(n).padStart(2, "0")}`,
  wording: `N. N. ${n}`,
  criteria: { type: "Person", where: { friend: { is: MARIE } } },
  broken: "where.office: the field 'office' of HoldsOffice was removed",
  brokenSince: "demo_app.0024_remove_office",
  head: { id: SIGHTING, type: "Sighting", label: `Seen at Ghent ${n}` },
  ...extra,
});

const pageOf = (count: number, results: BrokenDescription[], page = 1): BrokenPage => ({ count, page, pageSize: BROKEN_PAGE_SIZE, results });

function list(answer: (path: string, body: unknown) => unknown, page = 1) {
  const api = fakeApi(answer);
  const onPage = vi.fn();
  show(api.client, () => <BrokenList page={page} onPage={onPage} />);
  return { asked: api.asked, onPage };
}

const rows = () => [...document.body.querySelectorAll<HTMLElement>("[data-testid=criteria-broken-row]")];

test("each description out of date: its document as a chip, its wording and summary, since which migration and why, and its form", async () => {
  const { asked } = list((path) =>
    path === "/references"
      ? { found: [{ type: "Person", id: MARIE, label: "Marie of Burgundy" }] }
      : pageOf(2, [description(1), description(2, { brokenSince: null })]),
  );
  await vi.waitFor(() => expect(rows()).toHaveLength(2));
  expect(byTestId("criteria-broken-count")?.textContent).toBe("Out of date: 2");
  const [first, second] = rows();
  // (the document: a chip, to its page)
  const chip = first!.querySelector("td a")!;
  expect(chip.textContent).toContain("Seen at Ghent 1");
  expect(chip.getAttribute("href")).toBe(`/Sighting/${SIGHTING}`);
  expect(first!.querySelector("[data-testid=criteria-wording]")?.textContent).toBe("“N. N. 1”");
  await vi.waitFor(() => expect(first!.querySelector("[data-testid=criteria-summary]")?.textContent).toBe("Person · friend: PersonMarie of Burgundy"));
  expect(first!.querySelector("[data-testid=criteria-broken-since]")?.textContent).toBe("since migration demo_app.0024_remove_office");
  expect(first!.querySelector("[data-testid=criteria-broken-reason]")?.textContent).toBe(
    "where.office: the field 'office' of HoldsOffice was removed",
  );
  // (no migration to name: only the reason)
  expect(second!.querySelector("[data-testid=criteria-broken-since]")).toBeNull();
  // (to the form of its document, at the description)
  expect(first!.querySelector<HTMLAnchorElement>("[data-testid=criteria-broken-open]")?.getAttribute("href")).toBe(
    `/Sighting/${SIGHTING}/edit?show=${description(1).id}`,
  );
  // (asked once for the page, and once for the labels of every row's entities)
  expect(asked.filter((each) => each.path === "/criteria/broken").map((each) => each.body)).toEqual([{ page: 1, page_size: BROKEN_PAGE_SIZE }]);
  expect(asked.filter((each) => each.path === "/references")).toHaveLength(1);
});

test("a pattern that no longer fits the models is summarised as it is written", async () => {
  list((path) =>
    path === "/references"
      ? { found: [] }
      : pageOf(1, [description(1, { criteria: { type: "HoldsOffice", where: { office: { eq: "Secretary" }, $gone: [1] } } })]),
  );
  await vi.waitFor(() => expect(rows()).toHaveLength(1));
  expect(rows()[0]!.querySelector("[data-testid=criteria-summary]")?.textContent).toBe('HoldsOffice · office: Secretary, $gone: [1]');
});

test("none out of date: a sentence that says so", async () => {
  list(() => pageOf(0, []));
  await vi.waitFor(() => expect(byTestId("criteria-broken-none")).not.toBeNull());
  expect(byTestId("criteria-broken-none")?.textContent).toBe("No description is out of date.");
  expect(rows()).toHaveLength(0);
});

test("more than a page: the pager asks for the next; a later page is asked for as such", async () => {
  const { onPage } = list((path) => (path === "/references" ? { found: [] } : pageOf(30, [description(1)])));
  await vi.waitFor(() => expect(rows()).toHaveLength(1));
  expect(document.body.textContent).toContain("Page 1 of 2");
  click(button("Next"));
  expect(onPage).toHaveBeenCalledWith(2);
  cleanUp();

  const { asked } = list((path) => (path === "/references" ? { found: [] } : pageOf(30, [description(26)], 2)), 2);
  await vi.waitFor(() => expect(rows()).toHaveLength(1));
  expect(asked.find((each) => each.path === "/criteria/broken")?.body).toEqual({ page: 2, page_size: BROKEN_PAGE_SIZE });
  expect(document.body.textContent).toContain("Page 2 of 2");
});

test("on /admin: how many are out of date, and the link to the page", async () => {
  const api = fakeApi(() => pageOf(3, [description(1)]));
  show(api.client, () => <BrokenAdminSection />);
  await vi.waitFor(() => expect(byTestId("admin-criteria-broken-count")?.textContent).toBe("3 descriptions are out of date."));
  expect(byTestId("admin-criteria-broken")?.querySelector("a")?.getAttribute("href")).toBe("/criteria/broken");
  expect(api.asked).toEqual([{ path: "/criteria/broken", body: { page: 1, page_size: 1 } }]);
  cleanUp();

  show(fakeApi(() => pageOf(0, [])).client, () => <BrokenAdminSection />);
  await vi.waitFor(() => expect(byTestId("admin-criteria-broken-count")?.textContent).toBe("No description is out of date."));
});
