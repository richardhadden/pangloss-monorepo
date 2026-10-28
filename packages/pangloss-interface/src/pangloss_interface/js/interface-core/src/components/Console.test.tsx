// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { createSignal } from "solid-js";
import { afterEach, expect, test } from "vitest";
import type { User } from "../api";
import { ConsoleMountProvider, ModelsProvider, SessionProvider } from "../context";
import type { ModelDefinition, ModelDefinitions } from "../types";
import { Console } from "./Console";
import { ConsoleBar } from "./ConsoleBar";

const model = (name: string, kind: ModelDefinition["kind"], abstract = false): ModelDefinition => ({
  name,
  kind,
  abstract,
  description: null,
  parent: null,
  concreteTypes: [],
  typeParameters: [],
  createWithId: false,
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
  },
  enums: {},
};

const demo = { username: "demo", email: "d@example.org", fullName: null, admin: false } as User;
const settle = () => new Promise((resolve) => setTimeout(resolve));

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

function show(user: () => User | undefined, props: { type: string; list?: boolean; label?: string; spaces?: string[] }) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <SessionProvider user={user}>
        <ModelsProvider definitions={definitions}>
          <ConsoleMountProvider>
            <ConsoleBar />
            <Console {...props} />
          </ConsoleMountProvider>
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

test("and none for no one", async () => {
  show(() => undefined, { type: "Place", list: true });
  await settle();
  expect(document.body.querySelector('header[aria-label="Console"]')?.textContent).toContain("Places");
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

test("an item in semantic spaces has a cell for each, outermost first, before its type", async () => {
  show(() => demo, { type: "Place", label: "Rome", spaces: ["Negative", "Hypothetical"] });
  await settle();
  const text = document.body.textContent ?? "";
  expect(text.indexOf("Negative")).toBeLessThan(text.indexOf("Hypothetical"));
  expect(text.indexOf("Hypothetical")).toBeLessThan(text.indexOf("Place"));
});
