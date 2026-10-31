// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { TranslationBundle } from "../types";
import { interpolate, TranslationsProvider, useTranslations } from "./translations";
import type { Translations } from "./translations";

const english: TranslationBundle = {
  language: "en",
  default: "en",
  languages: ["en", "de"],
  ui: { log_in: "Log in", greeting: "Hello {user}", only_english: "Only English" },
  models: {
    Person: {
      name: "Person",
      plural: "People",
      fields: { birth_place: { name: "Place of birth", plural: "", help: "" } },
      incoming: { carried_out: { name: "Carried out", plural: "", help: "" } },
    },
  },
  enums: { Colour: { name: "Colour", plural: "Colours", members: { RED: { name: "Red" } } } },
};
const german: TranslationBundle = {
  ...english,
  language: "de",
  ui: { log_in: "Anmelden", greeting: "Hallo {user}", only_english: "" },
  models: {
    Person: {
      name: "Person",
      plural: "Personen",
      fields: { birth_place: { name: "Geburtsort", plural: "", help: "" } },
      incoming: { carried_out: { name: "Ausgeführt", plural: "", help: "" } },
    },
  },
  enums: { Colour: { name: "Farbe", plural: "Farben", members: { RED: { name: "Rot" } } } },
};

let cleanup: (() => void) | undefined;
let tr: Translations;
beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup?.();
  document.documentElement.removeAttribute("data-translating");
});

function mount(load: (language?: string) => Promise<TranslationBundle>) {
  const container = document.createElement("div");
  document.body.append(container);
  const dispose = render(() => {
    return (
      <TranslationsProvider initial={english} load={load}>
        {(() => {
          tr = useTranslations();
          return <p>{tr.t("log_in", "Log in")}</p>;
        })()}
      </TranslationsProvider>
    );
  }, container);
  cleanup = () => {
    dispose();
    container.remove();
  };
  return container;
}

const settle = () => new Promise((resolve) => setTimeout(resolve));

test("interpolate replaces the parameters that are given and leaves the others", () => {
  expect(interpolate("Hi {a} and {b}", { a: "x" })).toBe("Hi x and {b}");
  expect(interpolate("plain")).toBe("plain");
});

test("the default language is there without loading anything", () => {
  const load = vi.fn();
  const container = mount(load);
  expect(container.textContent).toBe("Log in");
  expect(tr.modelName("Person", true)).toBe("People");
  expect(tr.fieldName("Person", "birth_place")).toBe("Place of birth");
  expect(load).not.toHaveBeenCalled();
});

test("another language is loaded when it is chosen, once, and the page keeps the old words meanwhile", async () => {
  let finish!: (bundle: TranslationBundle) => void;
  const load = vi.fn(() => new Promise<TranslationBundle>((resolve) => (finish = resolve)));
  mount(load);
  const choosing = tr.setLanguage("de");
  await settle();
  expect(load).toHaveBeenCalledWith("de");
  expect(tr.loading()).toBe(true);
  expect(document.documentElement.hasAttribute("data-translating")).toBe(true);
  expect(tr.t("log_in", "Log in")).toBe("Log in");
  finish(german);
  await choosing;
  expect(tr.loading()).toBe(false);
  expect(tr.language()).toBe("de");
  expect(tr.t("log_in", "Log in")).toBe("Anmelden");
  expect(tr.t("greeting", "Hello {user}", { user: "Ada" })).toBe("Hallo Ada");
  expect(tr.modelName("Person", true)).toBe("Personen");
  expect(tr.modelName("Person")).toBe("Person");
  expect(tr.fieldName("Person", "birth_place")).toBe("Geburtsort");
  expect(tr.incomingName("Person", "carried_out")).toBe("Ausgeführt");
  expect(tr.enumName("Colour", true)).toBe("Farben");
  expect(tr.memberName("Colour", "RED")).toBe("Rot");
  expect(document.documentElement.lang).toBe("de");
  expect(localStorage.getItem("pangloss.language")).toBe("de");
  // back to English, and to German again: nothing is fetched twice
  await tr.setLanguage("en");
  expect(tr.t("log_in", "Log in")).toBe("Log in");
  await tr.setLanguage("de");
  expect(load).toHaveBeenCalledTimes(1);
});

test("a text a language does not have is the default language's, then the English given", async () => {
  mount(async () => german);
  await tr.setLanguage("de");
  expect(tr.t("only_english", "x")).toBe("Only English");
  expect(tr.t("no_such_slot", "Given {n}", { n: 3 })).toBe("Given 3");
  expect(tr.modelName("Unknown")).toBe("Unknown");
  expect(tr.fieldName("Unknown", "some_field")).toBe("some field");
});

test("a language that fails to load leaves the page as it was", async () => {
  const error = vi.spyOn(console, "error").mockImplementation(() => {});
  mount(async () => {
    throw new Error("down");
  });
  await tr.setLanguage("de");
  expect(tr.language()).toBe("en");
  expect(tr.loading()).toBe(false);
  expect(localStorage.getItem("pangloss.language")).toBeNull();
  error.mockRestore();
});

test("a language that is not one of the languages is ignored", async () => {
  const load = vi.fn();
  mount(load);
  await tr.setLanguage("fr");
  expect(load).not.toHaveBeenCalled();
  expect(tr.language()).toBe("en");
});

test("the last choice is loaded when the page starts", async () => {
  localStorage.setItem("pangloss.language", "de");
  const load = vi.fn(async () => german);
  mount(load);
  await settle();
  await settle();
  expect(tr.language()).toBe("de");
});

test("when another language is chosen while one is loading, the last choice is shown", async () => {
  let finish!: (bundle: TranslationBundle) => void;
  mount(() => new Promise<TranslationBundle>((resolve) => (finish = resolve)));
  const first = tr.setLanguage("de");
  await settle();
  await tr.setLanguage("en");
  finish(german);
  await first;
  expect(tr.language()).toBe("en");
});
