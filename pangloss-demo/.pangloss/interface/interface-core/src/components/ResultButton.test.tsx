// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { expect, test } from "vitest";
import { ModelsProvider, ModulesProvider } from "../context";
import type { ModuleManifest, ResultMarkProps } from "../types";
import { ResultButton } from "./ResultButton";

function show(spaces?: string[], head?: { type: string; id: string }) {
  const host = document.createElement("div");
  render(
    () => (
      <ModelsProvider definitions={{ models: {}, enums: {} }}>
        <ResultButton href="/Activity/1" type="Activity" label="A coronation" spaces={spaces} head={head} />
      </ModelsProvider>
    ),
    host,
  );
  return host;
}

test("an item in no space is only its button", () => {
  const host = show([]);
  expect(host.querySelector("a")?.textContent).toContain("A coronation");
  expect(host.textContent).not.toContain("Negative");
});

test("each space is a band round the next, the names outermost first, the button innermost", () => {
  const host = show(["Negative", "Hypothetical"]);
  const text = host.textContent ?? "";
  expect(text.indexOf("Negative")).toBeLessThan(text.indexOf("Hypothetical"));
  expect(text.indexOf("Hypothetical")).toBeLessThan(text.indexOf("A coronation"));
  // (the link is inside both bands)
  const link = host.querySelector("a")!;
  expect(link.parentElement?.parentElement?.textContent).toContain("Hypothetical");
  expect(host.firstElementChild?.textContent).toContain("Negative");
});

test("a space with a colour of its model is that colour, whatever its depth", () => {
  const host = document.createElement("div");
  const space = (colour: "teal" | null) => ({
    name: "Negative",
    kind: "SemanticSpace",
    interfaceMeta: colour ? { colour } : null,
  });
  render(
    () => (
      <ModelsProvider
        definitions={{ models: { Negative: space("teal") } as never, enums: {} }}
      >
        <ResultButton href="/Activity/1" type="Activity" label="x" spaces={["Negative"]} />
      </ModelsProvider>
    ),
    host,
  );
  expect(host.querySelector(".bg-teal-400\\/15")?.textContent).toContain("Negative");
});

test("an item inside a document has a button to it, at the far right, not in the bands", () => {
  const host = show(["Negative"], { type: "Factoid", id: "f1" });
  const links = host.querySelectorAll("a");
  expect(links).toHaveLength(2);
  const last = links[1];
  expect(last.getAttribute("href")).toBe("/Factoid/f1");
  // (after the bands: the name of the band comes before it)
  expect(host.textContent).toContain("Negative");
  expect(last.previousElementSibling?.textContent).toContain("Negative");
  expect(last.textContent).not.toContain("Negative");
});

test("an item that is a head node has no such button", () => {
  expect(show([]).querySelectorAll("a")).toHaveLength(1);
});

function counted(useCount?: number) {
  const host = document.createElement("div");
  render(
    () => (
      <ModelsProvider definitions={{ models: {}, enums: {} }}>
        <ResultButton href="/Source/1" type="Source" label="A book" useCount={useCount} />
      </ModelsProvider>
    ),
    host,
  );
  return host.querySelector<HTMLElement>("[data-testid=use-count]");
}

test("with a count of its uses it has a bubble, and none unless it is given", () => {
  expect(counted()).toBeNull();
  expect(counted(12)?.textContent).toBe("12");
  expect(counted(12)?.className).toContain("bg-sky-600");
});

test("a count of nothing is shown too, and quieter", () => {
  expect(counted(0)?.textContent).toBe("0");
  expect(counted(0)?.className).toContain("bg-slate-200");
});

const mark = (props: ResultMarkProps) => <i data-testid="mark">{`${props.type} ${String(props.item.id)}`}</i>;
const WITH_MARK: ModuleManifest[] = [{ name: "m", components: {}, resultMarks: { Flag: mark } }];

function showMarked(options: { item?: Record<string, unknown>; head?: { type: string; id: string }; disabled?: string[] }) {
  const host = document.createElement("div");
  render(
    () => (
      <ModelsProvider definitions={{ models: {}, enums: {}, disabled: options.disabled }}>
        <ModulesProvider modules={WITH_MARK}>
          <ResultButton href="/Activity/1" type="Activity" label="A coronation" head={options.head} item={options.item} />
        </ModulesProvider>
      </ModelsProvider>
    ),
    host,
  );
  return host;
}

test("what a module adds is inside the row's link, given the item", () => {
  const host = showMarked({ item: { id: "1" } });
  const found = host.querySelector("a [data-testid=mark]");
  expect(found?.textContent).toBe("Activity 1");
});

test("a row given no item has no marks, and a mark a project disables is not drawn", () => {
  expect(showMarked({}).querySelector("[data-testid=mark]")).toBeNull();
  expect(showMarked({ item: { id: "1" }, disabled: ["m:Flag"] }).querySelector("[data-testid=mark]")).toBeNull();
});

test("the button to the head is last in the row, after what a module adds", () => {
  const host = showMarked({ item: { id: "1" }, head: { type: "Factoid", id: "9" } });
  const links = [...host.querySelectorAll("a")];
  expect(links.map((a) => a.getAttribute("href"))).toEqual(["/Activity/1", "/Factoid/9"]);
  const marked = host.querySelector("[data-testid=mark]")!;
  expect(marked.compareDocumentPosition(links[1]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});
