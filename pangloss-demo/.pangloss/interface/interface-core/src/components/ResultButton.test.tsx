// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { expect, test } from "vitest";
import { ModelsProvider } from "../context";
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
  expect(host.querySelector(".bg-teal-400\\/25")?.textContent).toContain("Negative");
});

test("an item inside a document has a button to it, at the far left, not in the bands", () => {
  const host = show(["Negative"], { type: "Factoid", id: "f1" });
  const first = host.querySelector("a")!;
  expect(first.getAttribute("href")).toBe("/Factoid/f1");
  expect(host.querySelectorAll("a")).toHaveLength(2);
  // (before the bands: the name of the band comes after it)
  expect(host.textContent).toContain("Negative");
  expect(first.nextElementSibling?.textContent).toContain("Negative");
  expect(first.textContent).not.toContain("Negative");
});

test("an item that is a head node has no such button", () => {
  expect(show([]).querySelectorAll("a")).toHaveLength(1);
});
