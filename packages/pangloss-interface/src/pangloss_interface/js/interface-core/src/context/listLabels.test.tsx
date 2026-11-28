// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { expect, test, vi } from "vitest";
import type { ModelDefinition, ModelDefinitions, ModuleManifest } from "../types";
import { ModelsProvider } from "./models";
import { ModulesProvider, useModules } from "./modules";

// `listLabels`: what a module says of the items another lists, asked by the list's name and the page's model

const model = (name: string, extras?: Record<string, unknown>) => ({ name, extras }) as unknown as ModelDefinition;
const loader = () => Promise.resolve({ default: () => null });

const labelling = (name: string, lists: string[], applies: (model: ModelDefinition) => boolean): ModuleManifest => ({
  name,
  components: {},
  listLabels: { Labels: { lists, applies, component: loader } },
});

function asked(modules: ModuleManifest[], list: string, of: ModelDefinition | undefined, disabled: string[] = []) {
  let found: { name: string; component: unknown }[] = [];
  let again: { name: string; component: unknown }[] = [];
  const definitions = { models: {}, enums: {}, disabled } as unknown as ModelDefinitions;
  function Probe() {
    const { listLabels } = useModules();
    found = listLabels(list, of);
    again = listLabels(list, of);
    return null;
  }
  render(
    () => (
      <ModelsProvider definitions={definitions}>
        <ModulesProvider modules={modules}>
          <Probe />
        </ModulesProvider>
      </ModelsProvider>
    ),
    document.createElement("div"),
  );
  return { found, again };
}

const compared = (each: ModelDefinition) => each.extras?.compared === true;

test("a list no module labels has no labellers, and without modules there are none", () => {
  expect(asked([], "similar", model("Baptism")).found).toEqual([]);
  expect(asked([{ name: "plain", components: {} }], "similar", model("Baptism")).found).toEqual([]);
});

test("a labeller is given for the lists it names and the models it applies to only", () => {
  const modules = [labelling("compare", ["similar"], compared)];
  expect(asked(modules, "similar", model("Baptism", { compared: true })).found).toHaveLength(1);
  expect(asked(modules, "similar", model("Person")).found).toEqual([]);
  expect(asked(modules, "another", model("Baptism", { compared: true })).found).toEqual([]);
  expect(asked(modules, "similar", undefined).found).toEqual([]);
});

test("the same component each time, in the order of the modules, and one a project disables is not given", () => {
  const modules = [labelling("first", ["similar"], () => true), labelling("second", ["similar"], () => true)];
  const { found, again } = asked(modules, "similar", model("Baptism"));
  expect(found.map((each) => each.name)).toEqual(["first:Labels", "second:Labels"]);
  expect(again[0]!.component).toBe(found[0]!.component);
  expect(again[1]!.component).toBe(found[1]!.component);
  expect(asked(modules, "similar", model("Baptism"), ["first:Labels"]).found.map((each) => each.name)).toEqual([
    "second:Labels",
  ]);
});

test("a labeller whose applies throws, or that lacks a part, does not apply, said once; the others still do", () => {
  const said = vi.spyOn(console, "error").mockImplementation(() => {});
  try {
    const throwing = labelling("throwing", ["similar"], () => {
      throw new Error("no");
    });
    const lacking = { name: "lacking", components: {}, listLabels: { Labels: { lists: ["similar"] } } } as unknown as ModuleManifest;
    const fine = labelling("fine", ["similar"], () => true);
    const { found, again } = asked([throwing, lacking, fine], "similar", model("Baptism"));
    expect(found.map((each) => each.name)).toEqual(["fine:Labels"]);
    expect(again.map((each) => each.name)).toEqual(["fine:Labels"]);
    // (each said once, though asked twice)
    expect(said).toHaveBeenCalledTimes(2);
    expect(String(said.mock.calls[0]![0])).toContain("throwing:Labels");
    expect(String(said.mock.calls[1]![0])).toContain("lacking:Labels");
  } finally {
    said.mockRestore();
  }
});
