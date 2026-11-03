// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { expect, test } from "vitest";
import { ModelsProvider, NavExpandedProvider, TranslationsProvider } from "../context";
import type { ModelDefinition, ModelDefinitions, TranslationBundle } from "../types";
import { NavModelList } from "./NavModelList";

const definitions: ModelDefinitions = {
  models: {},
  enums: {},
  nav: {
    sections: ["Entities", "Documents"],
    models: {},
    links: [
      { label: "Public", labelSlot: "a", href: "/public", section: "Tools", order: null, external: false, requiresLogin: false },
      { label: "Private", labelSlot: "b", href: "/private", section: "Tools", order: null, external: false, requiresLogin: true },
    ],
  },
};

function show(loggedIn: boolean) {
  const host = document.createElement("div");
  render(
    () => (
      <ModelsProvider definitions={definitions}>
        <NavExpandedProvider>
          <NavModelList loggedIn={loggedIn} />
        </NavExpandedProvider>
      </ModelsProvider>
    ),
    host,
  );
  return [...host.querySelectorAll("a")].map((a) => a.textContent?.trim());
}

test("a link that needs a login is shown only to someone logged in", () => {
  expect(show(false)).toEqual(["Public"]);
  expect(show(true)).toEqual(["Public", "Private"]);
});

const entity = (name: string, parent: string | null = null): ModelDefinition => ({
  name,
  kind: "Entity",
  abstract: false,
  description: null,
  parent,
  concreteTypes: [],
  typeParameters: [],
  createWithId: false,
  createDirectly: true,
  acceptUrlAsId: false,
  requireLabel: true,
  useInSemanticSpaceLabel: true,
  interfaceMeta: null,
  fields: [],
  incoming: [],
});

const typed: ModelDefinitions = {
  models: { Person: entity("Person"), Saint: entity("Saint", "Person"), Place: entity("Place") },
  enums: {},
};

// (English is shown; the German names come only in `modelNames`, as the browser has no German bundle)
const bundle: TranslationBundle = {
  language: "en",
  default: "en",
  languages: ["en", "de"],
  ui: {},
  models: {
    Person: { name: "Person", plural: "People" },
    Place: { name: "Place", plural: "Places" },
    Saint: { name: "Saint", plural: "Saints" },
  },
  enums: {},
  modelNames: {
    Person: ["Person", "People", "Personen"],
    Place: ["Place", "Places", "Ort", "Orte"],
    Saint: ["Saint", "Saints", "Heiliger", "Heilige"],
  },
};

function filtered(filter: string) {
  const host = document.createElement("div");
  render(
    () => (
      <ModelsProvider definitions={typed}>
        <TranslationsProvider initial={bundle} load={async () => bundle}>
          <NavExpandedProvider>
            <NavModelList filter={filter} />
          </NavExpandedProvider>
        </TranslationsProvider>
      </ModelsProvider>
    ),
    host,
  );
  return {
    names: [...host.querySelectorAll("a")].map((a) => a.textContent?.trim()),
    indents: [...host.querySelectorAll("a")].map((a) => (a as HTMLElement).style.paddingLeft),
    text: host.textContent,
  };
}

test("the filter matches part of any name of a type, in any language, without indents", () => {
  expect(filtered("").names).toEqual(["Person", "Saint", "Place"]);
  expect(filtered("lac").names).toEqual(["Place"]);
  // (German, which is not shown, and regardless of case and accents)
  expect(filtered("ORT").names).toEqual(["Place"]);
  expect(filtered("héil").names).toEqual(["Saint"]);
  expect(filtered("heil").indents).toEqual(["0.75rem"]);
  // (each word is to match)
  expect(filtered("pe ple").names).toEqual(["Person"]);
  expect(filtered("zzz").text).toContain("No types match");
});
