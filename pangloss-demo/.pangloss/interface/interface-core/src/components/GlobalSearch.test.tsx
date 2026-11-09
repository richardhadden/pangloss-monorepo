// @vitest-environment happy-dom
import { createSignal, flush } from "solid-js";
import { render } from "@solidjs/web";
import { afterEach, expect, test, vi } from "vitest";
import { ApiProvider, ComponentsProvider, ModelsProvider, SearchAddressProvider } from "../context";
import type { SearchAddress } from "../context";
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
    CertifiedTranscription: { name: "CertifiedTranscription", kind: "Document", abstract: false, createDirectly: true, globalSearch: true },
    Certificate: { name: "Certificate", kind: "Document", abstract: false, createDirectly: true, globalSearch: true },
  },
} as unknown as ModelDefinitions;

function setup(results = [{ id: "1", type: "Person", label: "Smith" }], address: SearchAddress | null = null) {
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
            <SearchAddressProvider value={address}>
              <GlobalSearch />
            </SearchAddressProvider>
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
  const press = (name: string) => {
    box.dispatchEvent(new KeyboardEvent("keydown", { key: name, bubbles: true, cancelable: true }));
    flush();
  };
  const options = () => [...host.querySelectorAll("[role=option]")].map((option) => option.textContent);
  const completion = () => host.querySelector("[data-testid=search-type-completion]")?.textContent;
  const key = (name: string) => {
    box.setSelectionRange(0, 0);
    press(name);
  };
  const chip = () => host.querySelector("[data-testid=search-type-chip]");
  const settle = async () => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    flush();
  };
  return { get, host, box, type, key, press, options, completion, chip, settle };
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

test("the types a word could be are offered, and the rest of the first is shown after it", () => {
  const { type, options, completion } = setup();
  type("cert");
  flush();
  expect(options()).toEqual(["Certificate", "Certified Transcription"]);
  expect(completion()).toBe("certificate");
  type("smith");
  flush();
  expect(options()).toEqual([]);
});

test("Tab takes the first, and searches by it", async () => {
  const { get, type, press, chip, box, options, settle } = setup();
  type("smith cert");
  flush();
  press("Tab");
  expect(chip()?.textContent).toBe("Certificate");
  expect(box.value).toBe("smith ");
  expect(options()).toEqual([]);
  await settle();
  expect(get).toHaveBeenLastCalledWith("/search-everything", { q: "smith", type: ["Certificate"], page_size: 25 });
});

test("the arrows choose another, and the completion and Enter follow", () => {
  const { type, press, chip, completion, host } = setup();
  type("cert");
  flush();
  press("ArrowDown");
  press("ArrowDown");
  expect(host.querySelector("[aria-selected=true]")?.textContent).toBe("Certified Transcription");
  expect(completion()).toBe("certified Transcription");
  press("Enter");
  expect(chip()?.getAttribute("data-type-info")).toBe("CertifiedTranscription");
});

test("Enter does not take a type unless one has been chosen", async () => {
  const { type, press, chip, host, settle } = setup();
  type("cert");
  await settle();
  const clicked = vi.fn((event: Event) => event.preventDefault());
  host.querySelector("li a")?.addEventListener("click", clicked);
  press("Enter");
  expect(chip()).toBeNull();
  expect(clicked).toHaveBeenCalledOnce();
});

test("Escape closes the list and leaves the box, and a click takes a type", () => {
  const { box, type, press, options, chip, host } = setup();
  type("cert");
  flush();
  press("Escape");
  expect(options()).toEqual([]);
  expect(box.value).toBe("cert");
  type("certi");
  flush();
  host.querySelector("[role=option]")?.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
  flush();
  expect(chip()).not.toBeNull();
});

test("a word turned back from a chip is not offered again", () => {
  const { type, press, key, options, box } = setup();
  type("cert");
  flush();
  press("Tab");
  key("Backspace");
  expect(box.value).toBe("Certificate");
  expect(options()).toEqual([]);
});

test("a word that only begins a longer name stays a word at the space, with the names still offered", () => {
  const { type, chip, options, box } = setup();
  type("certified ");
  flush();
  expect(chip()).toBeNull();
  expect(box.value).toBe("certified ");
  expect(options()).toEqual(["Certified Transcription"]);
});

