// @vitest-environment happy-dom
// (the dialog of a description with shared descriptions: "Start from" with Use and Copy, citing one, the offer to
// make identical criteria one)
import { ApiError } from "@pangloss/interface-core";
import { afterEach, expect, test, vi } from "vitest";
import type { Preview, ShareResult, Similar } from "../api";
import { addFilter, button, byLabel, byTestId, CHARLES, cleanUp, click, fakeApi, MARIE, SECRETARY, secretary, settle, show, type } from "../testing";
import { CriteriaDialog } from "./CriteriaDialog";
import type { CriteriaDone, CriteriaValue } from "./CriteriaDialog";

afterEach(cleanUp);

const found = (count: number): Preview => ({
  count,
  tooBroad: false,
  candidates: count > 0 ? [{ type: "Person", id: MARIE, label: "Marie of Burgundy" }] : [],
});

const listed = { count: 1, page: 1, pageSize: 5, results: [secretary] };
const none: Similar = { count: 0, documents: [] };

interface Answers {
  shared?: (query: Record<string, unknown>) => unknown;
  similar?: (body: Record<string, unknown>) => unknown;
  share?: (body: Record<string, unknown>) => unknown;
  preview?: (body: Record<string, unknown>) => unknown;
}

function open(answers: Answers = {}, value: CriteriaValue = { wording: "", criteria: null }, except: string | null = null) {
  const api = fakeApi((path, body) => {
    const given = (body ?? {}) as Record<string, unknown>;
    if (path === "/criteria/shared") return answers.shared ? answers.shared(given) : listed;
    if (path === "/criteria/similar") return answers.similar ? answers.similar(given) : none;
    if (path === "/criteria/share") return answers.share?.(given);
    if (path === "/criteria/preview") return answers.preview ? answers.preview(given) : found(1);
    if (path === `/Description/${SECRETARY}`) return { type: "Description", id: SECRETARY, label: secretary.label, criteria: secretary.criteria };
    return { found: [] };
  });
  const done = vi.fn((_: CriteriaDone) => undefined);
  show(api.client, () => (
    <CriteriaDialog types={["Person"]} value={value} named={() => [CHARLES]} except={except} onDone={done} onCancel={() => undefined} />
  ));
  return { asked: api.asked, done };
}

const ofPath = (asked: { path: string; body: unknown }[], path: string) => asked.filter((each) => each.path === path);
const startFrom = () => byTestId("criteria-start-from");
const rowButton = (name: string) =>
  [...startFrom()!.querySelectorAll<HTMLButtonElement>("button")].find((each) => each.textContent?.trim() === name);

test("Start from lists the shared descriptions of the classes the place takes, each with how many mentions use it", async () => {
  const { asked } = open();
  await vi.waitFor(() => expect(startFrom()).not.toBeNull());
  expect(ofPath(asked, "/criteria/shared")[0]!.body).toMatchObject({ types: "Person", page: 1, page_size: 5 });
  const row = byTestId("criteria-start-from-row")!;
  expect(row.querySelector("a")?.getAttribute("href")).toBe(`/Description/${SECRETARY}`);
  expect(row.textContent).toContain("The duke's secretary");
  expect(byTestId("criteria-shared-mentions")?.textContent).toBe("3 mentions");
  expect(row.querySelector('[data-testid="criteria-summary"]')?.textContent).toBe("Person · born: 1500");
});

test("Start from is not there when there is no shared description at all", async () => {
  const { asked } = open({ shared: () => ({ count: 0, page: 1, pageSize: 5, results: [] }) });
  await vi.waitFor(() => expect(ofPath(asked, "/criteria/shared")).toHaveLength(1));
  await settle();
  expect(startFrom()).toBeNull();
});

test("typing filters them, a moment after the last key, through q", async () => {
  const { asked } = open({
    shared: (query) => (query.q === "nobody" ? { count: 0, page: 1, pageSize: 5, results: [] } : listed),
  });
  await vi.waitFor(() => expect(startFrom()).not.toBeNull());
  type("Find a shared description", "nob");
  type("Find a shared description", "nobody");
  await settle(300);
  await vi.waitFor(() => expect(byTestId("criteria-start-from-none")).not.toBeNull());
  // (asked once for what was typed last, not for each key)
  expect(ofPath(asked, "/criteria/shared").map((each) => (each.body as Record<string, unknown>).q)).toEqual([undefined, "nobody"]);
  // (still there to be typed in again)
  expect(byLabel("Find a shared description")).not.toBeNull();
});

