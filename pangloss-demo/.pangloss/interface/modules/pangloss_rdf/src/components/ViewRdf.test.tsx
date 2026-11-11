// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { flush } from "solid-js";
import { afterEach, expect, test } from "vitest";
import type { ConsoleActionProps } from "@pangloss/interface-core";
import ViewRdf from "./ViewRdf";

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

const show = (page: string, id = "p1") => {
  const host = document.createElement("div");
  document.body.append(host);
  dispose = render(() => <ViewRdf {...({ type: "Person", id, page } as unknown as ConsoleActionProps)} />, host);
  flush();
  return host;
};
const opener = (host: HTMLElement) => host.querySelector<HTMLElement>("button")!;
const items = () => [...document.querySelectorAll<HTMLAnchorElement>('[role="menuitem"]')];
const press = (target: HTMLElement, key: string) => {
  target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  flush();
};

test("the menu has each format of the item, and the API's own JSON last, each in a new tab", () => {
  const host = show("item");
  expect(items()).toHaveLength(0);
  opener(host).click();
  flush();
  expect(items().map((item) => item.textContent)).toEqual(["Turtle", "JSON-LD", "TriG", "N-Triples", "N-Quads", "API JSON"]);
  expect(items().map((item) => item.getAttribute("href"))).toEqual([
    "/api/rdf/Person/p1?format=ttl&view=true",
    "/api/rdf/Person/p1?format=jsonld&view=true",
    "/api/rdf/Person/p1?format=trig&view=true",
    "/api/rdf/Person/p1?format=nt&view=true",
    "/api/rdf/Person/p1?format=nq&view=true",
    "/api/Person/p1",
  ]);
  expect(items().every((item) => item.target === "_blank")).toBe(true);
  expect(opener(host).getAttribute("aria-pressed")).toBe("true");
});

test("an id that is an address is escaped in the links", () => {
  const host = show("item", "http://example.org/a b");
  opener(host).click();
  flush();
  expect(items()[0]!.getAttribute("href")).toBe("/api/rdf/Person/http%3A%2F%2Fexample.org%2Fa%20b?format=ttl&view=true");
  expect(items().at(-1)!.getAttribute("href")).toBe("/api/Person/http%3A%2F%2Fexample.org%2Fa%20b");
});

test("it is only on the page of an item, not on its form", () => {
  expect(show("edit").querySelector("button")).toBeNull();
});

test("the button, a click elsewhere, Escape and choosing a format each close it", () => {
  const host = show("item");
  opener(host).click();
  flush();
  opener(host).click();
  flush();
  expect(items()).toHaveLength(0);

  opener(host).click();
  flush();
  document.body.click();
  flush();
  expect(items()).toHaveLength(0);

  opener(host).click();
  flush();
  press(opener(host), "Escape");
  expect(items()).toHaveLength(0);

  opener(host).click();
  flush();
  // (a link: stop it leaving the test's page)
  items()[0]!.addEventListener("click", (event) => event.preventDefault());
  items()[0]!.click();
  flush();
  expect(items()).toHaveLength(0);
});

test("Down opens it at the first, Up at the last, and they go round; Tab closes it", () => {
  const host = show("item");
  press(opener(host), "ArrowDown");
  expect(document.activeElement?.textContent).toBe("Turtle");
  press(document.activeElement as HTMLElement, "ArrowUp");
  expect(document.activeElement?.textContent).toBe("API JSON");
  press(document.activeElement as HTMLElement, "ArrowDown");
  expect(document.activeElement?.textContent).toBe("Turtle");
  press(document.activeElement as HTMLElement, "Tab");
  expect(items()).toHaveLength(0);

  press(opener(host), "ArrowUp");
  expect(document.activeElement?.textContent).toBe("API JSON");
});
