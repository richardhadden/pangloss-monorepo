// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import type { ApiClient, Summary } from "../../api";
import { ApiProvider, ModelsProvider } from "../../context";
import type { ModelDefinition, ModelDefinitions } from "../../types";
import { EntityPicker } from "./EntityPicker";

const definitions = {
  models: { Person: { name: "Person", kind: "Entity", parent: null, abstract: false, fields: [] } as unknown as ModelDefinition },
  enums: {},
} as unknown as ModelDefinitions;

const person = (id: string, label: string): Summary => ({ id, type: "Person", label }) as Summary;

// A client whose searches are answered when the test says (`answer`), or fail (`fail`), each by its words
function slowClient() {
  const waiting = new Map<string, { resolve: (value: unknown) => void; reject: (error: unknown) => void }>();
  const asked: string[] = [];
  const client = {
    baseUrl: "/api",
    get: (path: string, params?: Record<string, unknown>) => {
      const q = params?.q as string | undefined;
      // (the most used, asked for as the box is drawn: none)
      if (path !== "/autocomplete" || q === undefined) return Promise.resolve({ results: [], count: 0 });
      asked.push(q);
      return new Promise((resolve, reject) => waiting.set(q, { resolve, reject }));
    },
  } as unknown as ApiClient;
  return {
    client,
    asked,
    answer: (q: string, results: Summary[]) => waiting.get(q)!.resolve({ results, count: results.length }),
    fail: (q: string) => waiting.get(q)!.reject(new Error("down")),
  };
}

const settle = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));
let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
  localStorage.clear();
});

function show(client: ApiClient, picked: Summary[] = []) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <ApiProvider client={client}>
        <ModelsProvider definitions={definitions}>
          <EntityPicker types={["Person"]} onPick={(entity) => picked.push(entity)} />
        </ModelsProvider>
      </ApiProvider>
    ),
    container,
  );
  return container.querySelector<HTMLInputElement>('[role="combobox"]')!;
}

function type(box: HTMLInputElement, text: string) {
  box.value = text;
  box.dispatchEvent(new InputEvent("input", { bubbles: true }));
}

const options = () => [...document.body.querySelectorAll('[role="option"]')].map((option) => option.textContent);
const spinning = () => document.body.querySelector(".animate-spin") !== null;

test("a search is made a moment after the last key, with a spinner until it is answered", async () => {
  const api = slowClient();
  const box = show(api.client);
  await settle();
  box.dispatchEvent(new FocusEvent("focus"));
  type(box, "al");
  type(box, "ali");
  await settle(300);
  expect(api.asked).toEqual(["ali"]);
  expect(spinning()).toBe(true);
  api.answer("ali", [person("p1", "Alice")]);
  await settle();
  expect(spinning()).toBe(false);
  expect(options()).toEqual(["PersonAlice"]);
});

test("an answer for words that have been typed over is not shown", async () => {
  const api = slowClient();
  const box = show(api.client);
  await settle();
  box.dispatchEvent(new FocusEvent("focus"));
  type(box, "al");
  await settle(300);
  type(box, "bo");
  await settle(300);
  expect(api.asked).toEqual(["al", "bo"]);
  api.answer("bo", [person("p2", "Bob")]);
  await settle();
  expect(options()).toEqual(["PersonBob"]);
  // (the older answer comes last, and is not shown)
  api.answer("al", [person("p1", "Alice")]);
  await settle();
  expect(options()).toEqual(["PersonBob"]);
  expect(spinning()).toBe(false);
});

test("what is typed is not held up by a search being answered", async () => {
  const api = slowClient();
  const box = show(api.client);
  await settle();
  box.dispatchEvent(new FocusEvent("focus"));
  type(box, "ali");
  await settle(300);
  type(box, "alic");
  await settle();
  expect(box.value).toBe("alic");
  // (no match is shown for words that have not been answered: Alice's answer was for "ali")
  api.answer("ali", [person("p1", "Alice")]);
  await settle();
  expect(box.value).toBe("alic");
  expect(options()).toEqual([]);
  expect(document.body.textContent).not.toContain("Nothing found");
});

test("nothing found is said once the search has answered", async () => {
  const api = slowClient();
  const box = show(api.client);
  await settle();
  box.dispatchEvent(new FocusEvent("focus"));
  type(box, "zz");
  await settle(300);
  expect(document.body.textContent).not.toContain("Nothing found");
  api.answer("zz", []);
  await settle();
  expect(document.body.textContent).toContain("Nothing found");
});

test("a search that fails says so, and the same words typed again are asked again", async () => {
  const api = slowClient();
  const picked: Summary[] = [];
  const box = show(api.client, picked);
  await settle();
  box.dispatchEvent(new FocusEvent("focus"));
  type(box, "ali");
  await settle(300);
  api.fail("ali");
  await settle();
  expect(document.body.querySelector('[role="alert"]')?.textContent).toBe("The search failed");
  expect(spinning()).toBe(false);
  type(box, "ali");
  await settle(300);
  expect(api.asked).toEqual(["ali", "ali"]);
  api.answer("ali", [person("p1", "Alice")]);
  await settle();
  expect(document.body.querySelector('[role="alert"]')).toBeNull();
  (document.body.querySelector('[role="option"]') as HTMLElement).click();
  await settle();
  expect(picked).toEqual([person("p1", "Alice")]);
  expect(box.value).toBe("");
});

test("clearing the box stops waiting for a search", async () => {
  const api = slowClient();
  const box = show(api.client);
  await settle();
  box.dispatchEvent(new FocusEvent("focus"));
  type(box, "ali");
  await settle(300);
  expect(spinning()).toBe(true);
  type(box, "");
  await settle();
  expect(spinning()).toBe(false);
});
