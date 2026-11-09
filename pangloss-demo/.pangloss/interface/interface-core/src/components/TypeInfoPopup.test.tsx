// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { createSignal } from "solid-js";
import { afterEach, expect, test } from "vitest";
import { ModelsProvider, NavExpandedProvider, SessionProvider, TranslationsProvider } from "../context";
import type { User } from "../api";
import type { FieldDefinition, ModelDefinition, ModelDefinitions, TranslationBundle } from "../types";
import { NavModelList } from "./NavModelList";
import { ReferenceChip } from "./ReferenceChip";
import { placeTypeInfo, TypeInfoPopup } from "./TypeInfoPopup";

const base = { description: null, dbField: false, readOnly: false, required: true, nullable: false };
const person = {
  name: "Person",
  kind: "Entity",
  abstract: false,
  createDirectly: true,
  parent: null,
  concreteTypes: ["Person"],
  description: "From the docstring.",
  interfaceMeta: null,
  incoming: [],
  fields: [
    { ...base, name: "born_in", key: "bornIn", kind: "relation", many: false, reverseName: "x", validators: [], subclasses: [], options: [{ kind: "entity", type: "Place", edgeModel: null }] },
    { ...base, name: "age", key: "age", kind: "literal", type: { type: "int" }, validators: [] },
  ] as FieldDefinition[],
} as unknown as ModelDefinition;
const place = { ...person, name: "Place", concreteTypes: ["Place"], description: null, fields: [] } as ModelDefinition;
const definitions: ModelDefinitions = { models: { Person: person, Place: place }, enums: {} };

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

function page(given: { user?: User; bundle?: TranslationBundle } = {}) {
  const host = document.createElement("div");
  document.body.append(host);
  const [user] = createSignal(given.user);
  const bundle = given.bundle ?? ({ language: "en", languages: ["en"], ui: {}, models: {}, enums: {} } as unknown as TranslationBundle);
  dispose = render(
    () => (
      <ModelsProvider definitions={definitions}>
        <TranslationsProvider initial={bundle} load={async () => bundle}>
          <SessionProvider user={user}>
            <span id="chip" data-type-info="Person">Person</span>
            <span id="plain">Nothing</span>
            <span id="unknown" data-type-info="Nobody">Nobody</span>
            <TypeInfoPopup />
          </SessionProvider>
        </TranslationsProvider>
      </ModelsProvider>
    ),
    host,
  );
  return host;
}

const over = (id: string, altKey = false) =>
  document.getElementById(id)!.dispatchEvent(new MouseEvent("mouseover", { bubbles: true, altKey }));
const key = (type: "keydown" | "keyup") => {
  const event = new KeyboardEvent(type, { key: "Alt", bubbles: true, cancelable: true });
  document.body.dispatchEvent(event);
  return event;
};
const popup = () => document.querySelector<HTMLElement>('[role="tooltip"]');

test("hovering a chip and pressing Alt shows the popup; letting go hides it", async () => {
  page();
  await settle();
  over("chip");
  await settle();
  expect(popup()).toBeNull();
  key("keydown");
  await settle();
  expect(popup()?.textContent).toContain("Person");
  key("keyup");
  await settle();
  expect(popup()).toBeNull();
});

test("Alt already held when the chip is reached shows it, and leaving the chip hides it", async () => {
  page();
  await settle();
  over("chip", true);
  await settle();
  expect(popup()).not.toBeNull();
  over("plain", true);
  await settle();
  expect(popup()).toBeNull();
});

test("the window losing the focus hides it, so Alt+Tab does not leave it stuck", async () => {
  page();
  await settle();
  over("chip", true);
  await settle();
  window.dispatchEvent(new Event("blur"));
  await settle();
  expect(popup()).toBeNull();
});

test("a scroll hides a popup that is showing, but not the chip the pointer is on before Alt is pressed", async () => {
  page();
  await settle();
  over("chip");
  await settle();
  document.dispatchEvent(new Event("scroll"));
  key("keydown");
  await settle();
  expect(popup()).not.toBeNull();
  document.dispatchEvent(new Event("scroll"));
  await settle();
  expect(popup()).toBeNull();
});

test("a chip of a type there is no definition of shows nothing", async () => {
  page();
  await settle();
  over("unknown", true);
  await settle();
  expect(popup()).toBeNull();
});

test("Alt is left alone when there is no popup, and held back from the browser when there is one", async () => {
  page();
  await settle();
  expect(key("keydown").defaultPrevented).toBe(false);
  over("chip", true);
  await settle();
  expect(key("keyup").defaultPrevented).toBe(true);
});

test("it shows the verbose name and the help text, in the language", async () => {
  page({
    bundle: {
      language: "en",
      languages: ["en"],
      ui: {},
      models: { Person: { name: "Human being", plural: "", description: "From the docstring.", help: "Someone who lived." } },
      enums: {},
    } as unknown as TranslationBundle,
  });
  await settle();
  over("chip", true);
  await settle();
  expect(popup()?.textContent).toContain("Human being");
  expect(popup()?.textContent).toContain("Someone who lived.");
  expect(popup()?.textContent).not.toContain("From the docstring.");
});

test("with no help text it shows the description", async () => {
  page();
  await settle();
  over("chip", true);
  await settle();
  expect(popup()?.textContent).toContain("From the docstring.");
});

test("the fields are shown only to someone logged in, with what each accepts", async () => {
  page();
  await settle();
  over("chip", true);
  await settle();
  expect(popup()?.textContent).not.toContain("born in");
  dispose?.();
  document.body.innerHTML = "";
  page({ user: { username: "ada" } as User });
  await settle();
  over("chip", true);
  await settle();
  const text = popup()?.textContent ?? "";
  expect(text).toContain("born in");
  expect(text).toContain("Place");
  expect(text).toContain("Whole number");
});

test("the popup is placed under its chip, kept on the screen, and beside a row of the navigation bar", () => {
  const anchor = { left: 100, right: 200, top: 100, bottom: 120 };
  const viewport = { width: 1000, height: 800 };
  const size = { width: 300, height: 200 };
  expect(placeTypeInfo(anchor, size, viewport, "below")).toEqual({ left: 100, top: 126 });
  expect(placeTypeInfo(anchor, size, viewport, "right")).toEqual({ left: 206, top: 100 });
  // (no room below: above it)
  expect(placeTypeInfo({ ...anchor, top: 700, bottom: 720 }, size, viewport, "below").top).toBe(494);
  // (no room to the right: pulled in from the edge)
  expect(placeTypeInfo({ ...anchor, left: 900, right: 990 }, size, viewport, "below").left).toBe(692);
});

test("a reference chip and a type in the navigation bar are chips the popup knows", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  dispose = render(
    () => (
      <ModelsProvider definitions={definitions}>
        <NavExpandedProvider>
          <ReferenceChip type="Person" label="Ada" />
          <NavModelList />
        </NavExpandedProvider>
      </ModelsProvider>
    ),
    host,
  );
  await settle();
  expect(host.querySelector('span[data-type-info="Person"]')?.textContent).toContain("Person");
  const row = host.querySelector('a[data-type-info="Person"]');
  expect(row).not.toBeNull();
  expect(row?.getAttribute("data-type-info-side")).toBe("right");
});
