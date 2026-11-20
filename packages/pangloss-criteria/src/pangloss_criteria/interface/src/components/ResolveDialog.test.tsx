// @vitest-environment happy-dom
import { ApiError, SessionProvider, ToastsProvider, useToasts } from "@pangloss/interface-core";
import type { User } from "@pangloss/interface-core";
import { revalidate } from "@solidjs/router";
import { For } from "solid-js";
import { afterEach, expect, test, vi } from "vitest";
import type { CandidatesPage } from "../api";
import { button, byTestId, CHARLES, cleanUp, click, fakeApi, MARIE, settle, show } from "../testing";

vi.mock("@solidjs/router", async (original) => ({
  ...(await original<typeof import("@solidjs/router")>()),
  revalidate: vi.fn(),
}));
// (the card's feed is a server function, which a test has no server for: it says what `fed` holds (nothing, unless a
// test puts pages there), and the card keeps what the read gave)
const fed = vi.hoisted(() => ({ pages: [] as unknown[] }));
vi.mock("../feed", () => ({ candidatesFeed: () => undefined }));
vi.mock("@solidjs/web/server-functions", async (original) => ({
  ...(await original<typeof import("@solidjs/web/server-functions")>()),
  invoke: () =>
    (async function* () {
      yield* fed.pages;
    })(),
}));

const { default: ResolveDialog } = await import("./ResolveDialog");
const { default: CriteriaCard } = await import("./CriteriaCard");

afterEach(() => {
  cleanUp();
  fed.pages = [];
  vi.mocked(revalidate).mockClear();
});

const DESCRIPTION = "00000000-0000-0000-0000-0000000000d1";

const page = (...people: [string, string][]): CandidatesPage => ({
  count: people.length,
  tooBroad: false,
  pending: false,
  evaluatedWhen: "2026-11-19T10:00:00Z",
  broken: null,
  page: 1,
  pageSize: 25,
  candidates: people.map(([id, label]) => ({ type: "Person", id, label })),
});

function ShownToasts() {
  const toasts = useToasts();
  return (
    <ul>
      <For each={toasts?.toasts() ?? []}>
        {(toast) => (
          <li data-testid="toast" data-tone={toast.tone}>
            {toast.message}
          </li>
        )}
      </For>
    </ul>
  );
}

function open(answer: (path: string, body: unknown) => unknown, places: { places?: number | null; marked?: boolean } = {}) {
  const api = fakeApi(answer);
  const close = vi.fn();
  show(api.client, () => (
    <ToastsProvider>
      <ResolveDialog id={DESCRIPTION} places={places.places} marked={places.marked} onClose={close} />
      <ShownToasts />
    </ToastsProvider>
  ));
  return { asked: api.asked, close };
}

const resolving = (asked: { path: string; body: unknown }[]) =>
  asked.filter((each) => each.path === `/criteria/${DESCRIPTION}/resolve`);

test("the candidates are listed, each with a button; the one chosen is asked about once, then put in its place", async () => {
  const { asked, close } = open((path) =>
    path.endsWith("/resolve")
      ? { head: { type: "Sighting", id: "s1", label: "Seen" }, entity: { type: "Person", id: MARIE, label: null }, version: 2 }
      : page([CHARLES, "Charles the Bold"], [MARIE, "Marie of Burgundy"]),
  );
  await vi.waitFor(() => expect(document.body.querySelectorAll("[data-testid=criteria-candidate-row]")).toHaveLength(2));
  const rows = [...document.body.querySelectorAll<HTMLElement>("[data-testid=criteria-candidate-row]")];
  expect(rows.map((row) => row.querySelector("a")?.textContent)).toEqual([
    expect.stringContaining("Charles the Bold"),
    expect.stringContaining("Marie of Burgundy"),
  ]);
  expect(asked[0]).toEqual({ path: `/criteria/${DESCRIPTION}/candidates`, body: { page: 1, page_size: 25 } });

  // (chosen: asked about, and nothing sent yet)
  click(rows[1]!.querySelector("button"));
  expect(byTestId("criteria-resolve-confirm")?.textContent).toContain("Marie of Burgundy");
  expect(resolving(asked)).toHaveLength(0);
  // (Back: the list again)
  click(button("Back"));
  await vi.waitFor(() => expect(document.body.querySelectorAll("[data-testid=criteria-candidate-row]")).toHaveLength(2));
  click(document.body.querySelectorAll<HTMLElement>("[data-testid=criteria-candidate-row] button")[1]);

  click(byTestId("criteria-resolve-submit"));
  await vi.waitFor(() => expect(close).toHaveBeenCalled());
  expect(resolving(asked).map((each) => each.body)).toEqual([{ entity: { type: "Person", id: MARIE } }]);
  // (the page reads its item again; and says what was done)
  expect(revalidate).toHaveBeenCalled();
  const toast = byTestId("toast");
  expect(toast?.dataset.tone).toBe("success");
  expect(toast?.textContent).toBe("Marie of Burgundy is now in the place of the description");
});

