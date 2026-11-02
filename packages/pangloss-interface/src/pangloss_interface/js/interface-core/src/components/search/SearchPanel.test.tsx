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
import { SearchPanel } from "./SearchPanel";

const model = (name: string, kind: string, extra: Partial<ModelDefinition> = {}) =>
  ({
    name,
    kind,
    parent: null,
    abstract: false,
    concreteTypes: [name],
    fields: [],
    incoming: [],
    interfaceMeta: null,
    ...extra,
  }) as unknown as ModelDefinition;

// (a Letter has a year, a sender (a person), statements (activities) and a date; a Person is sent letters)
const definitions = {
  models: {
    Letter: model("Letter", "Document"),
    Activity: model("Activity", "Document"),
    Day: model("Day", "Embedded"),
    Person: model("Person", "Entity", {
      incoming: [{ name: "sent", key: "sent", sources: [{ model: "Letter", field: "sender", viaReified: false }] }],
    }),
  },
  enums: { Kind: { name: "Kind", members: [{ name: "MEETING", value: "meeting" }, { name: "BATTLE", value: "battle" }] } },
  searchPatterns: {
    Letter: {
      kind: "document",
      fields: {
        year: { operators: "compare", value: { type: "int" } },
        kind: { operators: "choice", value: { type: "enum", enum: "Kind" } },
        sender: { operators: "relation", targets: ["Person"] },
        statements: { operators: "relation", targets: ["Activity"] },
        when: { operators: "relation", targets: ["Day"] },
      },
      orderBy: [],
    },
    Activity: { kind: "document", fields: { text: { operators: "text", value: { type: "str" } } }, orderBy: [] },
    Day: { kind: "embedded", fields: { day: { operators: "compare", value: { type: "int" } } }, orderBy: [] },
    Person: { kind: "entity", fields: {}, orderBy: [] },
  },
} as unknown as ModelDefinitions;

// (every entity search finds Alice and Bob)
const client = {
  baseUrl: "/api",
  get: async () => ({
    results: [
      { id: "p1", type: "Person", label: "Alice" },
      { id: "p2", type: "Person", label: "Bob" },
    ],
    count: 2,
  }),
} as unknown as ApiClient;

const settle = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));
let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
  localStorage.clear();
});

function show(type: string, initial?: NodeSearch) {
  const said: NodeSearch[] = [];
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ComponentsProvider components={{ ReferenceChip } as unknown as ComponentMap}>
        <ModelsProvider definitions={definitions}>
          <ApiProvider client={client}>
            <SearchPanel type={type} initial={initial} open onChange={(form) => said.push(form)} onClose={() => {}} />
          </ApiProvider>
        </ModelsProvider>
      </ComponentsProvider>
    ),
    container,
  );
  // (what it said last, as the pattern of the API)
  return () => compileSearch(said.at(-1));
}

const byLabel = <T extends HTMLElement>(label: string) =>
  document.body.querySelector<T>(`[aria-label="${label}"]`)!;
const type = (label: string, text: string) => {
  const input = byLabel<HTMLInputElement>(label);
  input.value = text;
  input.dispatchEvent(new InputEvent("input", { bubbles: true }));
  flush();
};
const choose = (label: string, value: string) => {
  const select = byLabel<HTMLSelectElement>(label);
  select.value = value;
  select.dispatchEvent(new Event("change", { bubbles: true }));
  flush();
};
const click = (element: Element | null | undefined) => {
  (element as HTMLElement).dispatchEvent(new MouseEvent("click", { bubbles: true }));
  flush();
};
const button = (name: string) =>
  [...document.body.querySelectorAll<HTMLElement>("button")].find(
    (b) => b.textContent?.trim() === name || b.getAttribute("aria-label") === name,
  );
const names = () => [...document.body.querySelectorAll("dt")].map((dt) => dt.textContent);

test("a row for each field of the type, as the entry form has them, and Mentions for a document", () => {
  show("Letter");
  expect(names()).toEqual(["Label", "year", "kind", "sender", "statements", "when", "Mentions"]);
  // (each with its operators)
  const operators = [...byLabel<HTMLSelectElement>("Condition on year").options].map((option) => option.text);
  expect(operators).toEqual(["=", ">", "≥", "<", "≤", "between", "has a value", "has no value"]);
  const sender = [...byLabel<HTMLSelectElement>("Condition on sender").options].map((option) => option.value);
  expect(sender).toEqual(["any", "all", "match", "exists", "missing"]);
});

