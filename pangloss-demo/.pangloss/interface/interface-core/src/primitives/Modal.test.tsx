// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test, vi } from "vitest";
import { Modal } from "./Modal";

let cleanup: (() => void) | undefined;
afterEach(() => {
  cleanup?.();
  document.body.innerHTML = "";
  document.body.style.overflow = "";
});

const settle = () => new Promise((resolve) => setTimeout(resolve));

function open(onClose = () => {}) {
  const opener = document.createElement("button");
  opener.textContent = "open";
  document.body.append(opener);
  opener.focus();
  const container = document.createElement("div");
  document.body.append(container);
  const dispose = render(
    () => (
      <Modal title="Log in" onClose={onClose}>
        <input name="a" autofocus />
        <button type="button">go</button>
      </Modal>
    ),
    container,
  );
  cleanup = dispose;
  return { opener, dispose };
}

test("it is a dialog on the body, named by its heading, with the page behind it covered", async () => {
  open();
  await settle();
  const dialog = document.body.querySelector<HTMLElement>('[role="dialog"]')!;
  expect(dialog).not.toBeNull();
  expect(dialog.getAttribute("aria-modal")).toBe("true");
  const heading = document.getElementById(dialog.getAttribute("aria-labelledby")!)!;
  expect(heading.textContent).toBe("Log in");
  // (in the portal, not in the container it was rendered into)
  expect(dialog.closest("body > div")).not.toBeNull();
  // The backdrop is what the dialog is in: it covers the screen, so a click cannot reach the page
  const backdrop = dialog.parentElement!;
  expect(backdrop.className).toContain("fixed");
  expect(backdrop.className).toContain("inset-0");
  expect(document.body.style.overflow).toBe("hidden");
});

test("the focus goes in, and back to what had it when the dialog goes", async () => {
  const { opener, dispose } = open();
  await settle();
  expect(document.activeElement?.getAttribute("name")).toBe("a");
  dispose();
  cleanup = undefined;
  await settle();
  expect(document.activeElement).toBe(opener);
  expect(document.body.style.overflow).toBe("");
});

test("Escape and the close button ask for it to close; a click on the backdrop does not", async () => {
  const onClose = vi.fn();
  open(onClose);
  await settle();
  const dialog = document.body.querySelector<HTMLElement>('[role="dialog"]')!;
  dialog.parentElement!.click();
  expect(onClose).not.toHaveBeenCalled();
  document.activeElement!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  expect(onClose).toHaveBeenCalledTimes(1);
  document.body.querySelector<HTMLElement>('button[aria-label="Close"]')!.click();
  expect(onClose).toHaveBeenCalledTimes(2);
});

test("Tab goes round inside the dialog", async () => {
  open();
  await settle();
  const buttons = [...document.body.querySelectorAll<HTMLElement>('[role="dialog"] button')];
  const last = buttons[buttons.length - 1]!;
  const first = document.body.querySelector<HTMLElement>('[role="dialog"] button')!;
  last.focus();
  const tab = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
  last.dispatchEvent(tab);
  expect(tab.defaultPrevented).toBe(true);
  expect(document.activeElement).toBe(first);
  const back = new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true, cancelable: true });
  first.dispatchEvent(back);
  expect(back.defaultPrevented).toBe(true);
  expect(document.activeElement).toBe(last);
});
