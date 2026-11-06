import { expect, test } from "vitest";
import type { ModelDefinition, ModelDefinitions } from "../types";
import { navSections } from "./nav";

const model = (name: string, extra: Partial<ModelDefinition>) =>
  ({ name, kind: "Entity", parent: null, abstract: false, concreteTypes: [name], ...extra }) as ModelDefinition;

const definitions = {
  models: {
    Thing: model("Thing", { abstract: true, concreteTypes: ["Widget"] }),
    Widget: model("Widget", { parent: "Thing" }),
    // (abstract, and nothing concrete below it: the API has no list for it)
    Idea: model("Idea", { abstract: true, concreteTypes: [] }),
  },
  enums: {},
} as unknown as ModelDefinitions;

test("an abstract type with no concrete type below it is not in the bar, one with some is", () => {
  const labels = navSections(definitions).flatMap((section) => section.entries.map((e) => e.label));
  expect(labels).toEqual(["Thing", "Widget"]);
});

test("a type is listed under the section of its meta, indented under a parent in the same section only", () => {
  const typed = {
    models: {
      Base: model("Base", { abstract: true, concreteTypes: ["Kind"], interfaceMeta: { navSection: "Typologies" } as never }),
      Kind: model("Kind", { parent: "Base", interfaceMeta: { navSection: "Typologies" } as never }),
      Plain: model("Plain", {}),
      Under: model("Under", { parent: "Plain", interfaceMeta: { navSection: "Typologies" } as never }),
    },
    enums: {},
  } as unknown as ModelDefinitions;
  const sections = navSections(typed);
  expect(sections.map((s) => s.title)).toEqual(["Entities", "Typologies"]);
  expect(sections[0]!.entries.map((e) => e.label)).toEqual(["Plain"]);
  expect(sections[1]!.entries.map((e) => [e.label, e.depth])).toEqual([
    ["Base", 0],
    ["Kind", 1],
    ["Under", 0],
  ]);
});

test("an app's NavModel wins over the section of the meta", () => {
  const typed = {
    models: { Kind: model("Kind", { interfaceMeta: { navSection: "Typologies" } as never }) },
    enums: {},
    nav: { sections: ["Entities", "Documents"], models: { Kind: { section: "Vocabularies", label: null, order: null, hidden: false } }, links: [] },
  } as unknown as ModelDefinitions;
  expect(navSections(typed).map((s) => s.title)).toEqual(["Vocabularies"]);
});
