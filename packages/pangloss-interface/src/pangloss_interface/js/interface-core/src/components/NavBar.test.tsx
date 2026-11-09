// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { ModelsProvider, NavExpandedProvider, useNavExpanded } from "../context";
import type { ModelDefinitions } from "../types";
import { isNavShortcut } from "./keys";
import { NavBar } from "./NavBar";

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

async function bar() {
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
      <ModelsProvider definitions={definitions}>
        <NavExpandedProvider>
          <Pin />
          <NavBar />
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
