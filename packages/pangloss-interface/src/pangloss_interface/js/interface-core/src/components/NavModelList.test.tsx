// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { createSignal, flush } from "solid-js";
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

test("a label an app gave is translated by its slot, and found by its translation", () => {
  const german: TranslationBundle = {
    ...bundle,
    language: "de",
    ui: { a: "Öffentlich" },
    models: {},
    modelNames: {},
  };
  const list = (filter?: string) => {
    const host = document.createElement("div");
    render(
      () => (
        <ModelsProvider definitions={definitions}>
          <TranslationsProvider initial={german} load={async () => german}>
            <NavExpandedProvider>
              <NavModelList loggedIn filter={filter} />
            </NavExpandedProvider>
          </TranslationsProvider>
        </ModelsProvider>
      ),
      host,
    );
    return [...host.querySelectorAll("a")].map((a) => a.textContent?.trim());
  };
  // (a label with no translation is the label as written)
  expect(list()).toEqual(["Öffentlich", "Private"]);
  expect(list("öffentl")).toEqual(["Öffentlich"]);
});

const allowed: ModelDefinitions = {
  models: {
    Person: entity("Person"),
    Part: { ...entity("Part"), createDirectly: false },
    Thing: { ...entity("Thing"), abstract: true, concreteTypes: ["Place"] },
    Place: entity("Place", "Thing"),
  },
  enums: {},
  nav: {
    sections: ["Entities"],
    models: {},
    links: [{ label: "Elsewhere", labelSlot: "c", href: "/elsewhere", section: "Tools", order: null, external: false, requiresLogin: false }],
  },
};

function chooser(loggedIn = true) {
  const host = document.createElement("div");
  document.body.append(host);
  const opened: (string | null)[] = [];
  const made: string[] = [];
  host.addEventListener("click", (event) => {
    event.preventDefault();
    opened.push((event.target as HTMLElement).closest("a")!.getAttribute("href"));
  });
  const [filter, setFilter] = createSignal("");
  const [selecting, setSelecting] = createSignal(true);
  let key: (key: "next" | "previous" | "open" | "new") => void = () => {};
  render(
    () => (
      <ModelsProvider definitions={allowed}>
        <NavExpandedProvider>
          <NavModelList
            loggedIn={loggedIn}
            filter={filter()}
            selecting={selecting()}
            keys={(given) => (key = given)}
            onNew={(type) => made.push(type)}
          />
        </NavExpandedProvider>
      </ModelsProvider>
    ),
    host,
  );
  const press = (name: "next" | "previous" | "open" | "new") => {
    key(name);
    flush();
  };
  const current = () => host.querySelector("a[aria-current='true']")?.textContent?.trim();
  return { opened, made, press, current, setFilter, setSelecting, names: () => [...host.querySelectorAll("a")].map((a) => a.textContent?.trim()) };
}

// (the order of the list, whatever it is: what matters is moving along it)
function goTo(list: ReturnType<typeof chooser>, name: string) {
  for (const _ of list.names()) {
    if (list.current() === name) return;
    list.press("next");
  }
  expect(list.current()).toBe(name);
}

test("the first is selected, and the keys move along the list and stop at its ends", () => {
  const list = chooser();
  const names = list.names();
  expect(list.current()).toBe(names[0]);
  list.press("previous");
  expect(list.current()).toBe(names[0]);
  list.press("next");
  expect(list.current()).toBe(names[1]);
  for (const _ of names) list.press("next");
  expect(list.current()).toBe(names[names.length - 1]);
});

test("nothing is shown as selected unless it is asked for", () => {
  const list = chooser();
  list.setSelecting(false);
  flush();
  expect(list.current()).toBeUndefined();
});

test("a change of the filter selects the first of what is left", () => {
  const list = chooser();
  list.press("next");
  list.press("next");
  list.setFilter("pla");
  flush();
  expect(list.current()).toBe("Place");
  list.press("open");
  expect(list.opened).toEqual(["/Place"]);
});

test("a new item is asked for only of a type that can be made", () => {
  const list = chooser();
  goTo(list, "Person");
  list.press("new");
  expect(list.made).toEqual(["Person"]);
  // (create_directly=False; abstract; a link that is no type)
  for (const name of ["Part", "Thing", "Elsewhere"]) {
    const again = chooser();
    goTo(again, name);
    again.press("new");
    expect(again.made).toEqual([]);
  }
});

test("and only for someone logged in", () => {
  const list = chooser(false);
  goTo(list, "Person");
  list.press("new");
  expect(list.made).toEqual([]);
});
