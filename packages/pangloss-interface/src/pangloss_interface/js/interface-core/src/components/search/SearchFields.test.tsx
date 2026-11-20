// @vitest-environment happy-dom
import { flush } from "solid-js";
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import type { ApiClient } from "../../api";
import { ApiProvider, ComponentsProvider, ModelsProvider } from "../../context";
import { compileSearch } from "../../schema";
import type { NodeSearch } from "../../schema";
import type { ComponentMap, ModelDefinition, ModelDefinitions } from "../../types";
import { ReferenceChip } from "../ReferenceChip";
import { SearchFields } from "./SearchFields";
import type { SearchFieldsControl } from "./SearchFields";

const model = (name: string, kind: string) =>
  ({ name, kind, parent: null, abstract: false, concreteTypes: [name], fields: [], incoming: [], interfaceMeta: null }) as unknown as ModelDefinition;

// (a Letter has a year and a sender, and can be ordered by its year)
const definitions = {
  models: { Letter: model("Letter", "Document"), Person: model("Person", "Entity") },
  enums: {},
  searchPatterns: {
    Letter: {
      kind: "document",
      fields: {
        year: { operators: "compare", value: { type: "int" } },
        sender: { operators: "relation", targets: ["Person"] },
      },
      orderBy: ["label", "year"],
    },
    Person: { kind: "entity", fields: {}, orderBy: [] },
  },
} as unknown as ModelDefinitions;

const client = {
  baseUrl: "/api",
  get: async () => ({ results: [], count: 0 }),
  post: async () => ({ types: {} }),
} as unknown as ApiClient;

const settle = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));
let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

function show(props: { initial?: NodeSearch; order?: boolean } = {}) {
  const said: NodeSearch[] = [];
  const held: { control?: SearchFieldsControl } = {};
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ComponentsProvider components={{ ReferenceChip } as unknown as ComponentMap}>
        <ModelsProvider definitions={definitions}>
          <ApiProvider client={client}>
            <SearchFields
              type="Letter"
              initial={props.initial}
              order={props.order}
              onChange={(form) => said.push(form)}
              control={(control) => (held.control = control)}
            />
          </ApiProvider>
        </ModelsProvider>
      </ComponentsProvider>
    ),
    container,
  );
  return { said, held };
}

const byLabel = <T extends HTMLElement>(label: string) => document.body.querySelector<T>(`[aria-label="${label}"]`)!;
const click = (element: Element | null | undefined) => {
  (element as HTMLElement).dispatchEvent(new MouseEvent("click", { bubbles: true }));
  flush();
};
const type = (label: string, text: string) => {
  const input = byLabel<HTMLInputElement>(label);
  input.value = text;
  input.dispatchEvent(new InputEvent("input", { bubbles: true }));
  flush();
};
const addMenu = () => document.body.querySelector<HTMLElement>('[role="combobox"][aria-label="Add a filter"]')!;
const options = () => {
  const menu = addMenu();
  if (menu.getAttribute("aria-expanded") !== "true") click(menu);
  return [...document.getElementById(menu.getAttribute("aria-controls")!)!.querySelectorAll<HTMLElement>('[role="option"]')];
};
const offered = () => {
  const texts = options().map((option) => option.textContent);
  click(addMenu());
  return texts;
};
const add = (name: string) => click(options().find((option) => option.dataset.value!.endsWith(`:${name}`)));
const names = () => [...document.body.querySelectorAll("dt:not(.sr-only)")].map((dt) => dt.textContent);

test("the fields of a type, with nothing round them: no panel, no saved searches, no Clear or Close", () => {
  show();
  expect(document.body.querySelector("section")).toBeNull();
  expect([...document.body.querySelectorAll("button")].map((b) => b.textContent?.trim())).not.toContain("Clear");
  expect(offered()).toEqual(["Label", "year", "sender", "Mentions", "Contains", "Any of", "Order by"]);
});

test("with order={false} no Order by is offered", () => {
  show({ order: false });
  expect(offered()).toEqual(["Label", "year", "sender", "Mentions", "Contains", "Any of"]);
});

test("a change is said a moment later as the form, which compiles to the pattern; Enter says it at once", async () => {
  const { said } = show({ order: false });
  add("year");
  type("year", "1500");
  expect(said).toHaveLength(0);
  await settle(300);
  expect(compileSearch(said.at(-1))).toEqual({ year: { eq: 1500 } });
  type("year", "1600");
  byLabel("year").dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  expect(compileSearch(said.at(-1))).toEqual({ year: { eq: 1600 } });
});

test("what it is given to start with is shown, and a holder can read and replace it", async () => {
  const initial: NodeSearch = { type: "Letter", fields: { year: { op: "gt", value: 1600 } } };
  const { said, held } = show({ initial });
  expect(names()).toEqual(["year"]);
  expect(byLabel<HTMLInputElement>("year").value).toBe("1600");
  expect(held.control!.current()).toEqual(initial);
  held.control!.replace({ type: "Letter" });
  flush();
  expect(names()).toEqual([]);
  expect(said.at(-1)).toEqual({ type: "Letter" });
});
