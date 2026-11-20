// @vitest-environment happy-dom
import { createItemFormState, getModel, ItemFormProvider } from "@pangloss/interface-core";
import type { EditCardProps, FormData } from "@pangloss/interface-core";
import { afterEach, expect, test, vi } from "vitest";
import {
  addFilter,
  button,
  byLabel,
  byTestId,
  CHARLES,
  cleanUp,
  click,
  definitions,
  describedPerson,
  fakeApi,
  MARIE,
  settle,
  show,
  type,
} from "../testing";
import CriteriaEditor from "./CriteriaEditor";

afterEach(cleanUp);

const PATH = ["seen", 1];

/** The editor of the second of what a sighting saw (the first is Charles, named), in the sighting's form */
function edit(description: Record<string, unknown>, answer: (path: string, body: unknown) => unknown) {
  const api = fakeApi(answer);
  const form = createItemFormState({ type: "Sighting", seen: [{ type: "Person", id: CHARLES, label: "Charles" }, description] } as FormData);
  const removed = vi.fn(() => form.remove(PATH));
  const props = {
    type: "MatchesCriteria",
    model: getModel(definitions, "MatchesCriteria")!,
    label: "",
    path: PATH,
    get value() {
      return (form.get(PATH) ?? {}) as Record<string, unknown>;
    },
    onChange: (next: Record<string, unknown>) => form.set(PATH, next),
    onRemove: removed,
    option: describedPerson,
  } satisfies EditCardProps;
  show(api.client, () => (
    <ItemFormProvider state={form}>
      <CriteriaEditor {...props} />
    </ItemFormProvider>
  ));
  return { form, removed, asked: api.asked };
}

const preview = (path: string) =>
  path === "/criteria/preview"
    ? { count: 1, tooBroad: false, candidates: [{ type: "Person", id: MARIE, label: "Marie" }] }
    : { found: [] };

test("a new one opens its dialog at once, and Cancel takes it out again", async () => {
  const { removed, form } = edit({ type: "MatchesCriteria" }, preview);
  await vi.waitFor(() => expect(byTestId("criteria-dialog")).not.toBeNull());
  click(button("Cancel"));
  await settle();
  expect(removed).toHaveBeenCalled();
  expect((form.get(["seen"]) as unknown[]).length).toBe(1);
});

test("the criteria written in the dialog are the description's; the preview, without who the document names, is not saved yet", async () => {
  const { form, asked } = edit({ type: "MatchesCriteria" }, preview);
  await vi.waitFor(() => expect(byLabel("Add a filter")).not.toBeNull());
  addFilter("born");
  type("born", "1500");
  await settle(300);
  await vi.waitFor(() => expect(byTestId("criteria-count")?.textContent).toBe("1 candidate found"));
  // (Charles is named by the sighting: he is no candidate)
  expect(asked.find((each) => each.path === "/criteria/preview")?.body).toMatchObject({ named: [CHARLES] });
  click(button("Done"));
  await settle();
  expect(byTestId("criteria-dialog")).toBeNull();
  expect(form.get(PATH)).toEqual({
    type: "MatchesCriteria",
    wording: null,
    criteria: { type: "Person", where: { born: { eq: 1500 } } },
  });
  expect(byTestId("criteria-summary")?.textContent).toBe("Person · born: 1500");
  expect(byTestId("criteria-count")?.textContent).toBe("1 candidate found · not saved yet");
});

test("a saved one shows what the server found; changed criteria drop it, and show the preview", async () => {
  const saved = {
    type: "MatchesCriteria",
    id: "00000000-0000-0000-0000-0000000000d1",
    wording: "the one born in 1500",
    criteria: { type: "Person", where: { born: { eq: 1500 } } },
    target: [{ type: "Person", id: CHARLES, label: "Charles" }],
    candidateCount: 1,
    evaluatedWhen: "2026-11-19T10:00:00Z",
    broken: null,
  };
  const { form } = edit(saved, preview);
  await settle();
  // (not opened: it has its criteria)
  expect(byTestId("criteria-dialog")).toBeNull();
  expect(byTestId("criteria-wording")?.textContent).toBe("“the one born in 1500”");
  expect(byTestId("criteria-candidates")?.textContent).toContain("Charles");
  expect(byTestId("criteria-count")?.textContent).toBe("1 candidate found");
  click(byLabel("Edit the criteria"));
  await vi.waitFor(() => expect((byLabel("born") as HTMLInputElement | null)?.value).toBe("1500"));
  type("born", "1600");
  await settle(300);
  await vi.waitFor(() => expect(byTestId("criteria-dialog")?.querySelector('[data-testid="criteria-count"]')).not.toBeNull());
  click(button("Done"));
  await settle();
  expect(form.get(PATH)).toEqual({
    type: "MatchesCriteria",
    id: saved.id,
    wording: "the one born in 1500",
    criteria: { type: "Person", where: { born: { eq: 1600 } } },
  });
  expect(byTestId("criteria-candidates")?.textContent).toContain("Marie");
  expect(byTestId("criteria-count")?.textContent).toBe("1 candidate found · not saved yet");
});

