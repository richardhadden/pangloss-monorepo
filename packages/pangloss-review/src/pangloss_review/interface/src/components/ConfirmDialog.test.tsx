// @vitest-environment happy-dom
import { ComponentsProvider, defaultComponents, ModelsProvider } from "@pangloss/interface-core";
import type { ModelDefinition, ModelDefinitions } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { afterEach, expect, test, vi } from "vitest";
import type { Suggestion } from "../api";
import ConfirmDialog from "./ConfirmDialog";

const DEFINITIONS = {
  models: {
    Person: { name: "Person", kind: "Entity", parent: null, abstract: false, fields: [], incoming: [] } as unknown as ModelDefinition,
  },
  enums: {},
} as unknown as ModelDefinitions;

const SUGGESTION: Suggestion = {
  id: "s1",
  type: "IdentificationByToolchainFromText",
  becomes: "IdentificationFromText",
  identifiedBy: "extractor",
  uris: [],
  text: "Jon Smyth",
  candidates: [
    { type: "Person", id: "p1", label: "John", percent: 70 },
    { type: "Person", id: "p2", label: "Jack", percent: 30 },
  ],
  holder: { type: "Activity", id: "a1", label: "A sale" },
  head: { type: "Factoid", id: "f1", label: "A sale" },
};

const settle = async () => {
  for (let i = 0; i < 6; i++) await new Promise((resolve) => setTimeout(resolve));
};

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

function show(suggestion: Suggestion, onConfirm: (also: string[], mentions: string[], entity?: unknown) => void) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ComponentsProvider components={defaultComponents}>
        <ModelsProvider definitions={DEFINITIONS}>
          <ConfirmDialog asked={{ suggestion, similar: [], mentions: [] }} onConfirm={onConfirm} onClose={() => {}} />
        </ModelsProvider>
      </ComponentsProvider>
    ),
    container,
  );
}

const all = (testid: string) => [...document.querySelectorAll<HTMLElement>(`[data-testid="${testid}"]`)];

test("what the source wrote is shown beside the candidates, and each candidate can be confirmed as the one", async () => {
  const onConfirm = vi.fn();
  show(SUGGESTION, onConfirm);
  await settle();
  expect(all("source-text").map((node) => node.textContent)).toEqual(["“Jon Smyth”"]);
  const rows = all("confirm-alternative");
  expect(rows.map((row) => row.dataset.id)).toEqual(["p1", "p2"]);
  expect(rows[1].textContent).toContain("Jack");
  expect(rows[1].textContent).toContain("30%");
  const button = rows[1].querySelector<HTMLButtonElement>('[data-testid="confirm-as-one"]');
  expect(button?.textContent).toBe("Confirm as this one");
  expect(button?.getAttribute("aria-label")).toBe("Confirm as Jack");
  button?.click();
  expect(onConfirm).toHaveBeenCalledWith([], [], SUGGESTION.candidates[1]);
  // (Confirm itself confirms it as it is)
  all("confirm-submit")[0].click();
  expect(onConfirm).toHaveBeenLastCalledWith([], [], undefined);
});

test("with one candidate, or no text, there is nothing of either", async () => {
  show({ ...SUGGESTION, text: null, candidates: [SUGGESTION.candidates[0]] }, () => {});
  await settle();
  expect(all("source-text")).toEqual([]);
  expect(all("confirm-alternatives")).toEqual([]);
  expect(all("suggestion-candidates")).toHaveLength(1);
});
