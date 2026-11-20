// @vitest-environment happy-dom
import { ApiError } from "@pangloss/interface-core";
import { afterEach, expect, test, vi } from "vitest";
import type { Preview } from "../api";
import { addFilter, button, byTestId, CHARLES, cleanUp, click, fakeApi, MARIE, settle, show, type } from "../testing";
import { CriteriaDialog } from "./CriteriaDialog";
import type { CriteriaDone, CriteriaValue } from "./CriteriaDialog";

afterEach(cleanUp);

const found = (count: number, ...people: [string, string][]): Preview => ({
  count,
  tooBroad: false,
  candidates: people.map(([id, label]) => ({ type: "Person", id, label })),
});

function open(answer: (path: string, body: unknown) => unknown, value: CriteriaValue = { wording: "", criteria: null }) {
  const api = fakeApi(answer);
  const done = vi.fn((_: CriteriaDone) => undefined);
  const cancel = vi.fn();
  show(api.client, () => (
    <CriteriaDialog types={["Person"]} value={value} named={() => [CHARLES]} onDone={done} onCancel={cancel} />
  ));
  return { asked: api.asked, done, cancel };
}

const previews = (asked: { path: string; body: unknown }[]) => asked.filter((each) => each.path === "/criteria/preview");

test("without a condition there is nothing to save: a hint, and Done is off", async () => {
  const { asked } = open(() => found(0));
  await vi.waitFor(() => expect(document.body.querySelector('[aria-label="Add a filter"]')).not.toBeNull());
  expect(byTestId("criteria-need-condition")).not.toBeNull();
  expect(button("Done")!.disabled).toBe(true);
  expect(previews(asked)).toHaveLength(0);
});

test("what the criteria find is shown a moment after a change, without what the document names", async () => {
  const { asked, done } = open((path) => (path === "/criteria/preview" ? found(1, [MARIE, "Marie of Burgundy"]) : { found: [] }));
  await vi.waitFor(() => expect(document.body.querySelector('[aria-label="Add a filter"]')).not.toBeNull());
  type("What the source says", "N. N., born in 1500");
  addFilter("born");
  type("born", "1500");
  await settle(300);
  await vi.waitFor(() => expect(byTestId("criteria-count")?.textContent).toBe("1 candidate found"));
  expect(byTestId("criteria-candidates")?.textContent).toContain("Marie of Burgundy");
  expect(previews(asked).at(-1)!.body).toEqual({ criteria: { type: "Person", where: { born: { eq: 1500 } } }, named: [CHARLES] });
  // (and the summary says what they are)
  expect(byTestId("criteria-summary")?.textContent).toBe("Person · born: 1500");
  expect(button("Done")!.disabled).toBe(false);
  click(button("Done"));
  expect(done).toHaveBeenCalledWith({
    wording: "N. N., born in 1500",
    criteria: { type: "Person", where: { born: { eq: 1500 } } },
    shared: null,
    preview: found(1, [MARIE, "Marie of Burgundy"]),
  });
});

test("an answer that comes after a later one is not shown", async () => {
  const waiting: ((preview: Preview) => void)[] = [];
  open((path) => (path === "/criteria/preview" ? new Promise((resolve) => waiting.push(resolve)) : { found: [] }));
  await vi.waitFor(() => expect(document.body.querySelector('[aria-label="Add a filter"]')).not.toBeNull());
  addFilter("born");
  type("born", "1500");
  await settle(300);
  type("born", "1600");
  await settle(300);
  expect(waiting).toHaveLength(2);
  waiting[1]!(found(2, [MARIE, "Marie"], [CHARLES, "Charles"]));
  await settle();
  waiting[0]!(found(1, [MARIE, "Marie"]));
  await settle();
  expect(byTestId("criteria-count")?.textContent).toBe("2 candidates found");
});