test("the wording alone changed keeps what the server found", async () => {
  const saved = {
    type: "MatchesCriteria",
    id: "00000000-0000-0000-0000-0000000000d2",
    wording: "",
    criteria: { type: "Person", where: { born: { eq: 1500 } } },
    target: [{ type: "Person", id: CHARLES, label: "Charles" }],
    candidateCount: 1,
    evaluatedWhen: "2026-11-19T10:00:00Z",
  };
  const { form } = edit(saved, preview);
  click(byLabel("Edit the criteria"));
  await vi.waitFor(() => expect(byTestId("criteria-dialog")).not.toBeNull());
  type("What the source says", "the one");
  click(button("Done"));
  await settle();
  expect(form.get(PATH)).toEqual({ ...saved, wording: "the one" });
  expect(byTestId("criteria-count")?.textContent).toBe("1 candidate found");
});

test("one out of date says so, with its last candidates; its dialog has the notice; changed criteria are no longer out of date", async () => {
  const saved = {
    type: "MatchesCriteria",
    id: "00000000-0000-0000-0000-0000000000d4",
    wording: "the one born in 1500",
    criteria: { type: "Person", where: { born: { eq: 1500 } } },
    target: [{ type: "Person", id: CHARLES, label: "Charles" }],
    candidateCount: 1,
    evaluatedWhen: "2026-11-19T10:00:00Z",
    broken: "where.born: not a year",
    brokenSince: "demo_app.0024_born_text",
  };
  const { form } = edit(saved, preview);
  await settle();
  expect(byTestId("criteria-broken")?.querySelector("p")?.textContent).toBe("Out of date since migration demo_app.0024_born_text");
  expect(byTestId("criteria-broken-reason")?.textContent).toBe("where.born: not a year");
  expect(byTestId("criteria-candidates")?.textContent).toContain("Charles");
  expect(byTestId("criteria-candidates")?.hasAttribute("data-faded")).toBe(true);
  expect(byTestId("criteria-count")?.textContent).toBe("1 candidate found · the last found: no longer kept up to date");
  click(byLabel("Edit the criteria"));
  await vi.waitFor(() => expect(byTestId("criteria-broken-notice")).not.toBeNull());
  await vi.waitFor(() => expect((byLabel("born") as HTMLInputElement | null)?.value).toBe("1500"));
  type("born", "1600");
  await settle(300);
  await vi.waitFor(() => expect(button("Done")!.disabled).toBe(false));
  click(button("Done"));
  await settle();
  // (what the server worked out of the old criteria is gone, its being out of date with it)
  expect(form.get(PATH)).toEqual({
    type: "MatchesCriteria",
    id: saved.id,
    wording: "the one born in 1500",
    criteria: { type: "Person", where: { born: { eq: 1600 } } },
  });
  expect(byTestId("criteria-broken")).toBeNull();
});

// --- the same one in several places of the sighting (`sameOne`) -------------------------------------------------------

const MARK = "00000000-0000-0000-0000-00000000000f";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

const holding = (extra: Record<string, unknown> = {}) => ({
  type: "MatchesCriteria",
  id: "00000000-0000-0000-0000-0000000000d3",
  wording: "the secretary",
  criteria: { type: "Person", where: { born: { eq: 1500 } } },
  target: [{ type: "Person", id: CHARLES, label: "Charles" }],
  candidateCount: 1,
  evaluatedWhen: "2026-11-19T10:00:00Z",
  ...extra,
});

