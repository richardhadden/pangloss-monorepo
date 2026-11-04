// @vitest-environment happy-dom
import { ComponentsProvider, defaultComponents, ModelsProvider, ModulesProvider } from "@pangloss/interface-core";
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import type { Contents, Version } from "../api";
import { DEFINITIONS } from "../fixtures";
import { columnsOf, Compare } from "./HistoryPage";

const version = (n: number, content: Version["content"], op: Version["op"] = "update"): Version => ({
  seq: n,
  version: n,
  op,
  who: "ann",
  at: "2026-11-04T10:00:00Z",
  schemaPosition: {},
  restoredFrom: null,
  content,
  upgraded: false,
  problems: [],
});

const CONTENTS: Contents = {
  id: "f1",
  model: "Factoid",
  currentVersion: 2,
  versions: [
    version(1, { type: "Factoid", label: "Crowned", text: "The king is crowned", places: [] }, "create"),
    version(2, {
      type: "Factoid",
      label: "Crowned",
      text: "The emperor is crowned",
      places: [{ id: "p1", type: "Place", label: "Rome" }],
    }),
  ],
};

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

test("the columns are the recorded versions, and what the item is now if that was not recorded", () => {
  expect(columnsOf(CONTENTS).map((c) => [c.version, c.current, !!c.record])).toEqual([
    [1, false, true],
    [2, true, true],
  ]);
  const ahead = columnsOf({ ...CONTENTS, currentVersion: 3 }, { type: "Factoid", label: "Now" });
  expect(ahead.map((c) => [c.version, c.current, !!c.record])).toEqual([
    [1, false, true],
    [2, false, true],
    [3, true, false],
  ]);
});

test("every version side by side, row by row, each cell marked against the one to its left", () => {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ComponentsProvider components={defaultComponents}>
        <ModelsProvider definitions={DEFINITIONS}>
          <ModulesProvider modules={[]}>
            <Compare type="Factoid" contents={CONTENTS} />
          </ModulesProvider>
        </ModelsProvider>
      </ComponentsProvider>
    ),
    container,
  );
  const columns = [...document.querySelectorAll<HTMLElement>('[data-testid="history-column"]')];
  expect(columns.map((c) => c.dataset.version)).toEqual(["1", "2"]);
  const marks = (row: string) =>
    [...document.querySelectorAll<HTMLElement>(`[data-testid="history-cell"][data-row="${row}"]`)].map((c) => c.dataset.mark);
  expect(marks(".label")).toEqual(["same", "same"]);
  expect(marks(".text")).toEqual(["same", "changed"]);
  expect(marks(".places[p1]")).toEqual(["absent", "added"]);
  const text = document.querySelectorAll('[data-row=".text"]')[1]!;
  expect(text.querySelector('[data-kind="added"]')!.textContent).toBe("emperor");
  expect(document.querySelector('[data-row=".places[p1]"][data-mark="added"]')!.textContent).toContain("Rome");
});