test("what the server refuses is said in a red toast, and the dialog stays", async () => {
  const { close } = open((path) => {
    if (path.endsWith("/resolve")) throw new ApiError(422, "Sighting does not take that in the place of the description");
    return page([MARIE, "Marie of Burgundy"]);
  });
  await vi.waitFor(() => expect(document.body.querySelector("[data-testid=criteria-candidate-row] button")).not.toBeNull());
  click(document.body.querySelector("[data-testid=criteria-candidate-row] button"));
  click(byTestId("criteria-resolve-submit"));
  await vi.waitFor(() => expect(byTestId("toast")).not.toBeNull());
  expect(byTestId("toast")?.dataset.tone).toBe("error");
  expect(byTestId("toast")?.textContent).toBe("Not resolved: Sighting does not take that in the place of the description");
  expect(close).not.toHaveBeenCalled();
  expect(revalidate).not.toHaveBeenCalled();
  expect(byTestId("criteria-resolve-submit")?.hasAttribute("disabled")).toBe(false);
});

test("with no candidates there is nothing to choose, and it says so", async () => {
  open(() => page());
  await vi.waitFor(() => expect(byTestId("criteria-no-candidates")).not.toBeNull());
  expect(byTestId("criteria-no-candidates")?.textContent).toBe("There are no candidates to choose from");
});

// --- the card -----------------------------------------------------------------------------------------------------

const ANN: User = { username: "ann", email: "ann@example.com", admin: false } as unknown as User;

const item = {
  id: DESCRIPTION,
  type: "MatchesCriteria",
  wording: "N. N., born in 1500",
  criteria: { type: "Person", where: { born: { eq: 1500 } } },
  target: [{ type: "Person", id: MARIE, label: "Marie of Burgundy" }],
  candidateCount: 1,
  evaluatedWhen: "2026-11-19T10:00:00Z",
};

function card(props: { incoming?: boolean; user?: User; item?: Record<string, unknown> }) {
  const api = fakeApi((path) => (path === "/references" ? [] : page([MARIE, "Marie of Burgundy"])));
  show(api.client, () => (
    <SessionProvider user={() => props.user}>
      <CriteriaCard type="MatchesCriteria" label="" item={props.item ?? item} context="embedded" incoming={props.incoming} />
    </SessionProvider>
  ));
}

test("in a list of what refers to a candidate it is the mark and the summary, not the candidates", async () => {
  card({ incoming: true, user: ANN });
  await vi.waitFor(() => expect(byTestId("criteria-as-candidate")).not.toBeNull());
  expect(byTestId("criteria-candidate-mark")?.textContent).toBe("identified as candidate");
  expect(byTestId("criteria-as-candidate")?.textContent).toBe("identified as candidate·Person · born: 1500");
  expect(byTestId("criteria-candidates")).toBeNull();
  expect(byTestId("criteria-this-is")).toBeNull();
  expect(byTestId("criteria-card")).toBeNull();
});

test("on its document's page someone logged in has This is… in its bar; a reader does not", async () => {
  card({ user: ANN });
  await vi.waitFor(() => expect(byTestId("criteria-card")).not.toBeNull());
  expect(byTestId("criteria-this-is")?.textContent).toBe("This is…");
  expect(byTestId("criteria-candidates")?.textContent).toContain("Marie of Burgundy");
  cleanUp();

  card({});
  await vi.waitFor(() => expect(byTestId("criteria-card")).not.toBeNull());
  expect(byTestId("criteria-candidates")?.textContent).toContain("Marie of Burgundy");
  expect(byTestId("criteria-this-is")).toBeNull();
});

// --- the same one in several places of a document ---------------------------------------------------------------------

const MARK = "00000000-0000-0000-0000-00000000000f";

/** A place that is the same one as another: the mark, its wording, no criteria */
const bare = {
  id: DESCRIPTION,
  type: "MatchesCriteria",
  wording: "the same man",
  criteria: null,
  sameOne: MARK,
  target: [{ type: "Person", id: MARIE, label: "Marie of Burgundy" }],
  candidateCount: 1,
  evaluatedWhen: "2026-11-19T10:00:00Z",
};