/** The editor of the description at `path` in a sighting holding `data` (its other places are in the form, not drawn) */
function editAt(data: Record<string, unknown>, path: (string | number)[], answer: (path: string, body: unknown) => unknown = preview) {
  const api = fakeApi(answer);
  const form = createItemFormState({ type: "Sighting", seen: [], company: [], ...data } as FormData);
  const removed = vi.fn(() => form.remove(path));
  const props = {
    type: "MatchesCriteria",
    model: getModel(definitions, "MatchesCriteria")!,
    label: "",
    path,
    get value() {
      return (form.get(path) ?? {}) as Record<string, unknown>;
    },
    onChange: (next: Record<string, unknown>) => form.set(path, next),
    onRemove: removed,
    option: describedPerson,
  } satisfies EditCardProps;
  show(api.client, () => (
    <ItemFormProvider state={form}>
      <CriteriaEditor {...props} />
    </ItemFormProvider>
  ));
  return { form, removed, asked: api.asked };
}

/** Chooses `option` in the menu of `label` (a `MenuSelect`) */
function choose(label: string, option: (element: HTMLElement) => boolean) {
  const menu = document.body.querySelector<HTMLElement>(`[role="combobox"][aria-label="${label}"]`)!;
  if (menu.getAttribute("aria-expanded") !== "true") click(menu);
  click([...document.getElementById(menu.getAttribute("aria-controls")!)!.querySelectorAll<HTMLElement>('[role="option"]')].find(option));
}

const removeButton = () => document.body.querySelector<HTMLElement>('button[aria-label^="Remove "]');

const options = (label: string) => {
  const menu = document.body.querySelector<HTMLElement>(`[role="combobox"][aria-label="${label}"]`)!;
  if (menu.getAttribute("aria-expanded") !== "true") click(menu);
  return [...document.getElementById(menu.getAttribute("aria-controls")!)!.querySelectorAll<HTMLElement>("li")].map((each) => each.textContent);
};

test("a new one is offered the descriptions of the document as the same one; one chosen gives both one mark, and none of the criteria here", async () => {
  const { form } = editAt({ seen: [holding()], company: [{ type: "MatchesCriteria" }] }, ["company", 0]);
  await vi.waitFor(() => expect(byTestId("criteria-same-one")).not.toBeNull());
  // (each by its summary and wording, under the name of the field it is in)
  expect(options("The same one as")).toEqual(["seen", "Person · born: 1500 · “the secretary”"]);
  type("What the source says", "the same man");
  choose("The same one as", () => true);
  await settle();
  expect(byTestId("criteria-dialog")).toBeNull();
  const mark = form.get(["seen", 0, "sameOne"]);
  expect(mark).toMatch(UUID);
  expect(form.get(["company", 0])).toEqual({ type: "MatchesCriteria", wording: "the same man", criteria: null, sameOne: mark });
  // (the holder keeps its criteria and what the server found)
  expect(form.get(["seen", 0])).toEqual({ ...holding(), sameOne: mark });
  // (the card is now that of a place that is the same one as another)
  expect(byTestId("criteria-same-one-mark")?.textContent).toBe("The same one as");
  expect(byTestId("criteria-summary")?.textContent).toBe("Person · born: 1500");
  expect((byLabel<HTMLInputElement>("wording"))?.value).toBe("the same man");
});

test("a holder that has a mark keeps it; one of several holders of a mark is offered once; one this field cannot take is not offered", async () => {
  const { form } = editAt(
    {
      seen: [holding({ sameOne: MARK }), { type: "MatchesCriteria", criteria: { type: "Group", where: {} } }],
      company: [holding({ id: undefined, sameOne: MARK, wording: "" }), { type: "MatchesCriteria" }],
    },
    ["company", 1],
  );
  await vi.waitFor(() => expect(byTestId("criteria-same-one")).not.toBeNull());
  expect(options("The same one as")).toEqual(["seen", "Person · born: 1500 · “the secretary”"]);
  choose("The same one as", () => true);
  await settle();
  expect(form.get(["company", 1, "sameOne"])).toBe(MARK);
  expect(form.get(["seen", 0, "sameOne"])).toBe(MARK);
});

test("with no other description of the document, nothing is offered", async () => {
  editAt({ seen: [{ type: "MatchesCriteria" }] }, ["seen", 0]);
  await vi.waitFor(() => expect(byTestId("criteria-dialog")).not.toBeNull());
  expect(byTestId("criteria-same-one")).toBeNull();
});

