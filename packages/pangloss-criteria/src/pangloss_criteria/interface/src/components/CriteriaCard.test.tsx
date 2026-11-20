// @vitest-environment happy-dom
import { SessionProvider } from "@pangloss/interface-core";
import { afterEach, expect, test, vi } from "vitest";
import type { CandidatesPage } from "../api";
import { byTestId, CHARLES, cleanUp, fakeApi, MARIE, settle, show } from "../testing";

// (the card's feed is a server function, which a test has no server for: it says what `fed` holds, and the card
// keeps what the read gave; as in `ResolveDialog.test.tsx`)
const fed = vi.hoisted(() => ({ pages: [] as unknown[] }));
vi.mock("../feed", () => ({ candidatesFeed: () => undefined }));
vi.mock("@solidjs/web/server-functions", async (original) => ({
  ...(await original<typeof import("@solidjs/web/server-functions")>()),
  invoke: () =>
    (async function* () {
      yield* fed.pages;
    })(),
}));

const { default: CriteriaCard } = await import("./CriteriaCard");

afterEach(() => {
  cleanUp();
  fed.pages = [];
});

const DESCRIPTION = "00000000-0000-0000-0000-0000000000d1";
const REASON = "where.born: the field 'born' of Person was removed";

/** A description that a migration has put out of date: it keeps the candidates it had */
const broken = {
  id: DESCRIPTION,
  type: "MatchesCriteria",
  wording: "N. N., born in 1500",
  criteria: { type: "Person", where: { born: { eq: 1500 } } },
  target: [
    { type: "Person", id: MARIE, label: "Marie of Burgundy" },
    { type: "Person", id: CHARLES, label: "Charles the Bold" },
  ],
  candidateCount: 2,
  evaluatedWhen: "2026-11-19T10:00:00Z",
  broken: REASON,
  brokenSince: "demo_app.0024_remove_born",
};

function card(item: Record<string, unknown>) {
  const api = fakeApi(() => []);
  show(api.client, () => (
    <SessionProvider user={() => undefined}>
      <CriteriaCard type="MatchesCriteria" label="" item={item} context="embedded" />
    </SessionProvider>
  ));
  return api;
}

test("out of date since a migration: the migration, the reason under it, and the last candidates, marked so", async () => {
  card(broken);
  await vi.waitFor(() => expect(byTestId("criteria-card")).not.toBeNull());
  const notice = byTestId("criteria-broken")!;
  expect(notice.querySelector("p")?.textContent).toBe("Out of date since migration demo_app.0024_remove_born");
  expect(byTestId("criteria-broken-reason")?.textContent).toBe(REASON);
  // (the candidates it had are still shown, faded, and said to be the last found; not "updated …")
  expect(byTestId("criteria-candidates")?.textContent).toContain("Marie of Burgundy");
  expect(byTestId("criteria-candidates")?.textContent).toContain("Charles the Bold");
  expect(byTestId("criteria-candidates")?.hasAttribute("data-faded")).toBe(true);
  expect(byTestId("criteria-count")?.textContent).toBe("2 candidates · the last found: no longer kept up to date");
  expect(byTestId("criteria-finding")).toBeNull();
});

test("out of date with no migration to name: the reason in one line", async () => {
  card({ ...broken, brokenSince: null });
  await vi.waitFor(() => expect(byTestId("criteria-card")).not.toBeNull());
  expect(byTestId("criteria-broken")?.textContent).toBe(`Out of date: ${REASON}`);
  expect(byTestId("criteria-broken-reason")).toBeNull();
  expect(byTestId("criteria-candidates")?.textContent).toContain("Marie of Burgundy");
});

test("out of date while its document was written since: the last candidates, not Finding candidates…", async () => {
  card({ ...broken, evaluatedWhen: null });
  await vi.waitFor(() => expect(byTestId("criteria-card")).not.toBeNull());
  expect(byTestId("criteria-finding")).toBeNull();
  expect(byTestId("criteria-candidates")?.textContent).toContain("Marie of Burgundy");
});

test("out of date as the candidates route says it, after the read had it evaluated", async () => {
  const page: CandidatesPage = {
    count: 1,
    tooBroad: false,
    pending: false,
    evaluatedWhen: "2026-11-19T11:00:00Z",
    broken: REASON,
    brokenSince: "demo_app.0024_remove_born",
    page: 1,
    pageSize: 5,
    candidates: [{ type: "Person", id: MARIE, label: "Marie of Burgundy" }],
  };
  fed.pages = [page];
  const { broken: _reason, brokenSince: _since, ...evaluated } = broken;
  card(evaluated);
  await vi.waitFor(() =>
    expect(byTestId("criteria-broken")?.querySelector("p")?.textContent).toBe("Out of date since migration demo_app.0024_remove_born"),
  );
  expect(byTestId("criteria-count")?.textContent).toBe("1 candidate · the last found: no longer kept up to date");
});

test("one that is not out of date says nothing of it, and when it was updated", async () => {
  const { broken: _reason, brokenSince: _since, ...evaluated } = broken;
  card(evaluated);
  await vi.waitFor(() => expect(byTestId("criteria-card")).not.toBeNull());
  await settle();
  expect(byTestId("criteria-broken")).toBeNull();
  expect(byTestId("criteria-candidates")?.hasAttribute("data-faded")).toBe(false);
  expect(byTestId("criteria-count")?.textContent).toMatch(/^2 candidates · updated /);
});