test("under the results, a link to the list of each type found, with the words but not the type", async () => {
  const { type, host, settle } = setup([
    { id: "1", type: "Person", label: "Smith" },
    { id: "2", type: "Certificate", label: "Smith's" },
    { id: "3", type: "Person", label: "Smithson" },
  ]);
  type("person ");
  flush();
  type("john  smith");
  await settle();
  const more = [...host.querySelectorAll("[data-testid=search-more]")].map((link) => link.getAttribute("href"));
  expect(more).toEqual(["/Person?q=john%20%20smith", "/Certificate?q=john%20%20smith"]);
  expect(host.querySelector("hr")).not.toBeNull();
});

test("a type by itself links to the whole list; nothing found, no links", async () => {
  const shown = setup();
  shown.type("person ");
  await shown.settle();
  expect(shown.host.querySelector("[data-testid=search-more]")?.getAttribute("href")).toBe("/Person");
  dispose?.();
  document.body.innerHTML = "";
  const none = setup([]);
  none.type("nobody");
  await none.settle();
  expect(none.host.querySelector("[data-testid=search-more]")).toBeNull();
  expect(none.host.querySelector("hr")).toBeNull();
});

function addressOf(q: string, type?: string) {
  const [read, write] = createSignal<{ q: string; type?: string }>({ q, type });
  const set = vi.fn((search: { q: string; type?: string }) => void write(search));
  const value: SearchAddress = { q: () => read().q, type: () => read().type, set };
  return { value, set, write };
}

test("the search in the address is in the box, with its type, and is made at once", async () => {
  const { value } = addressOf("smith", "Person");
  const { get, box, chip, host, settle } = setup(undefined, value);
  await settle();
  expect(box.value).toBe("smith");
  expect(chip()?.textContent).toBe("Person");
  expect(get).toHaveBeenCalledWith("/search-everything", { q: "smith", type: ["Person"], page_size: 25 });
  expect(host.querySelector("li a")).not.toBeNull();
});

test("what is typed goes to the address, words and type apart", async () => {
  const { value, set } = addressOf("");
  const { type, settle } = setup(undefined, value);
  type("person ");
  flush();
  type("smith");
  await settle();
  expect(set).toHaveBeenLastCalledWith({ q: "smith", type: "Person" });
});

test("the address changing otherwise is shown; a type it cannot be narrowed to is ignored", async () => {
  const { value, write } = addressOf("smith", "Person");
  const { box, chip, settle, get } = setup(undefined, value);
  await settle();
  write({ q: "jones", type: "NoSuchThing" });
  await settle();
  expect(box.value).toBe("jones");
  expect(chip()).toBeNull();
  expect(get).toHaveBeenLastCalledWith("/search-everything", { q: "jones", type: undefined, page_size: 25 });
});

function selectAll(box: HTMLInputElement) {
  box.setSelectionRange(0, box.value.length);
  box.dispatchEvent(new KeyboardEvent("keydown", { key: "a", metaKey: true, bubbles: true, cancelable: true }));
  flush();
}

test("select all takes in the chip, and Backspace then empties everything", async () => {
  const { get, box, type, press, chip, settle } = setup();
  type("person ");
  flush();
  type("smith");
  await settle();
  selectAll(box);
  expect(chip()?.hasAttribute("data-selected")).toBe(true);
  press("Backspace");
  expect(chip()).toBeNull();
  expect(box.value).toBe("");
  const calls = get.mock.calls.length;
  await settle();
  expect(get.mock.calls.length).toBe(calls);
});

test("select all with only a chip, and Delete, removes it rather than giving the word back", () => {
  const { box, type, press, chip } = setup();
  type("person ");
  flush();
  selectAll(box);
  press("Delete");
  expect(chip()).toBeNull();
  expect(box.value).toBe("");
});

test("typing over everything selected replaces the chip too; an arrow only unselects it", () => {
  const { box, type, press, chip } = setup();
  type("person ");
  flush();
  type("smith");
  selectAll(box);
  press("ArrowLeft");
  expect(chip()?.hasAttribute("data-selected")).toBe(false);
  selectAll(box);
  type("j");
  flush();
  expect(chip()).toBeNull();
  expect(box.value).toBe("j");
});