test("criteria the server would refuse say why", async () => {
  open((path) => {
    if (path === "/criteria/preview") throw new ApiError(422, "born: not a year", { error: "PanglossSearchError" });
    return { found: [] };
  });
  await vi.waitFor(() => expect(document.body.querySelector('[aria-label="Add a filter"]')).not.toBeNull());
  addFilter("born");
  type("born", "1500");
  await settle(300);
  await vi.waitFor(() => expect(byTestId("criteria-refused")?.textContent).toBe("born: not a year"));
});

test("criteria the form cannot show are shown as they are; the wording can still be changed, and Done keeps them", async () => {
  const criteria = { type: "Person", where: { label: { regex: "^Jo" } } };
  const { asked, done } = open((path) => (path === "/criteria/preview" ? found(0) : { found: [] }), {
    wording: "John",
    criteria,
  });
  await settle();
  expect(byTestId("criteria-read-only")).not.toBeNull();
  expect(byTestId("criteria-read-only")?.querySelector("pre")?.textContent).toContain('"regex": "^Jo"');
  expect(document.body.querySelector('[aria-label="Add a filter"]')).toBeNull();
  // (what they find is asked at once, and said)
  await vi.waitFor(() => expect(byTestId("criteria-count")?.textContent).toBe("No candidates yet: it will update as data is added"));
  expect(previews(asked)[0]!.body).toEqual({ criteria, named: [CHARLES] });
  type("What the source says", "Johannes");
  click(button("Done"));
  expect(done).toHaveBeenCalledWith({ wording: "Johannes", criteria, shared: null, preview: found(0) });
});

test("saved criteria open in the form, with the labels of the entities they name", async () => {
  const criteria = { type: "Person", where: { born: { eq: 1500 }, friend: { is: MARIE } } };
  const { asked } = open(
    (path) =>
      path === "/criteria/preview"
        ? found(1, [CHARLES, "Charles"])
        : { found: [{ type: "Person", id: MARIE, label: "Marie of Burgundy" }] },
    { wording: "", criteria },
  );
  await vi.waitFor(() => expect((document.body.querySelector('[aria-label="born"]') as HTMLInputElement | null)?.value).toBe("1500"));
  expect(byTestId("criteria-read-only")).toBeNull();
  // (the entity picked, by its label, in the form and in the summary: asked once for each)
  const form = document.body.querySelector('[aria-label="Criteria"]')!;
  await vi.waitFor(() => expect(form.textContent).toContain("Marie of Burgundy"));
  await vi.waitFor(() => expect(byTestId("criteria-summary")?.textContent).toBe("Person · born: 1500, friend: PersonMarie of Burgundy"));
  expect(asked.filter((each) => each.path === "/references").map((each) => each.body)).toEqual([{ ids: [MARIE] }, { ids: [MARIE] }]);
  await vi.waitFor(() => expect(byTestId("criteria-count")?.textContent).toBe("1 candidate found"));
});

// --- out of date (a migration took away what the criteria name) ---------------------------------------------------------

const SINCE = "demo_app.0024_remove_office";

test("out of date, in a form that can still show them: the notice in red, the row of the failed field red, Done off until changed", async () => {
  const criteria = { type: "Person", where: { born: { eq: 1500 }, friend: { is: MARIE } } };
  const { asked, done } = open(
    (path) => (path === "/criteria/preview" ? found(0) : { found: [{ type: "Person", id: MARIE, label: "Marie of Burgundy" }] }),
    { wording: "N. N.", criteria, broken: { reason: "where.born: 1500 is no longer a value of born", since: SINCE } },
  );
  const notice = byTestId("criteria-broken-notice")!;
  expect(notice.getAttribute("role")).toBe("alert");
  expect(notice.textContent).toContain(`Out of date since migration ${SINCE}`);
  expect(byTestId("criteria-broken-reason")?.textContent).toBe("where.born: 1500 is no longer a value of born");
  await vi.waitFor(() => expect((document.body.querySelector('[aria-label="born"]') as HTMLInputElement | null)?.value).toBe("1500"));
  // (the row of `born` is red; `friend`'s is not)
  const invalid = [...document.body.querySelectorAll<HTMLElement>("[data-invalid] dt")].map((dt) => dt.textContent);
  expect(invalid).toEqual(["born"]);
  // (the server is not asked what criteria it refuses find; saved as they are, they would be refused again)
  await settle();
  expect(previews(asked)).toHaveLength(0);
  expect(button("Done")!.disabled).toBe(true);
  type("born", "1600");
  await settle(300);
  expect(button("Done")!.disabled).toBe(false);
  click(button("Done"));
  expect(done.mock.calls[0]![0].criteria).toEqual({ type: "Person", where: { born: { eq: 1600 }, friend: { is: MARIE } } });
});

