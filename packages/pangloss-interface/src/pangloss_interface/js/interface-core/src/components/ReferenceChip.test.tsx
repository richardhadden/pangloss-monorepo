// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { ModelsProvider } from "../context";
import type { ModelDefinitions } from "../types";
import { DefaultReferenceChip } from "./ReferenceChip";

const base = { description: null, dbField: false, required: false, nullable: false, validators: [] };
const model = (name: string, kind: string, fields: object[] = []) => ({ name, kind, fields, concreteTypes: [name] });
const definitions = {
  models: {
    Person: model("Person", "Entity"),
    // (one written with its unit, `Slider(unit="%")`; one by its name)
    Likelihood: model("Likelihood", "EdgeModel", [
      { ...base, name: "percent", key: "percent", kind: "literal", type: { type: "int" }, markers: [{ name: "Slider", unit: "%" }] },
    ]),
    Certainty: model("Certainty", "EdgeModel", [
      { ...base, name: "level", key: "level", kind: "literal", type: { type: "int" }, markers: [] },
    ]),
  },
  enums: {},
} as unknown as ModelDefinitions;

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

const chip = (edgeModel: string | undefined, edgeProperties: Record<string, unknown>) => {
  const host = document.createElement("div");
  document.body.append(host);
  dispose = render(
    () => (
      <ModelsProvider definitions={definitions}>
        <DefaultReferenceChip type="Person" label="Charlemagne" href="/Person/p1" edgeModel={edgeModel} edgeProperties={edgeProperties} />
      </ModelsProvider>
    ),
    host,
  );
  return host;
};

const parts = (host: HTMLElement) => [...host.querySelectorAll("[data-edge-property]")];

test("the properties of the edge are the end of the chip, inside its frame: a value with a unit is the value and the unit", () => {
  const host = chip("Likelihood", { percent: 19 });
  expect(parts(host).map((part) => part.textContent)).toEqual(["19%"]);
  // (inside the frame, after the link, not a pill beside it)
  const link = host.querySelector("a")!;
  expect(link.parentElement).toBe(parts(host)[0]!.parentElement);
});

test("a value without a unit is said with the name of its field; one not given is left out", () => {
  expect(parts(chip("Certainty", { level: 3 })).map((part) => part.textContent)).toEqual(["level 3"]);
  dispose?.();
  expect(parts(chip("Certainty", { level: null }))).toHaveLength(0);
  dispose?.();
  // (no edge model known: the key and the value)
  expect(parts(chip(undefined, { level: 3 })).map((part) => part.textContent)).toEqual(["level 3"]);
});
