// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { createSignal } from "solid-js";
import { afterEach, expect, test, vi } from "vitest";
import type { User } from "../api";
import {
  ConsoleMountProvider,
  ModelsProvider,
  ModulesProvider,
  NavExpandedProvider,
  SessionProvider,
} from "../context";
import type { ModelDefinition, ModelDefinitions, ModuleManifest } from "../types";
import { Console } from "./Console";
import { ConsoleBar } from "./ConsoleBar";

const model = (
  name: string,
  kind: ModelDefinition["kind"],
  abstract = false,
): ModelDefinition => ({
  name,
  kind,
  abstract,
  description: null,
  parent: null,
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

const definitions: ModelDefinitions = {
  models: {
    Place: model("Place", "Entity"),
    Agent: model("Agent", "Entity", true),
    Statement: { ...model("Statement", "Document"), createDirectly: false },
  },
  enums: {},
};

const demo = {
  username: "demo",
  email: "d@example.org",
  fullName: null,
  admin: false,
} as User;
const settle = () => new Promise((resolve) => setTimeout(resolve));

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

function show(
  user: () => User | undefined,
  props: {
    type: string;
    list?: boolean;
    label?: string;
    spaces?: string[];
    meta?: {
      createdBy?: string | null;
      createdWhen?: string | null;
      updatedBy?: string | null;
      updatedWhen?: string | null;
    };
    count?: number;
    truncated?: boolean;
    editHref?: string;
    onNew?: () => void;
    page?: "item" | "edit";
    formMode?: "new" | "edit";
  },
  modules: readonly ModuleManifest[] = [],
) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <SessionProvider user={user}>
        <ModelsProvider definitions={definitions}>
          <NavExpandedProvider>
            <ConsoleMountProvider>
              <ModulesProvider modules={modules}>
                <ConsoleBar />
                <Console {...props} />
              </ModulesProvider>
            </ConsoleMountProvider>
          </NavExpandedProvider>
        </ModelsProvider>
      </SessionProvider>
    ),
    container,
  );
  return container;
}

const newLink = () => document.body.querySelector('a[aria-label^="New "]');

test("a list has a new button for someone logged in", async () => {
  show(() => demo, { type: "Place", list: true });
  await settle();
  expect(newLink()?.getAttribute("href")).toBe("/Place/new");
});

test("a list that makes its new items itself (onNew) has a button that calls it, not a link", async () => {
  const onNew = vi.fn();
  show(() => demo, { type: "Place", list: true, onNew });
  await settle();
  expect(newLink()).toBeNull();
  const button = document.body.querySelector<HTMLButtonElement>('button[aria-label^="New "]')!;
  button.click();
  expect(onNew).toHaveBeenCalledOnce();
});

test("and none for no one", async () => {
  show(() => undefined, { type: "Place", list: true });
  await settle();
  expect(
    document.body.querySelector('header[aria-label="Console"]')?.textContent,
  ).toContain("Places");
  expect(newLink()).toBeNull();
});

test("the button comes and goes as the user logs in and out", async () => {
  const [user, setUser] = createSignal<User | undefined>(undefined);
  show(user, { type: "Place", list: true });
  await settle();
  expect(newLink()).toBeNull();
  setUser(demo);
  await settle();
  expect(newLink()).not.toBeNull();
  setUser(undefined);
  await settle();
  expect(newLink()).toBeNull();
});

test("an abstract type, or an item, has none even for someone logged in", async () => {
  show(() => demo, { type: "Agent", list: true });
  await settle();
  expect(newLink()).toBeNull();
  dispose?.();
  document.body.innerHTML = "";
  show(() => demo, { type: "Place" });
  await settle();
  expect(newLink()).toBeNull();
});

test("a document that cannot be made on its own (create_directly) has none either", async () => {
  show(() => demo, { type: "Statement", list: true });
  await settle();
  expect(
    document.body.querySelector('header[aria-label="Console"]')?.textContent,
  ).toContain("Statements");
  expect(newLink()).toBeNull();
});

test("an item in semantic spaces has a cell for each, outermost first, before its type", async () => {
  show(() => demo, {
    type: "Place",
    label: "Rome",
    spaces: ["Negative", "Hypothetical"],
  });
  await settle();
  const text = document.body.textContent ?? "";
  expect(text.indexOf("Negative")).toBeLessThan(text.indexOf("Hypothetical"));
  expect(text.indexOf("Hypothetical")).toBeLessThan(text.indexOf("Place"));
});

test("a count that is not all there is has a plus, and says so", async () => {
  show(() => demo, { type: "Place", list: true, count: 100, truncated: true });
  await settle();
  const found = document.body.querySelector('[title^="Found"]');
  expect(found?.textContent).toBe("100+");
  expect(found?.getAttribute("title")).toContain("narrow");
  dispose?.();
  document.body.innerHTML = "";
  show(() => demo, { type: "Place", list: true, count: 100 });
  await settle();
  expect(document.body.querySelector('[title="Found"]')?.textContent).toBe(
    "100",
  );
});

const metaRows = () =>
  [...document.body.querySelectorAll('[data-testid="console-meta"] > span')].map(
    (row) => row.textContent,
  );
const metaIcons = () =>
  [...document.body.querySelectorAll('[data-testid="console-meta"] > span')].map(
    (row) => [row.querySelector("svg") !== null, row.getAttribute("title")],
  );