test("Use: the mention cites it; its criteria read only, a form for conditions of its own, the preview of both, Done with none", async () => {
  const { asked, done } = open();
  await vi.waitFor(() => expect(startFrom()).not.toBeNull());
  click(rowButton("Use"));
  await vi.waitFor(() => expect(byTestId("criteria-shared-head")).not.toBeNull());
  expect(startFrom()).toBeNull();
  const head = byTestId("criteria-shared-head")!;
  expect(head.querySelector("a")?.getAttribute("href")).toBe(`/Description/${SECRETARY}`);
  expect(head.querySelector('[data-testid="criteria-summary"]')?.textContent).toBe("Person · born: 1500");
  expect(document.body.querySelector('[aria-label="Criteria"]')?.textContent).toContain("And also, for this mention: Person");
  // (the preview is of the shared criteria alone so far: asked with the description, and no condition)
  await vi.waitFor(() => expect(ofPath(asked, "/criteria/preview")).toHaveLength(1));
  expect(ofPath(asked, "/criteria/preview")[0]!.body).toEqual({
    criteria: { type: "Person", where: {} },
    named: [CHARLES],
    description: SECRETARY,
  });
  expect(byTestId("criteria-need-condition")).toBeNull();
  await vi.waitFor(() => expect(button("Done")!.disabled).toBe(false));
  // (what is not its own is not offered to be shared)
  expect(ofPath(asked, "/criteria/similar")).toHaveLength(0);

  // (a condition of its own: the summary is the shared description, then it)
  addFilter("born");
  type("born", "1501");
  await settle(300);
  await vi.waitFor(() => expect(ofPath(asked, "/criteria/preview")).toHaveLength(2));
  expect(ofPath(asked, "/criteria/preview")[1]!.body).toEqual({
    criteria: { type: "Person", where: { born: { eq: 1501 } } },
    named: [CHARLES],
    description: SECRETARY,
  });
  const summary = byTestId("criteria-result")!.querySelector('[data-testid="criteria-shared-summary"]')!;
  expect(summary.querySelector('[data-testid="criteria-shared"]')?.textContent).toContain("The duke's secretary");
  expect(summary.querySelector('[data-testid="criteria-summary"]')?.textContent).toBe("born: 1501");
  await vi.waitFor(() => expect(byTestId("criteria-count")?.textContent).toBe("1 candidate found"));
  click(button("Done"));
  expect(done).toHaveBeenCalledWith({
    wording: "",
    criteria: { type: "Person", where: { born: { eq: 1501 } } },
    shared: { id: SECRETARY, label: "The duke's secretary" },
    preview: found(1),
  });
});

test("Done in the Use state with no condition of its own gives no criteria, and the shared description", async () => {
  const { done } = open();
  await vi.waitFor(() => expect(startFrom()).not.toBeNull());
  click(rowButton("Use"));
  await vi.waitFor(() => expect(button("Done")!.disabled).toBe(false));
  click(button("Done"));
  expect(done.mock.calls[0]![0]).toMatchObject({ criteria: null, shared: { id: SECRETARY, label: "The duke's secretary" } });
});

test("Stop using: the conditions of its own stay, now its criteria, and Start from is back", async () => {
  const { asked, done } = open();
  await vi.waitFor(() => expect(startFrom()).not.toBeNull());
  click(rowButton("Use"));
  await vi.waitFor(() => expect(byLabel("Add a filter")).not.toBeNull());
  addFilter("born");
  type("born", "1501");
  await settle(300);
  click(button("Stop using"));
  await vi.waitFor(() => expect((byLabel("born") as HTMLInputElement | null)?.value).toBe("1501"));
  expect(byTestId("criteria-shared-head")).toBeNull();
  await vi.waitFor(() => expect(startFrom()).not.toBeNull());
  // (asked of its own alone now)
  await vi.waitFor(() => expect(ofPath(asked, "/criteria/preview").at(-1)!.body).toEqual({ criteria: { type: "Person", where: { born: { eq: 1501 } } }, named: [CHARLES] }));
  click(button("Done"));
  expect(done.mock.calls[0]![0]).toMatchObject({ criteria: { type: "Person", where: { born: { eq: 1501 } } }, shared: null });
});

test("Copy: its criteria fill the form as the mention's own, with no link", async () => {
  const { done } = open();
  await vi.waitFor(() => expect(startFrom()).not.toBeNull());
  click(rowButton("Copy"));
  await vi.waitFor(() => expect((byLabel("born") as HTMLInputElement | null)?.value).toBe("1500"));
  expect(byTestId("criteria-shared-head")).toBeNull();
  await vi.waitFor(() => expect(button("Done")!.disabled).toBe(false));
  click(button("Done"));
  expect(done.mock.calls[0]![0]).toMatchObject({ criteria: { type: "Person", where: { born: { eq: 1500 } } }, shared: null });
});

test("a mention that cites one opens in the Use state, its criteria read when they are not known", async () => {
  const { asked } = open({}, {
    wording: "the secretary",
    criteria: { type: "Person", where: { born: { eq: 1501 } } },
    shared: { id: SECRETARY, label: "The duke's secretary" },
  });
  await vi.waitFor(() => expect(byTestId("criteria-shared-head")).not.toBeNull());
  expect(ofPath(asked, `/Description/${SECRETARY}`)).toHaveLength(1);
  expect(byTestId("criteria-shared-head")?.querySelector('[data-testid="criteria-summary"]')?.textContent).toBe("Person · born: 1500");
  // (its own conditions in the form)
  await vi.waitFor(() => expect((byLabel("born") as HTMLInputElement | null)?.value).toBe("1501"));
  expect(startFrom()).toBeNull();
});

