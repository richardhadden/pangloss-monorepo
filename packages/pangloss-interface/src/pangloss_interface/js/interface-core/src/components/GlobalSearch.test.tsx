// @vitest-environment happy-dom
import { flush } from "solid-js";
import { render } from "@solidjs/web";
import { afterEach, expect, test, vi } from "vitest";
import { ApiProvider, ComponentsProvider, ModelsProvider } from "../context";
import type { ApiClient } from "../api";
import type { ModelDefinitions } from "../types";
import { GlobalSearch } from "./GlobalSearch";

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

const definitions = {
  models: {
    Person: { name: "Person", kind: "Entity", abstract: false, createDirectly: true, globalSearch: true },
  },
} as unknown as ModelDefinitions;

function setup(results = [{ id: "1", type: "Person", label: "Smith" }]) {
  const get = vi.fn(async () => ({ results, count: results.length }));
  const host = document.createElement("div");
  document.body.append(host);
  const components = {
    ReferenceChip: (props: { label: string; href?: string }) => <a href={props.href}>{props.label}</a>,
  } as never;
  dispose = render(
    () => (
      <ComponentsProvider components={components}>
        <ApiProvider client={{ get } as unknown as ApiClient}>
          <ModelsProvider definitions={definitions}>
            <GlobalSearch />
          </ModelsProvider>
        </ApiProvider>
      </ComponentsProvider>
    ),
    host,
  );
  const box = host.querySelector("input")!;
  const type = (text: string) => {
    box.value = text;
    box.dispatchEvent(new InputEvent("input", { bubbles: true }));
  };
  const key = (name: string) => {
    box.setSelectionRange(0, 0);
    box.dispatchEvent(new KeyboardEvent("keydown", { key: name, bubbles: true, cancelable: true }));
  };
  const chip = () => host.querySelector("[data-testid=search-type-chip]");
  const settle = async () => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    flush();
  };
  return { get, host, box, type, key, chip, settle };
}

test("nothing is asked until words are typed; then the results are chips that are links", async () => {
  const { get, host, type, settle } = setup();
  await settle();
  expect(get).not.toHaveBeenCalled();
  type("smith");
  await settle();
  expect(get).toHaveBeenCalledWith("/search-everything", { q: "smith", type: undefined, page_size: 25 });
  expect(host.querySelector("li a")?.getAttribute("href")).toBe("/Person/1");
});

test("a finished word that names a type becomes a chip, and narrows the search", async () => {
  const { get, box, type, chip, settle } = setup();
  type("person ");
  flush();
  expect(chip()?.textContent).toBe("Person");
  expect(box.value).toBe("");
  await settle();
  // (the chip alone: the most connected of the type)
  expect(get).toHaveBeenLastCalledWith("/search-everything", { q: "", type: ["Person"], page_size: 25 });
  type("smith");
  await settle();
  expect(get).toHaveBeenLastCalledWith("/search-everything", { q: "smith", type: ["Person"], page_size: 25 });
});

test("Backspace against the chip gives the word back, and it does not become a chip again", async () => {
  const { box, type, key, chip } = setup();
  type("person ");
  flush();
  type("smith");
  key("Backspace");
  flush();
  expect(chip()).toBeNull();
  expect(box.value).toBe("person smith");
  type("person smith ");
  flush();
  expect(chip()).toBeNull();
});

test("when nothing is found it says so", async () => {
  const { host, type, settle } = setup([]);
  type("nobody");
  await settle();
  expect(host.textContent).toContain("Nothing found");
});
