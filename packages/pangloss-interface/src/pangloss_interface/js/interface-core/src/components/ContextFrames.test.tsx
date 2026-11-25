// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import type { PathEntry } from "../api";
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

function show(path: PathEntry[]) {
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

const at = (kind: PathEntry["kind"], type: string, id: string, field: string): PathEntry => ({ kind, type, id, field });

test("a semantic space round an item is a band, and a document is its head, a link, with a rule down the side", () => {
  const host = show([at("space", "Negative", "n1", "contents"), at("document", "Order", "o 1", "thing_ordered")]);
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

test("a document says the field that holds what follows, between its head and what is in it; a space does not", () => {
  const host = show([at("space", "Negative", "n1", "contents"), at("document", "Order", "o1", "thing_ordered")]);
  const fields = [...host.querySelectorAll<HTMLElement>("[data-context-field]")];
  expect(fields.map((field) => [field.dataset.contextField, field.textContent])).toEqual([
    ["thing_ordered", "thing ordered"],
  ]);
  const head = host.querySelector('a:has([data-type-info="Order"])')!;
  const item = host.querySelector("#item")!;
  expect(head.compareDocumentPosition(fields[0]!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(fields[0]!.compareDocumentPosition(item) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("a band or a frame is chosen by the entry's kind, not by the model: a document the models do not know is a frame", () => {
  const host = show([at("document", "Unknown", "u1", "parts")]);
  expect(host.querySelector<HTMLAnchorElement>('a:has([data-type-info="Unknown"])')!.getAttribute("href")).toBe("/Unknown/u1");
  expect(host.querySelector("[data-context-field]")!.textContent).toBe("parts");
});

test("documents nested in documents are frames inside frames, each with its field, outermost first", () => {
  const host = show([at("document", "Order", "o1", "carried_out"), at("document", "Order", "o2", "parts")]);
  const fields = [...host.querySelectorAll<HTMLElement>("[data-context-field]")].map((field) => field.dataset.contextField);
  expect(fields).toEqual(["carried_out", "parts"]);
});