// --- the offer to share ---------------------------------------------------------------------------------------------

const others: Similar = {
  count: 4,
  documents: [
    { id: "s1", type: "Sighting", label: "Seen at Ghent" },
    { id: "s2", type: "Sighting", label: "Seen at Bruges" },
    { id: "s3", type: "Sighting", label: "Seen at Lille" },
    { id: "s4", type: "Sighting", label: "Seen at Arras" },
  ],
};

async function withOwn(answers: Answers, except: string | null = "this-document") {
  const opened = open({ shared: () => ({ count: 0, page: 1, pageSize: 5, results: [] }), ...answers }, { wording: "", criteria: null }, except);
  await vi.waitFor(() => expect(byLabel("Add a filter")).not.toBeNull());
  addFilter("born");
  type("born", "1500");
  await settle(300);
  return opened;
}

test("no offer while no other document has the same criteria", async () => {
  const { asked } = await withOwn({});
  await vi.waitFor(() => expect(ofPath(asked, "/criteria/similar")).toHaveLength(1));
  expect(ofPath(asked, "/criteria/similar")[0]!.body).toEqual({
    type: "Person",
    where: { born: { eq: 1500 } },
    description: null,
    except: "this-document",
  });
  await settle();
  expect(byTestId("criteria-similar")).toBeNull();
});

test("the same criteria in other documents: how many, the first as chips; nothing is done until it is confirmed", async () => {
  const { asked } = await withOwn({ similar: () => others });
  await vi.waitFor(() => expect(byTestId("criteria-similar-count")?.textContent).toBe("The same criteria are used in 4 other documents"));
  const chips = byTestId("criteria-similar")!.querySelector('[data-testid="criteria-similar-documents"]')!;
  expect([...chips.querySelectorAll("a")].map((a) => a.getAttribute("href"))).toEqual(["/Sighting/s1", "/Sighting/s2", "/Sighting/s3"]);
  expect(chips.textContent).toContain("and 1 more");
  // (asked a moment after the change, as the preview is: once)
  expect(ofPath(asked, "/criteria/similar")).toHaveLength(1);

  click(button("Make them one shared description…"));
  const confirm = byTestId("criteria-share-confirm")!;
  expect(confirm.textContent).toContain("changes 4 other documents, which may be other people's: each gets a new version");
  expect(confirm.textContent).toContain("This mention cites it too, once you save this document.");
  // (every one it changes is named)
  expect(confirm.querySelectorAll("a")).toHaveLength(4);
  expect(button("Change 4 documents and share")!.disabled).toBe(true);
  click(button("Cancel"));
  expect(byTestId("criteria-share-confirm")).toBeNull();
  expect(ofPath(asked, "/criteria/share")).toHaveLength(0);
});

test("shared: the description is made, the dialog cites it, and what was done is said, failures by document", async () => {
  const made: ShareResult = {
    description: { id: SECRETARY, type: "Description", label: "The duke's secretary" },
    updated: 3,
    failed: [{ head: others.documents[3]!, detail: "the document was changed meanwhile" }],
  };
  const { asked, done } = await withOwn({ similar: () => others, share: () => made });
  await vi.waitFor(() => expect(byTestId("criteria-similar")).not.toBeNull());
  click(button("Make them one shared description…"));
  type("Label of the shared description", "The duke's secretary");
  click(button("Change 4 documents and share"));
  await vi.waitFor(() => expect(byTestId("criteria-shared-head")).not.toBeNull());
  expect(ofPath(asked, "/criteria/share")[0]!.body).toMatchObject({ label: "The duke's secretary", type: "Person", where: { born: { eq: 1500 } } });
  const outcome = byTestId("criteria-share-outcome")!;
  expect(outcome.textContent).toContain("3 other documents now cite it.");
  const failed = byTestId("criteria-share-failed")!;
  expect(failed.querySelector("a")?.getAttribute("href")).toBe("/Sighting/s4");
  expect(failed.textContent).toContain("the document was changed meanwhile");
  // (its own conditions are now those of the shared description: none here)
  await vi.waitFor(() => expect(button("Done")!.disabled).toBe(false));
  click(button("Done"));
  expect(done.mock.calls[0]![0]).toMatchObject({ criteria: null, shared: { id: SECRETARY, label: "The duke's secretary" } });
});

test("a share the server refuses says why, and nothing else changes", async () => {
  await withOwn({
    similar: () => others,
    share: () => {
      throw new ApiError(422, "too many documents: 4000 (at most 500 at once)", {});
    },
  });
  await vi.waitFor(() => expect(byTestId("criteria-similar")).not.toBeNull());
  click(button("Make them one shared description…"));
  type("Label of the shared description", "The duke's secretary");
  click(button("Change 4 documents and share"));
  await vi.waitFor(() => expect(byTestId("criteria-share-refused")?.textContent).toBe("too many documents: 4000 (at most 500 at once)"));
  expect(byTestId("criteria-shared-head")).toBeNull();
});