test("a change is said a moment later, as a condition of the operator on show", async () => {
  const pattern = show("Letter");
  type("Label", "rome");
  flush();
  expect(pattern()).toBeUndefined();
  await settle(300);
  expect(pattern()).toEqual({ label: { contains: "rome" } });
  // (Enter does not wait)
  choose("Condition on Label", "starts_with");
  byLabel("Label").dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  expect(pattern()).toEqual({ label: { starts_with: "rome" } });
});

test("a number is a number; between keeps what was given as its first end; not negates the condition", async () => {
  const pattern = show("Letter");
  type("year", "1500");
  choose("Condition on year", "between");
  flush();
  expect(byLabel<HTMLInputElement>("year from").value).toBe("1500");
  type("year to", "1600");
  click(button("Not: year"));
  await settle(300);
  expect(pattern()).toEqual({ $not: { year: { between: [1500, 1600] } } });
  expect(byLabel("Not: year").getAttribute("aria-pressed")).toBe("true");
});

test("the values of an enum are pills, any number of them chosen", async () => {
  const pattern = show("Letter");
  click(button("MEETING"));
  click(button("BATTLE"));
  await settle(300);
  expect(pattern()).toEqual({ kind: { in: ["meeting", "battle"] } });
});

test("entities are picked as in the entry form, and taken out by their chips", async () => {
  const pattern = show("Letter");
  const box = byLabel<HTMLInputElement>("Find Person…");
  box.dispatchEvent(new FocusEvent("focus"));
  box.value = "a";
  box.dispatchEvent(new InputEvent("input", { bubbles: true }));
  await settle(300);
  box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await settle(300);
  expect(pattern()).toEqual({ sender: { is_any: ["p1"] } });
  choose("Condition on sender", "all");
  await settle(300);
  expect(pattern()).toEqual({ sender: { is: "p1" } });
  click(button("Remove Alice"));
  await settle(300);
  expect(pattern()).toBeUndefined();
});

test("a document or embedded field is a form of its own type, nested", async () => {
  const pattern = show("Letter");
  // (one type to choose: the button chooses it)
  const [statements, when] = [...document.body.querySelectorAll("button")].filter(
    (b) => b.textContent?.trim() === "Choose a type",
  );
  click(statements);
  click(when);
  flush();
  expect(document.body.querySelector('[data-search-node="Activity"]')).not.toBeNull();
  type("text", "battle");
  type("day", "3");
  choose("Condition on day", "lt");
  await settle(300);
  expect(pattern()).toEqual({
    statements: { type: "Activity", where: { text: { contains: "battle" } } },
    when: { type: "Day", where: { day: { lt: 3 } } },
  });
});

test("an entity is found by what refers to it, with a form for that", async () => {
  const pattern = show("Person");
  expect(names()).toEqual(["Label", "Referred to by"]);
  choose("Add what refers to it", "0");
  flush();
  type("year", "1500");
  choose("Condition on year", "gt");
  await settle(300);
  expect(pattern()).toEqual({
    $incoming: [{ type: "Letter", field: "sender", where: { year: { gt: 1500 } } }],
  });
  click(button("Not: Letter · sender"));
  await settle(300);
  expect(pattern()).toEqual({
    $not: { $incoming: [{ type: "Letter", field: "sender", where: { year: { gt: 1500 } } }] },
  });
});

test("it starts from what it is given, and Clear takes everything out at once", () => {
  const pattern = show("Letter", { type: "Letter", fields: { year: { op: "gt", value: 1500 } } });
  expect(byLabel<HTMLSelectElement>("Condition on year").value).toBe("gt");
  expect(byLabel<HTMLInputElement>("year").value).toBe("1500");
  click(button("Clear"));
  expect(pattern()).toBeUndefined();
  flush();
  expect(byLabel<HTMLInputElement>("year").value).toBe("");
});
