// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { ModelsProvider } from "../context";
import type { ModelDefinition, ModelDefinitions } from "../types";
import { ContextFrames } from "./ContextFrames";

const model = (name: string, kind: string) =>
  ({ name, kind, parent: null, abstract: false, concreteTypes: [name], fields: [], incoming: [] }) as unknown as ModelDefinition;

const definitions = {
  models: { Negative: model("Negative", "SemanticSpace"), Order: model("Order", "Document") },
} as unknown as ModelDefinitions;

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

function show(path: { type: string; id?: string }[]) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ModelsProvider definitions={definitions}>
        <ContextFrames path={path}>
          <p id="item">the item</p>
        </ContextFrames>
      </ModelsProvider>
    ),
    container,
  );
  return container;
}

test("a semantic space round an item is a band, and a document is its head, a link, with a rule down the side", () => {
  const host = show([{ type: "Negative" }, { type: "Order", id: "o 1" }]);
  const label = host.querySelector('[data-type-info="Negative"]')!;
  expect(label.closest("a")).toBeNull();
  const head = host.querySelector<HTMLAnchorElement>('a:has([data-type-info="Order"])')!;
  expect(head.getAttribute("href")).toBe("/Order/o%201");
  // (the document has no band of its own: what is in it is under the rule)
  const rule = host.querySelector("#item")!.closest(".border-l-2")!;
  expect(rule.parentElement!.contains(head)).toBe(true);
  expect(label.parentElement!.contains(rule)).toBe(true);
});

test("an item that is in nothing is only itself", () => {
  const host = show([]);
  expect(host.firstElementChild!.id).toBe("item");
});
