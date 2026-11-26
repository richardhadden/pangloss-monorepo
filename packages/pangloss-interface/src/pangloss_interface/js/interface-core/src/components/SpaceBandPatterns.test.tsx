// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import type { JSX } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { ModelsProvider } from "../context";
import type { ModelDefinitions } from "../types";
import { SpaceBands } from "./SpaceBands";

const space = (name: string, said: Record<string, unknown>, interfaceMeta: object | null = null) => ({
  name,
  kind: "SemanticSpace",
  abstract: false,
  concreteTypes: [name],
  interfaceMeta,
  veridical: 0,
  fit: "describes",
  logical: null,
  unary: false,
  degree: null,
  fields: [],
  incoming: [],
  ...said,
});

const definitions = {
  models: {
    Not: space("Not", { veridical: -1, logical: { not: true }, unary: true }),
    // (a plain space, as every space of a project that sets no option)
    Reported: space("Reported", {}),
    Rumoured: space("Rumoured", {}, { colour: null, band: "bars" }),
  },
  enums: {},
} as unknown as ModelDefinitions;

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  globalThis.document.body.innerHTML = "";
});

const draw = (element: () => JSX.Element) => {
  const host = globalThis.document.createElement("div");
  globalThis.document.body.append(host);
  dispose = render(() => <ModelsProvider definitions={definitions}>{element()}</ModelsProvider>, host);
  return host;
};

const bands = (host: HTMLElement) =>
  [...host.querySelectorAll<HTMLElement>("[data-band]")].map((element) => element.dataset.band);

for (const stacked of [true, false]) {
  const how = stacked ? "stacked" : "as tabs";

  test(`a "not" band ${how} is hatched, and a plain one has no pattern`, () => {
    const host = draw(() => (
      <SpaceBands spaces={["Reported", "Not"]} depth={0} stacked={stacked}>
        <span>The mill burnt</span>
      </SpaceBands>
    ));
    expect(host.textContent).toContain("The mill burnt");
    expect(bands(host)).toEqual(["hatch"]);
    const hatched = host.querySelector<HTMLElement>("[data-band='hatch']")!;
    expect(hatched.className).toContain("bg-[image:repeating-linear-gradient(45deg");
    // (its tint as well, by its depth: the second band)
    expect(hatched.className).toContain("bg-violet-400/15");
    // (the plain one: its tint alone, as before there were patterns)
    const plain = hatched.parentElement!.closest<HTMLElement>("[class*='bg-amber-400/15']")!;
    expect(plain).not.toBeNull();
    expect(plain.hasAttribute("data-band")).toBe(false);
    expect(plain.className).not.toContain("bg-[image:");
  });

  test(`a class's own pattern ${how}`, () => {
    const host = draw(() => (
      <SpaceBands spaces={["Rumoured"]} depth={0} stacked={stacked}>
        <span>The well ran dry</span>
      </SpaceBands>
    ));
    expect(bands(host)).toEqual(["bars"]);
  });
}
