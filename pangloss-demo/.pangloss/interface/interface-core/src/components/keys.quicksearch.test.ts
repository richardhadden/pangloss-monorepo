// @vitest-environment happy-dom
import { afterEach, expect, test } from "vitest";
import { isQuickSearchShortcut } from "./keys";

function press(on: Element, init: KeyboardEventInit = {}) {
  const event = new KeyboardEvent("keydown", { key: "/", bubbles: true, ...init });
  on.dispatchEvent(event);
  return event;
}

afterEach(() => {
  document.body.innerHTML = "";
});

test("/ on the page is the quick search, with Shift too for the layouts that need it", () => {
  expect(isQuickSearchShortcut(press(document.body))).toBe(true);
  expect(isQuickSearchShortcut(press(document.body, { shiftKey: true }))).toBe(true);
});

test("not with Cmd, Ctrl or Alt, and not another key", () => {
  expect(isQuickSearchShortcut(press(document.body, { metaKey: true }))).toBe(false);
  expect(isQuickSearchShortcut(press(document.body, { ctrlKey: true }))).toBe(false);
  expect(isQuickSearchShortcut(press(document.body, { altKey: true }))).toBe(false);
  expect(isQuickSearchShortcut(press(document.body, { key: "k" }))).toBe(false);
});

test.each(["input", "textarea", "select"])("not in a %s", (tag) => {
  const field = document.body.appendChild(document.createElement(tag));
  expect(isQuickSearchShortcut(press(field))).toBe(false);
});

test("not while a dialog covers the page", () => {
  const dialog = document.body.appendChild(document.createElement("div"));
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  expect(isQuickSearchShortcut(press(document.body))).toBe(false);
});