test("an item says who made it and who changed it last, in two rows", async () => {
  show(() => demo, {
    type: "Place",
    label: "Rome",
    meta: {
      createdBy: "alice",
      createdWhen: "2026-01-02T10:00:00Z",
      updatedBy: "bob",
      updatedWhen: "2026-03-04T11:30:00Z",
    },
  });
  await settle();
  const rows = metaRows();
  expect(rows.length).toBe(2);
  // (what happened is an icon; the words are for a screen reader, and the tooltip)
  expect(rows[0]).toMatch(/^Created alice · .*2026/);
  expect(rows[1]).toMatch(/^Modified bob · .*2026/);
  expect(metaIcons()).toEqual([
    [true, "Created"],
    [true, "Modified"],
  ]);
  const words = document.body.querySelectorAll('[data-testid="console-meta"] .sr-only');
  expect([...words].map((word) => word.textContent?.trim())).toEqual(["Created", "Modified"]);
});

const metaLinks = () =>
  [...document.body.querySelectorAll('[data-testid="console-meta"] a')].map((link) => [
    link.textContent,
    link.getAttribute("href"),
  ]);
const withUserPages: ModuleManifest[] = [
  { name: "users", components: {}, userHref: (username) => `/users/${username}` },
];
const nameDemo = { type: "Place", label: "Rome", meta: { createdBy: "alice", createdWhen: "2026-01-02T10:00:00Z" } };

test("a name is a link to the user's page for someone logged in, if a module has such a page", async () => {
  show(() => demo, nameDemo, withUserPages);
  await settle();
  expect(metaLinks()).toEqual([["alice", "/users/alice"]]);
  expect(metaRows()[0]).toMatch(/^Created alice · /);
});

test("a name is not a link for someone not logged in, or with no such page", async () => {
  show(() => undefined, nameDemo, withUserPages);
  await settle();
  expect(metaRows()[0]).toMatch(/^Created alice · /);
  expect(metaLinks()).toEqual([]);
  dispose?.();
  document.body.innerHTML = "";
  show(() => demo, nameDemo);
  await settle();
  expect(metaLinks()).toEqual([]);
});

test("a row of the item's history is left out when it is not known; a list has none", async () => {
  show(() => demo, {
    type: "Place",
    label: "Rome",
    meta: {
      createdBy: null,
      createdWhen: "2026-01-02T10:00:00Z",
      updatedBy: null,
      updatedWhen: null,
    },
  });
  await settle();
  expect(metaRows().length).toBe(1);
  expect(metaRows()[0]).toMatch(/^Created · /);
  dispose?.();
  document.body.innerHTML = "";
  show(() => demo, { type: "Place", list: true });
  await settle();
  expect(metaRows()).toEqual([]);
});

const editLink = () => document.body.querySelector('a[aria-label="Edit"]');

test("an item has an edit button, on the far right, for someone logged in", async () => {
  show(() => demo, { type: "Place", label: "Rome", editHref: "/Place/p1/edit" });
  await settle();
  expect(editLink()?.getAttribute("href")).toBe("/Place/p1/edit");
  // (after the actions the page gave, and the history: the buttons are the last things on the right)
  const buttons = [...document.body.querySelectorAll("header a, header button")];
  expect(buttons[buttons.length - 1]).toBe(editLink());
});

test("and none for no one, or for a page that offers no edit", async () => {
  show(() => undefined, { type: "Place", label: "Rome", editHref: "/Place/p1/edit" });
  await settle();
  expect(editLink()).toBeNull();
  dispose?.();
  document.body.innerHTML = "";
  show(() => demo, { type: "Place", label: "Rome" });
  await settle();
  expect(editLink()).toBeNull();
});

test("Cmd/Ctrl+Enter does what the New button of a list does", async () => {
  const onNew = vi.fn();
  show(() => demo, { type: "Place", list: true, onNew });
  await settle();
  const mac = /Mac|iPhone|iPad/.test(navigator.platform);
  document.body.dispatchEvent(
    new KeyboardEvent("keydown", { key: "Enter", metaKey: mac, ctrlKey: !mac, bubbles: true, cancelable: true }),
  );
  expect(onNew).toHaveBeenCalledOnce();
});

test("Cmd/Ctrl+E follows the edit button, and is left to the browser where there is none", async () => {
  const press = () => {
    const mac = /Mac|iPhone|iPad/.test(navigator.platform);
    const event = new KeyboardEvent("keydown", { key: "e", metaKey: mac, ctrlKey: !mac, bubbles: true, cancelable: true });
    document.body.dispatchEvent(event);
    return event;
  };
  show(() => undefined, { type: "Place", label: "Rome", editHref: "/Place/p1/edit" });
  await settle();
  expect(press().defaultPrevented).toBe(false);
  dispose?.();
  document.body.innerHTML = "";
  show(() => demo, { type: "Place", label: "Rome", editHref: "/Place/p1/edit" });
  await settle();
  const click = vi.fn();
  editLink()!.addEventListener("click", (event) => {
    event.preventDefault();
    click();
  });
  expect(press().defaultPrevented).toBe(true);
  expect(click).toHaveBeenCalledOnce();
});

test("a form says in the console whether the item is new or being edited", async () => {
  show(() => demo, { type: "Place", formMode: "new" });
  await settle();
  expect(document.body.textContent).toContain("New");
  dispose?.();
  document.body.innerHTML = "";
  show(() => demo, { type: "Place", label: "Rome", formMode: "edit" });
  await settle();
  expect(document.body.textContent).toContain("Edit");
});
