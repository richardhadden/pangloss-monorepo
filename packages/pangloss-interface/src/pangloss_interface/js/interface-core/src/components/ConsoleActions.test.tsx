// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import {
  ConsoleMountProvider,
  ModelsProvider,
  ModulesProvider,
  NavExpandedProvider,
  SessionProvider,
} from "../context";
import type {
  ConsoleActionProps,
  ConsoleProps,
  ModelDefinition,
  ModelDefinitions,
  ModuleManifest,
} from "../types";
import { Console } from "./Console";
import { ConsoleBar } from "./ConsoleBar";

const model = (name: string): ModelDefinition => ({
  name,
  kind: "Document",
  abstract: false,
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

const definitions: ModelDefinitions = { models: { Letter: model("Letter") }, enums: {} };

// (a module whose action shows what it was given; and one whose action fails)
const seen: ConsoleActionProps[] = [];
function Shows(props: ConsoleActionProps) {
  seen.push({ ...props });
  return (
    <button type="button" data-testid="module-action">
      {props.type} {props.id} {props.page} {props.model.name}
    </button>
  );
}
function Fails(): never {
  throw new Error("broken");
}
const modules: ModuleManifest[] = [
  { name: "first", components: {}, consoleActions: { Shows: async () => ({ default: Shows }) } },
  { name: "second", components: {}, consoleActions: { Fails: async () => ({ default: Fails }) } },
];

const settle = () => new Promise((resolve) => setTimeout(resolve, 10));

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
  seen.length = 0;
});

function show(props: ConsoleProps) {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <SessionProvider user={() => undefined}>
        <ModelsProvider definitions={definitions}>
          <ModulesProvider modules={modules}>
            <NavExpandedProvider>
              <ConsoleMountProvider>
                <ConsoleBar />
                <Console {...props}>
                  <button type="button" data-testid="page-button">
                    Save
                  </button>
                </Console>
              </ConsoleMountProvider>
            </NavExpandedProvider>
          </ModulesProvider>
        </ModelsProvider>
      </SessionProvider>
    ),
    container,
  );
}

test("the console of an item shows the modules' actions, given the item, before the page's own buttons", async () => {
  show({ type: "Letter", item: { type: "Letter", id: "abc" }, page: "edit" });
  await settle();
  const action = document.querySelector('[data-testid="module-action"]');
  expect(action?.textContent).toBe("Letter abc edit Letter");
  expect(seen.at(-1)).toMatchObject({ type: "Letter", id: "abc", page: "edit" });
  // (before the page's buttons; and the one that failed shows nothing, without taking the console down)
  const buttons = [...document.querySelectorAll("header button")].map((b) => b.getAttribute("data-testid"));
  expect(buttons.filter(Boolean)).toEqual(["module-action", "page-button"]);
});

test("the page is the item page unless said", async () => {
  show({ type: "Letter", item: { type: "Letter", id: "abc" } });
  await settle();
  expect(seen.at(-1)?.page).toBe("item");
});

test("a console without an item (a list, a new item) has none", async () => {
  show({ type: "Letter", list: true });
  await settle();
  expect(document.querySelector('[data-testid="module-action"]')).toBeNull();
  expect(document.querySelector('[data-testid="page-button"]')).not.toBeNull();
});
