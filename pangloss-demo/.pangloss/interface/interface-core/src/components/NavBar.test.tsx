// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { ModelsProvider, NavExpandedProvider, useNavExpanded } from "../context";
import type { ModelDefinitions } from "../types";
import { isNavShortcut } from "./keys";
import { NavBar, readableName } from "./NavBar";

const definitions: ModelDefinitions = { models: {}, enums: {} };

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
  localStorage.clear();
});

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

const shortcut = () => {
  const mac = /Mac|iPhone|iPad/.test(navigator.platform);
  const event = new KeyboardEvent("keydown", { key: "k", metaKey: mac, ctrlKey: !mac, bubbles: true, cancelable: true });
  document.body.dispatchEvent(event);
  return event;
};

const person = () =>
  ({
    name: "Person",
    kind: "Entity",
    abstract: false,
    createDirectly: true,
    globalSearch: true,
    parent: null,
    concreteTypes: [],
    interfaceMeta: null,
    fields: [],
    incoming: [],
  }) as never;

async function bar(given: { definitions?: ModelDefinitions; user?: string; onNavigate?: (href: string) => void } = {}) {
  const outside = document.createElement("input");
  const host = document.createElement("div");
  document.body.append(outside, host);
  let pin: (pinned: boolean) => void = () => {};
  function Pin() {
    pin = useNavExpanded().setNavPinned;
    return null;
  }
  dispose = render(
    () => (
      <ModelsProvider definitions={given.definitions ?? definitions}>
        <NavExpandedProvider>
          <Pin />
          <NavBar user={given.user} onNavigate={given.onNavigate} />
        </NavExpandedProvider>
      </ModelsProvider>
    ),
    host,
  );
  await settle();
  return { outside, filter: () => host.querySelector<HTMLInputElement>('input[type="search"]'), pin: (on: boolean) => pin(on) };
}

const press = (over: Partial<KeyboardEventInit>) => new KeyboardEvent("keydown", { key: "k", ...over });

test("the shortcut is Cmd+K on a Mac and Ctrl+K elsewhere, and nothing else", () => {
  expect(isNavShortcut(press({ metaKey: true }), true)).toBe(true);
  expect(isNavShortcut(press({ ctrlKey: true }), false)).toBe(true);
  // (Ctrl+K deletes to the end of the line in a text box on a Mac)
  expect(isNavShortcut(press({ ctrlKey: true }), true)).toBe(false);
  expect(isNavShortcut(press({}), true)).toBe(false);
  expect(isNavShortcut(press({ metaKey: true, shiftKey: true }), true)).toBe(false);
  expect(isNavShortcut(press({ metaKey: true, altKey: true }), true)).toBe(false);
  expect(isNavShortcut(press({ metaKey: true, key: "j" }), true)).toBe(false);
});

test("the shortcut is shown at the foot of the retracted bar and hidden while it is open", async () => {
  const { pin } = await bar();
  const hint = document.querySelector("kbd")!;
  expect(hint.textContent).toBe(/Mac|iPhone|iPad/.test(navigator.platform) ? "⌘ + K" : "Ctrl + K");
  expect(hint.classList.contains("opacity-0")).toBe(false);
  pin(true);
  shortcut();
  await settle();
  expect(hint.classList.contains("opacity-0")).toBe(true);
});

test("the shortcut opens the bar with the cursor in the filter, and again closes it and gives the focus back", async () => {
  const { outside, filter } = await bar();
  outside.focus();
  expect(filter()).toBeNull();
  expect(shortcut().defaultPrevented).toBe(true);
  await settle();
  expect(document.activeElement).toBe(filter());
  shortcut();
  await settle();
  expect(filter()).toBeNull();
  expect(document.activeElement).toBe(outside);
});

test("Escape in an empty filter closes the bar; with something in it, it clears it first", async () => {
  const { outside, filter } = await bar();
  outside.focus();
  shortcut();
  await settle();
  const box = filter()!;
  box.value = "pers";
  box.dispatchEvent(new InputEvent("input", { bubbles: true }));
  await settle();
  const escape = () => box.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
  escape();
  await settle();
  expect(box.value).toBe("");
  expect(filter()).not.toBeNull();
  escape();
  await settle();
  expect(filter()).toBeNull();
  expect(document.activeElement).toBe(outside);
});

test("the bar closes when the focus leaves it, the mouse not being over it", async () => {
  const { outside, filter } = await bar();
  shortcut();
  await settle();
  expect(document.activeElement).toBe(filter());
  outside.focus();
  await settle();
  expect(filter()).toBeNull();
});

