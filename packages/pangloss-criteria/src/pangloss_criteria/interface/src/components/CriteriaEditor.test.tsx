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