test("out of date with no migration to name: Out of date, and the reason", () => {
  open(() => found(0), {
    wording: "",
    criteria: { type: "Person", where: { born: { eq: 1500 } } },
    broken: { reason: "born: not a year", since: null },
  });
  const notice = byTestId("criteria-broken-notice")!;
  expect(notice.querySelector("p")?.textContent).toBe("Out of date");
  expect(byTestId("criteria-broken-reason")?.textContent).toBe("born: not a year");
});

test("out of date and naming a field the models no longer have: the stored JSON under the notice, and a start afresh", async () => {
  const criteria = { type: "Person", where: { office: { eq: "Secretary" } } };
  const { asked, done } = open((path) => (path === "/criteria/preview" ? found(0) : { found: [] }), {
    wording: "the secretary",
    criteria,
    broken: { reason: "where.office: the field 'office' of Person was removed", since: SINCE },
  });
  await settle();
  // (nothing thrown, nothing dropped: the pattern as it was stored, read-only)
  expect(byTestId("criteria-broken-notice")).not.toBeNull();
  const shown = byTestId("criteria-read-only")!;
  expect(shown.textContent).toContain("The form can no longer show these criteria");
  expect(shown.querySelector("pre")?.textContent).toContain('"office"');
  expect(document.body.querySelector('[aria-label="Add a filter"]')).toBeNull();
  // (the summary says the field gone as it is written)
  expect(byTestId("criteria-summary")?.textContent).toBe("Person · office: Secretary");
  expect(button("Done")!.disabled).toBe(true);
  expect(previews(asked)).toHaveLength(0);

  // (started afresh: the search form of the class, empty; the notice stays until the criteria are saved)
  click(byTestId("criteria-start-afresh"));
  await vi.waitFor(() => expect(document.body.querySelector('[aria-label="Add a filter"]')).not.toBeNull());
  expect(byTestId("criteria-read-only")).toBeNull();
  expect(byTestId("criteria-need-condition")).not.toBeNull();
  expect(byTestId("criteria-broken-notice")).not.toBeNull();
  addFilter("born");
  type("born", "1500");
  await settle(300);
  await vi.waitFor(() => expect(button("Done")!.disabled).toBe(false));
  click(button("Done"));
  expect(done).toHaveBeenCalledWith({
    wording: "the secretary",
    criteria: { type: "Person", where: { born: { eq: 1500 } } },
    shared: null,
    preview: found(0),
  });
});

test("out of date and of a class the models no longer have: shown as stored, and started afresh with a class that is there", async () => {
  open(() => found(0), {
    wording: "",
    criteria: { type: "Officer", where: { rank: { eq: 1 } } },
    broken: { reason: "Officer: not a model that can be searched", since: SINCE },
  });
  await settle();
  expect(byTestId("criteria-read-only")?.querySelector("pre")?.textContent).toContain('"Officer"');
  click(byTestId("criteria-start-afresh"));
  await vi.waitFor(() => expect(document.body.querySelector('[aria-label="Add a filter"]')).not.toBeNull());
  expect(document.body.querySelector('[aria-label="Criteria"]')?.textContent).toContain("Criteria: Person");
});