test("the pencil of a place that is the same one as another edits the criteria of the one that holds them, at its path", async () => {
  const { form } = editAt(
    { seen: [holding({ sameOne: MARK })], company: [{ type: "MatchesCriteria", id: "00000000-0000-0000-0000-0000000000d4", wording: "him", criteria: null, sameOne: MARK }] },
    ["company", 0],
  );
  await settle();
  expect(byTestId("criteria-summary")?.textContent).toBe("Person · born: 1500");
  click(byLabel("Edit the criteria"));
  await vi.waitFor(() => expect((byLabel("born") as HTMLInputElement | null)?.value).toBe("1500"));
  // (the wording is the place's own: not in the dialog)
  expect(byLabel("What the source says")).toBeNull();
  type("born", "1600");
  await settle(300);
  click(button("Done"));
  await settle();
  // (the holder's criteria changed, and what the server found of the old ones gone; this place as it was)
  expect(form.get(["seen", 0])).toEqual({
    type: "MatchesCriteria",
    id: holding().id,
    wording: "the secretary",
    criteria: { type: "Person", where: { born: { eq: 1600 } } },
    sameOne: MARK,
  });
  expect(form.get(["company", 0])).toMatchObject({ wording: "him", criteria: null, sameOne: MARK });
  expect(byTestId("criteria-summary")?.textContent).toBe("Person · born: 1600");
});

test("the wording of a place that is the same one as another is its own", async () => {
  const { form } = editAt({ seen: [holding({ sameOne: MARK })], company: [{ type: "MatchesCriteria", criteria: null, sameOne: MARK }] }, ["company", 0]);
  await settle();
  type("wording", "his man");
  expect(form.get(["company", 0, "wording"])).toBe("his man");
  expect(form.get(["seen", 0, "wording"])).toBe("the secretary");
});

test("removing the last place of a mark that holds the criteria gives them to the next place of the mark first", async () => {
  const { form, removed } = editAt(
    { seen: [holding({ sameOne: MARK })], company: [{ type: "MatchesCriteria", wording: "him", criteria: null, sameOne: MARK }] },
    ["seen", 0],
  );
  await settle();
  click(removeButton());
  await settle();
  expect(removed).toHaveBeenCalled();
  expect(form.get(["seen"])).toEqual([]);
  expect(form.get(["company", 0])).toEqual({
    type: "MatchesCriteria",
    wording: "him",
    criteria: { type: "Person", where: { born: { eq: 1500 } } },
    sameOne: MARK,
  });
});

test("removing a holder while another place of its mark holds the criteria too moves nothing", async () => {
  const other = holding({ id: "00000000-0000-0000-0000-0000000000d5", sameOne: MARK, wording: "him" });
  const { form } = editAt({ seen: [holding({ sameOne: MARK })], company: [other] }, ["seen", 0]);
  await settle();
  click(removeButton());
  await settle();
  expect(form.get(["company", 0])).toEqual(other);
});

test("Describe separately gives the place a copy of the criteria of its own, and no mark", async () => {
  const { form } = editAt(
    { seen: [holding({ sameOne: MARK })], company: [{ type: "MatchesCriteria", wording: "him", criteria: null, sameOne: MARK }] },
    ["company", 0],
  );
  await settle();
  click(button("Describe separately"));
  await settle();
  expect(form.get(["company", 0])).toEqual({
    type: "MatchesCriteria",
    wording: "him",
    criteria: { type: "Person", where: { born: { eq: 1500 } } },
    sameOne: null,
  });
  // (a copy: a change of the other's criteria does not reach it)
  form.set(["seen", 0, "criteria", "where", "born", "eq"], 1700);
  expect(form.get(["company", 0, "criteria", "where", "born", "eq"])).toBe(1500);
  // (the card is now one with criteria of its own)
  expect(byTestId("criteria-same-one-mark")).toBeNull();
  expect(byTestId("criteria-summary")?.textContent).toBe("Person · born: 1500");
  expect(byTestId("criteria-dialog")).toBeNull();
});

test("a place whose mark no description in the form holds criteria for says so in red, and can be removed", async () => {
  const { removed } = editAt({ company: [{ type: "MatchesCriteria", wording: "him", criteria: null, sameOne: MARK }] }, ["company", 0]);
  await settle();
  expect(byTestId("criteria-same-one-missing")?.textContent).toBe("No description in this form holds the criteria");
  expect(byLabel("Edit the criteria")).toBeNull();
  expect(button("Describe separately")).toBeUndefined();
  click(removeButton());
  expect(removed).toHaveBeenCalled();
});
