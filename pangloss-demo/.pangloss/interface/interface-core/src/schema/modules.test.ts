import { expect, test } from "vitest";
import { defineModule, findLoader, navSections, orderModules, slotOf } from "./index";
import type { ModelDefinition, ModelDefinitions } from "../types";

const loader = () => Promise.resolve({ default: () => null });
const module = (name: string, requires: string[] = []) =>
  defineModule({ name, requires, components: { Page: loader } });

function model(name: string, kind: ModelDefinition["kind"], parent: string | null = null, meta = {}): ModelDefinition {
  return {
    name,
    kind,
    abstract: false,
    description: null,
    parent,
    concreteTypes: [],
    typeParameters: [],
    createWithId: false,
    acceptUrlAsId: false,
    requireLabel: true,
    useInSemanticSpaceLabel: true,
    interfaceMeta: {
      colour: null,
      listPage: null,
      itemPage: null,
      viewCard: null,
      editCard: null,
      ...meta,
    },
    fields: [],
    incoming: [],
  };
}

test("modules are ordered with those they require first, otherwise as given", () => {
  const ordered = orderModules([module("a", ["c"]), module("b"), module("c")]);
  expect(ordered.map((m) => m.name)).toEqual(["c", "a", "b"]);
});

test("a missing requirement and a circle are errors that name the modules", () => {
  expect(() => orderModules([module("a", ["zzz"])])).toThrow(/'a' requires 'zzz'/);
  expect(() => orderModules([module("a", ["b"]), module("b", ["a"])])).toThrow(/a -> b -> a/);
});

test("a loader is found by app and key, and only if it is there", () => {
  const modules = [module("ms")];
  expect(findLoader(modules, { module: "ms", name: "Page" })).toBe(loader);
  expect(findLoader(modules, { module: "ms", name: "Nope" })).toBeUndefined();
  expect(findLoader(modules, { module: "other", name: "Page" })).toBeUndefined();
  expect(findLoader(modules, { module: "ms", name: "toString" })).toBeUndefined();
});

const definitions: ModelDefinitions = {
  models: {
    Manuscript: model("Manuscript", "Document", null, { itemPage: { module: "ms", name: "Page" } }),
    Folio: model("Folio", "Entity"),
    Person: model("Person", "Entity"),
    Poet: model("Poet", "Entity", "Person"),
  },
  enums: {},
};

test("the component a model names for a slot", () => {
  expect(slotOf(definitions, "Manuscript", "itemPage")).toEqual({ module: "ms", name: "Page" });
  expect(slotOf(definitions, "Manuscript", "listPage")).toBeNull();
  expect(slotOf(definitions, "Nobody", "itemPage")).toBeNull();
});

test("without a config the bar is the Entities then the Documents, in the order of the hierarchy", () => {
  const sections = navSections(definitions);
  expect(sections.map((s) => s.title)).toEqual(["Entities", "Documents"]);
  expect(sections[0]!.entries.map((e) => [e.label, e.depth])).toEqual([
    ["Folio", 0],
    ["Person", 0],
    ["Poet", 1],
  ]);
});

test("a config moves, labels, orders and hides types, and adds links", () => {
  const sections = navSections({
    ...definitions,
    nav: {
      sections: ["Entities", "Documents", "Sources"],
      models: {
        Manuscript: { label: "Manuscripts", labelSlot: "x", section: "Sources", order: 2, hidden: false },
        Folio: { label: null, labelSlot: "x", section: null, order: null, hidden: true },
        Poet: { label: null, labelSlot: "x", section: "Sources", order: 1, hidden: false },
      },
      links: [
        { label: "Chart", labelSlot: "x", href: "/chart", section: "Sources", order: null, external: false, requiresLogin: false },
        { label: "Elsewhere", labelSlot: "x", href: "https://example.org", section: null, order: null, external: true, requiresLogin: false },
      ],
    },
  });
  expect(sections.map((s) => s.title)).toEqual(["Entities", "Sources", "Links"]);
  expect(sections[0]!.entries.map((e) => e.label)).toEqual(["Person"]); // (Folio hidden, Poet moved, Documents empty)
  expect(sections[1]!.entries.map((e) => [e.label, e.href, e.depth])).toEqual([
    ["Poet", "/Poet", 0],
    ["Manuscripts", "/Manuscript", 0],
    ["Chart", "/chart", 0],
  ]);
  expect(sections[2]!.entries[0]).toMatchObject({ label: "Elsewhere", external: true });
});

test("a link that needs a login is marked so", () => {
  const sections = navSections({
    ...definitions,
    nav: {
      sections: ["Entities", "Documents"],
      models: {},
      links: [{ label: "Mine", labelSlot: "x", href: "/mine", section: null, order: null, external: false, requiresLogin: true }],
    },
  });
  expect(sections.at(-1)!.entries[0]).toMatchObject({ href: "/mine", requiresLogin: true });
});