/** What the candidates route says of a place of a mark with two places */
const ofTheMark = { ...page([MARIE, "Marie of Burgundy"], [CHARLES, "Charles"]), criteria: { type: "Person", where: { born: { eq: 1500 } } }, places: 2 };

test("a place that is the same one as another says so, with the summary of the criteria the route gives, its wording and its candidates", async () => {
  fed.pages = [ofTheMark];
  card({ item: bare, user: ANN });
  await vi.waitFor(() => expect(byTestId("criteria-summary")?.textContent).toBe("Person · born: 1500"));
  expect(byTestId("criteria-same-one-mark")?.textContent).toBe("The same one as");
  expect(byTestId("criteria-wording")?.textContent).toBe("“the same man”");
  // (what the route says, not what the read gave)
  expect(byTestId("criteria-candidates")?.textContent).toContain("Charles");
  expect(byTestId("criteria-places")?.textContent).toBe("in 2 places of this document");
  expect(byTestId("criteria-this-is")?.textContent).toBe("This is…");
});

test("before the route has said, a place that is the same one as another has the mark and no summary", async () => {
  card({ item: bare });
  await vi.waitFor(() => expect(byTestId("criteria-card")).not.toBeNull());
  expect(byTestId("criteria-same-one-mark")?.textContent).toBe("The same one as");
  expect(byTestId("criteria-summary")).toBeNull();
  expect(byTestId("criteria-places")).toBeNull();
});

test("a holder of a mark with more places says how many; one with no mark says nothing of places", async () => {
  fed.pages = [ofTheMark];
  card({ item: { ...item, sameOne: MARK } });
  await vi.waitFor(() => expect(byTestId("criteria-places")?.textContent).toBe("in 2 places of this document"));
  expect(byTestId("criteria-same-one-mark")).toBeNull();
  expect(byTestId("criteria-count")?.textContent).toMatch(/^2 candidates · updated .* · in 2 places of this document$/);
  cleanUp();

  fed.pages = [{ ...page([MARIE, "Marie of Burgundy"]), criteria: item.criteria, places: 1 }];
  card({});
  await vi.waitFor(() => expect(byTestId("criteria-candidates")).not.toBeNull());
  await settle();
  expect(byTestId("criteria-places")).toBeNull();
});

test("on a candidate's page a place that is the same one as another says so, with its wording, and asks nothing", async () => {
  const api = fakeApi(() => {
    throw new Error("nothing is asked");
  });
  show(api.client, () => <CriteriaCard type="MatchesCriteria" label="" item={bare} context="embedded" incoming />);
  await vi.waitFor(() => expect(byTestId("criteria-as-candidate")).not.toBeNull());
  expect(byTestId("criteria-as-candidate")?.textContent).toBe(
    "identified as candidate·the same one as another description of this document·“the same man”",
  );
  expect(api.asked).toEqual([]);
});

test("resolving one of several places of the same one says that it is put in all of them", async () => {
  const { close } = open(
    (path) =>
      path.endsWith("/resolve")
        ? { head: { type: "Sighting", id: "s1", label: "Seen" }, entity: { type: "Person", id: MARIE, label: null }, version: 2 }
        : page([MARIE, "Marie of Burgundy"]),
    { places: 2, marked: true },
  );
  await vi.waitFor(() => expect(byTestId("criteria-resolve-places")).not.toBeNull());
  expect(byTestId("criteria-resolve-places")?.textContent).toBe("It is put in all 2 places of this document that are the same one.");
  click(document.body.querySelector("[data-testid=criteria-candidate-row] button"));
  expect(byTestId("criteria-resolve-confirm")?.textContent).toContain("It is put in all 2 places");
  click(byTestId("criteria-resolve-submit"));
  await vi.waitFor(() => expect(close).toHaveBeenCalled());
  expect(byTestId("toast")?.textContent).toBe("Marie of Burgundy is now in the 2 places of the description");
});

test("resolving: a mark whose places are not known yet says every place; no mark, nothing", async () => {
  open(() => page([MARIE, "Marie of Burgundy"]), { places: null, marked: true });
  await vi.waitFor(() => expect(byTestId("criteria-resolve-places")).not.toBeNull());
  expect(byTestId("criteria-resolve-places")?.textContent).toBe("It is put in every place of this document that is the same one.");
  cleanUp();

  open(() => page([MARIE, "Marie of Burgundy"]), { places: 1, marked: true });
  await vi.waitFor(() => expect(document.body.querySelector("[data-testid=criteria-candidate-row]")).not.toBeNull());
  expect(byTestId("criteria-resolve-places")).toBeNull();
});