test("a pinned bar stays open: the shortcut only moves the cursor into the filter", async () => {
  const { outside, filter, pin } = await bar();
  pin(true);
  await settle();
  outside.focus();
  shortcut();
  await settle();
  expect(document.activeElement).toBe(filter());
  shortcut();
  await settle();
  expect(filter()).not.toBeNull();
  expect(document.activeElement).toBe(outside);
});

test("in the filter, the arrows choose and Cmd/Ctrl+Enter makes a new item; a plain Enter does not", async () => {
  const navigated: string[] = [];
  const { filter } = await bar({
    definitions: { models: { Person: person() }, enums: {} },
    user: "me",
    onNavigate: (href) => navigated.push(href),
  });
  shortcut();
  await settle();
  const box = filter()!;
  const key = (init: KeyboardEventInit) => {
    const event = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init });
    box.dispatchEvent(event);
    return event;
  };
  expect(document.querySelector("nav a[aria-current='true']")?.textContent?.trim()).toBe("Person");
  expect(key({ key: "ArrowDown" }).defaultPrevented).toBe(true);
  // (the wrong modifier is not the shortcut)
  key({ key: "Enter", shiftKey: true });
  expect(navigated).toEqual([]);
  const mac = /Mac|iPhone|iPad/.test(navigator.platform);
  key({ key: "Enter", metaKey: mac, ctrlKey: !mac });
  expect(navigated).toEqual(["/Person/new"]);
  await settle();
  expect(filter()).toBeNull();
});

test("what is left in the filter is selected when the shortcut comes back to it, so that typing replaces it", async () => {
  const { filter, outside } = await bar();
  outside.focus();
  shortcut();
  await settle();
  const box = filter()!;
  box.value = "pers";
  box.dispatchEvent(new InputEvent("input", { bubbles: true }));
  shortcut();
  await settle();
  shortcut();
  await settle();
  expect(filter()!.selectionStart).toBe(0);
  expect(filter()!.selectionEnd).toBe(4);
});

test("the shortcut does nothing while a dialog is open", async () => {
  const { filter } = await bar();
  const dialog = document.createElement("div");
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  document.body.append(dialog);
  expect(shortcut().defaultPrevented).toBe(false);
  await settle();
  expect(filter()).toBeNull();
});

test("going to a type empties the filter: Enter, Cmd/Ctrl+Enter, or a click on it", async () => {
  const { filter, pin } = await bar({
    definitions: { models: { Person: person() }, enums: {} },
    user: "me",
  });
  // (pinned, so that the box is still there to be looked at)
  pin(true);
  await settle();
  const box = filter()!;
  const mac = /Mac|iPhone|iPad/.test(navigator.platform);
  const typed = async () => {
    box.value = "per";
    box.dispatchEvent(new InputEvent("input", { bubbles: true }));
    await settle();
    expect(box.value).toBe("per");
  };
  const link = () => document.querySelector<HTMLAnchorElement>("nav a[href='/Person']")!;
  // (the page is not left, here)
  const stay = (event: Event) => event.preventDefault();
  document.addEventListener("click", stay);

  await typed();
  box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
  await settle();
  expect(box.value).toBe("");

  await typed();
  box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", metaKey: mac, ctrlKey: !mac, bubbles: true, cancelable: true }));
  await settle();
  expect(box.value).toBe("");

  await typed();
  link().click();
  await settle();
  expect(box.value).toBe("");
  document.removeEventListener("click", stay);
});

test("only typing and going to a type change the filter: the bar closing keeps it", async () => {
  const { filter, outside } = await bar({ definitions: { models: { Person: person() }, enums: {} } });
  shortcut();
  await settle();
  const box = filter()!;
  box.value = "per";
  box.dispatchEvent(new InputEvent("input", { bubbles: true }));
  await settle();
  outside.focus();
  await settle();
  shortcut();
  await settle();
  expect(filter()!.value).toBe("per");
});

test("the top of the bar links home under the name of the project", async () => {
  await bar({ definitions: { ...definitions, projectName: "Prosopography" } });
  shortcut();
  await settle();
  expect(document.querySelector('nav a[href="/"]')?.textContent).toBe("Prosopography");
});

test("the name of a project loses its hyphens, underscores and camel case", () => {
  expect(readableName("pangloss_demo")).toBe("pangloss demo");
  expect(readableName("my-big__project")).toBe("my big project");
  expect(readableName("myBigProject")).toBe("my Big Project");
  expect(readableName("Prosopography")).toBe("Prosopography");
});
