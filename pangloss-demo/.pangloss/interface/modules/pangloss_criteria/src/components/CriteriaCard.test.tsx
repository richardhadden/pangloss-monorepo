// @vitest-environment happy-dom
import { SessionProvider } from "@pangloss/interface-core";
import { afterEach, expect, test, vi } from "vitest";
import type { CandidatesPage } from "../api";
import { byTestId, CHARLES, citesSecretary, cleanUp, fakeApi, MARIE, SECRETARY, settle, show } from "../testing";

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

// --- a mention that cites a shared description ------------------------------------------------------------------------

const citing = (citation: Record<string, unknown>) => {
  const { broken: _reason, brokenSince: _since, ...evaluated } = broken;
  return { ...evaluated, criteria: { type: "Person", where: { born: { eq: 1501 } } }, description: citation };
};

test("one that cites a shared description: its chip, then + and the conditions of its own", async () => {
  card(citing(citesSecretary()));
  await vi.waitFor(() => expect(byTestId("criteria-card")).not.toBeNull());
  const summary = byTestId("criteria-shared-summary")!;
  expect(summary.querySelector('[data-testid="criteria-shared"] a')?.getAttribute("href")).toBe(`/Description/${SECRETARY}`);
  expect(summary.querySelector('[data-testid="criteria-shared"]')?.textContent).toContain("The duke's secretary");
  expect(summary.textContent).toContain("+");
  // (the class is not said twice: the conditions alone)
  expect(summary.querySelector('[data-testid="criteria-summary"]')?.textContent).toBe("born: 1501");
  expect(byTestId("criteria-shared-marks")).toBeNull();
});

test("one that cites with no conditions of its own: the chip alone", async () => {
  card({ ...citing(citesSecretary()), criteria: null });
  await vi.waitFor(() => expect(byTestId("criteria-card")).not.toBeNull());
  expect(byTestId("criteria-shared-summary")?.textContent).not.toContain("+");
  expect(byTestId("criteria-shared-summary")?.querySelector('[data-testid="criteria-summary"]')).toBeNull();
});

test("the shared description changed since cited: the mark under the bar, and no Seen on a page that is read", async () => {
  card(citing(citesSecretary({ changedSinceCited: true })));
  await vi.waitFor(() => expect(byTestId("criteria-shared-marks")).not.toBeNull());
  expect(byTestId("criteria-shared-marks")?.textContent).toContain("changed since cited");
  expect([...document.body.querySelectorAll("button")].some((each) => each.textContent === "Seen")).toBe(false);
});

test("the shared description removed since cited: its chip with no link, and the mark", async () => {
  card(citing(citesSecretary({ targetState: "removed", targetLabel: null, citedLabel: "The duke's secretary" })));
  await vi.waitFor(() => expect(byTestId("criteria-shared-marks")).not.toBeNull());
  expect(byTestId("criteria-shared")?.querySelector("a")).toBeNull();
  expect(byTestId("criteria-shared")?.textContent).toContain("The duke's secretary");
  expect(byTestId("criteria-shared-marks")?.textContent).toContain("removed since cited");
});

test("a place that is the same one as another, whose holder cites: the shared description as the route says it", async () => {
  fed.pages = [
    {
      count: 0,
      tooBroad: false,
      pending: false,
      evaluatedWhen: "2026-11-19T11:00:00Z",
      broken: null,
      page: 1,
      pageSize: 5,
      candidates: [],
      criteria: { type: "Person", where: { born: { eq: 1501 } } },
      places: 2,
      shared: { id: SECRETARY, label: "The duke's secretary", criteria: { type: "Person", where: { born: { eq: 1500 } } } },
    } satisfies CandidatesPage,
  ];
  card({ id: DESCRIPTION, type: "MatchesCriteria", wording: "him", criteria: null, sameOne: "00000000-0000-0000-0000-00000000000f" });
  await vi.waitFor(() => expect(byTestId("criteria-shared-summary")).not.toBeNull());
  expect(byTestId("criteria-same-one-mark")).not.toBeNull();
  expect(byTestId("criteria-shared")?.querySelector("a")?.getAttribute("href")).toBe(`/Description/${SECRETARY}`);
  expect(byTestId("criteria-shared-summary")?.querySelector('[data-testid="criteria-summary"]')?.textContent).toBe("born: 1501");
});

test("among what refers to a candidate: identified as candidate, the chip and its own conditions", async () => {
  const api = fakeApi(() => []);
  show(api.client, () => (
    <SessionProvider user={() => undefined}>
      <CriteriaCard type="MatchesCriteria" label="" item={citing(citesSecretary())} context="embedded" incoming />
    </SessionProvider>
  ));
  await vi.waitFor(() => expect(byTestId("criteria-as-candidate")).not.toBeNull());
  expect(byTestId("criteria-as-candidate")?.textContent).toContain("identified as candidate");
  expect(byTestId("criteria-shared")?.textContent).toContain("The duke's secretary");
  expect(byTestId("criteria-shared-summary")?.querySelector('[data-testid="criteria-summary"]')?.textContent).toBe("born: 1501");
});
