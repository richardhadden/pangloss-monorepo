// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { ComponentsProvider, ModelsProvider, ReferenceChip } from "@pangloss/interface-core";
import type { ComponentMap, ModelDefinitions } from "@pangloss/interface-core";
import WeightedAlternativeCard from "./WeightedAlternativeCard";

const base = { description: null, dbField: false, readOnly: false, required: false, nullable: false };
const model = (name: string, kind: string, fields: object[] = []) => ({
  name, kind, parent: null, abstract: false, concreteTypes: [name], description: null, typeParameters: [],
  createWithId: false, createDirectly: true, acceptUrlAsId: false, requireLabel: false, useInSemanticSpaceLabel: true,
  interfaceMeta: null, fields, incoming: [],
});
const definitions = {
  models: {
    WeightedAlternative: model("WeightedAlternative", "Conjunction", [
      { ...base, name: "alternatives", key: "alternatives", kind: "relation", many: true, reverseName: "r", subclasses: [],
        options: [{ kind: "typeVar", name: "T", edgeModel: "Likelihood" }], validators: [] },
    ]),
    Likelihood: model("Likelihood", "EdgeModel", [
      { ...base, name: "percent", key: "percent", kind: "literal", type: { type: "int" }, validators: [],
        markers: [{ name: "Slider", unit: "%" }] },
    ]),
    Person: model("Person", "Entity"),
  },
  enums: {},
} as unknown as ModelDefinitions;

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

const person = (id: string, label: string, percent: number) => ({ type: "Person", id, label, edgeProperties: { percent } });
const show = (alternatives: unknown[]) => {
  const host = document.createElement("div");
  document.body.append(host);
  const item = { type: "WeightedAlternative", id: "w1", alternatives };
  dispose = render(
    () => (
      <ComponentsProvider components={{ ReferenceChip } as ComponentMap}>
        <ModelsProvider definitions={definitions}>
          <WeightedAlternativeCard type="WeightedAlternative" label="" item={item} context="embedded" />
        </ModelsProvider>
      </ComponentsProvider>
    ),
    host,
  );
  return host;
};

test("several alternatives: under the name of the field, each with its likelihood at the end of its chip, and no head", () => {
  const host = show([person("p1", "Charlemagne", 19), person("p2", "Pope Leo III", 81)]);
  expect(host.querySelector("dt")?.textContent).toBe("alternatives");
  expect([...host.querySelectorAll("[data-edge-property]")].map((part) => part.textContent)).toEqual(["19%", "81%"]);
  expect(host.textContent).not.toContain("WeightedAlternative");
  expect(host.textContent).not.toContain("percent");
});

test("one alternative alone is only itself, without the name of the field", () => {
  const host = show([person("p1", "Charlemagne", 100)]);
  expect(host.querySelector("dt")).toBeNull();
  expect(host.querySelector("[data-edge-property]")?.textContent).toBe("100%");
});
