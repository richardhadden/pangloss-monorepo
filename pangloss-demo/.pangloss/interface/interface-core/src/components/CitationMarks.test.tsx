// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { flush } from "solid-js";
import { expect, test, vi } from "vitest";
import { ComponentsProvider, ModelsProvider } from "../context";
import type { ComponentMap, ModelDefinitions } from "../types";
import { CitationChips, CitationMarks } from "./Citation";
import { ReferenceChip } from "./ReferenceChip";

const citation = (extra: Record<string, unknown> = {}) => ({
  type: "PGCitation",
  targetId: "d1",
  targetType: "Description",
  targetLabel: "Maximilian's secretary",
  targetHeadId: "d1",
  targetHeadType: "Description",
  targetHeadLabel: "Maximilian's secretary",
  targetState: "there",
  changedSinceCited: false,
  ...extra,
});

function shown(view: () => unknown) {
  const root = document.createElement("div");
  render(
    () => (
      <ComponentsProvider components={{ ReferenceChip } as ComponentMap}>
        <ModelsProvider definitions={{ models: {} } as unknown as ModelDefinitions}>{view() as never}</ModelsProvider>
      </ComponentsProvider>
    ),
    root,
  );
  flush();
  return root;
}

const button = (root: HTMLElement, name: string) =>
  [...root.querySelectorAll("button")].find((each) => each.textContent?.trim() === name);

test("the marks alone: nothing for a citation of what is there as it was cited", () => {
  expect(shown(() => <CitationMarks value={citation()} onSeen={() => undefined} />).textContent).toBe("");
});

test("the marks alone: changed since cited, and Seen in a form, which takes it off", () => {
  const seen = vi.fn();
  const root = shown(() => <CitationMarks value={citation({ changedSinceCited: true })} onSeen={seen} />);
  expect(root.textContent).toContain("changed since cited");
  button(root, "Seen")!.click();
  expect(seen).toHaveBeenCalled();
  // (on a page that is read, no Seen)
  expect(button(shown(() => <CitationMarks value={citation({ changedSinceCited: true })} />), "Seen")).toBeUndefined();
});

test("the marks alone: removed since cited, and not changed since cited then", () => {
  const root = shown(() => <CitationMarks value={citation({ targetState: "removed", changedSinceCited: true })} />);
  expect(root.textContent).toBe("removed since cited");
});

test("the chips without their marks, for a caller that draws them elsewhere", () => {
  const root = shown(() => <CitationChips value={citation({ changedSinceCited: true })} marks={false} />);
  expect(root.querySelector("a")?.getAttribute("href")).toBe("/Description/d1");
  expect(root.textContent).not.toContain("changed since cited");
  // (and with them, as before)
  expect(shown(() => <CitationChips value={citation({ changedSinceCited: true })} />).textContent).toContain("changed since cited");
  expect(shown(() => <CitationChips value={citation({ targetState: "removed" })} />).textContent).toContain("removed since cited");
});
