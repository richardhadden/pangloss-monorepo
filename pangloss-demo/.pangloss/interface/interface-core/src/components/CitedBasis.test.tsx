// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { flush } from "solid-js";
import { expect, test, vi } from "vitest";
import { ComponentsProvider, ModelsProvider } from "../context";
import type { ComponentMap, ModelDefinitions } from "../types";
import { CitedBasisChips } from "./Citation";
import { ReferenceChip } from "./ReferenceChip";

const citation = (id: string, label: string) => ({
  type: "PGCitation",
  targetId: id,
  targetType: "ChildOf",
  targetLabel: label,
  targetHeadId: `head-${id}`,
  targetHeadType: "Factoid",
  targetHeadLabel: `Factoid of ${label}`,
  targetState: "there",
  changedSinceCited: false,
});

const basis = (extra: Record<string, unknown> = {}) => ({
  type: "PGCitedBasis",
  id: "b1",
  viaId: "d1",
  viaType: "DerivedFactoid",
  viaRule: "siblings",
  viaLabel: "A and B, siblings",
  viaState: "there",
  derivationState: "",
  basis: [citation("s1", "A, child of P"), citation("s2", "B, child of P")],
  ...extra,
});

function shown(value: Record<string, unknown>, handlers: { onRemove?: () => void; onSeen?: () => void } = {}) {
  const root = document.createElement("div");
  render(
    () => (
      <ComponentsProvider components={{ ReferenceChip } as ComponentMap}>
        <ModelsProvider definitions={{ models: {} } as unknown as ModelDefinitions}>
          <CitedBasisChips value={value} {...handlers} />
        </ModelsProvider>
      </ComponentsProvider>
    ),
    root,
  );
  flush();
  return root;
}

test("something derived that was cited is a chip of it, its rule, and the citations of what it rests on", () => {
  const root = shown(basis());
  expect(root.querySelector("[data-cited-basis]")?.getAttribute("data-cited-basis")).toBe("d1");
  const links = [...root.querySelectorAll("a")].map((a) => a.getAttribute("href"));
  expect(links[0]).toBe("/DerivedFactoid/d1");
  expect(root.textContent).toContain("A and B, siblings");
  expect(root.textContent).toContain("derived by the rule siblings, from:");
  // (each of the basis as a citation is: what is cited, and the document it is in)
  expect([...root.querySelectorAll("[data-citation]")].map((c) => c.getAttribute("data-citation"))).toEqual(["s1", "s2"]);
  expect(links).toContain("/Factoid/head-s1?show=s1");
  expect(root.textContent).toContain("Factoid of B, child of P");
  expect(root.querySelector("[data-derivation-state]")).toBeNull();
  expect(root.querySelector("button")).toBeNull();
});

test("a derivation that is lost or changed is said so, and what was chosen is not a link when it is gone", () => {
  const lost = shown(basis({ derivationState: "lost", viaState: "removed", viaLabelNow: null }));
  expect(lost.querySelector("[data-derivation-state]")?.getAttribute("data-derivation-state")).toBe("lost");
  expect(lost.textContent).toContain("this derivation no longer holds");
  expect([...lost.querySelectorAll("a")].map((a) => a.getAttribute("href"))).not.toContain("/DerivedFactoid/d1");
  // (it is still called what it was when it was cited)
  expect(lost.textContent).toContain("A and B, siblings");
  const changed = shown(basis({ derivationState: "changed", viaLabelNow: "A and Z, siblings", viaRule: null }));
  expect(changed.querySelector("[data-derivation-state]")?.getAttribute("data-derivation-state")).toBe("changed");
  expect(changed.textContent).toContain("A and Z, siblings");
  expect(changed.textContent).toContain("derived, from:");
});

test("in a form it goes whole, and a mark is taken off with Seen", () => {
  const onRemove = vi.fn();
  const onSeen = vi.fn();
  const root = shown(basis({ derivationState: "lost" }), { onRemove, onSeen });
  const buttons = [...root.querySelectorAll("button")];
  const seen = buttons.find((button) => button.textContent === "Seen")!;
  seen.click();
  expect(onSeen).toHaveBeenCalledTimes(1);
  // (one remove button: of the whole, not of each citation of the basis)
  const removes = buttons.filter((button) => button !== seen);
  expect(removes).toHaveLength(1);
  removes[0]!.click();
  expect(onRemove).toHaveBeenCalledTimes(1);
  // (with no mark there is nothing to have seen)
  const plain = shown(basis(), { onRemove, onSeen });
  expect([...plain.querySelectorAll("button")].some((button) => button.textContent === "Seen")).toBe(false);
});
