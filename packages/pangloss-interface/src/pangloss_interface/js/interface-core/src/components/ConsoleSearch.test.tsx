// @vitest-environment happy-dom
import { createSignal, flush } from "solid-js";
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { ConsoleSearch } from "./ConsoleSearch";

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

const settle = (ms = 0) => new Promise((resolve) => setTimeout(resolve, ms));

test("what is typed is the box's own: the search it asked for coming back does not put back what it was, and only another address is written in", async () => {
  const [query, setQuery] = createSignal("rome");
  const asked: string[] = [];
  const host = document.createElement("div");
  document.body.append(host);
  dispose = render(
    () => <ConsoleSearch query={query()} onSearch={({ query }) => asked.push(query)} />,
    host,
  );
  const box = host.querySelector("input")!;
  // (the page opened with a search)
  expect(box.value).toBe("rome");
  const type = (text: string) => {
    box.value = text;
    box.dispatchEvent(new InputEvent("input", { bubbles: true }));
  };
  type("rom");
  box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  expect(asked).toEqual(["rom"]);
  // (more is typed before the address has the search)
  type("roman");
  setQuery("rom");
  flush();
  expect(box.value).toBe("roman");
  await settle(300);
  expect(asked).toEqual(["rom", "roman"]);
  // (going back)
  setQuery("paris");
  flush();
  expect(box.value).toBe("paris");
});

async function listed(query?: string) {
  const host = document.createElement("div");
  document.body.append(host);
  dispose = render(() => <ConsoleSearch query={query} />, host);
  await settle();
  return host.querySelector("input")!;
}

const press = (init: KeyboardEventInit, target: Element = document.body) => {
  target.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init }));
};

test("a character typed anywhere on the page goes to the box, after what is in it, and is left for the browser to write", async () => {
  const box = await listed("rome");
  const event = new KeyboardEvent("keydown", { key: "a", bubbles: true, cancelable: true });
  document.body.dispatchEvent(event);
  expect(document.activeElement).toBe(box);
  expect(box.selectionStart).toBe(4);
  expect(event.defaultPrevented).toBe(false);
});

test("a dead key starts typing too, so that an accented letter can be the first", async () => {
  const box = await listed();
  press({ key: "Dead" });
  expect(document.activeElement).toBe(box);
});

test.each([
  ["Control", { key: "a", ctrlKey: true }],
  ["Command", { key: "c", metaKey: true }],
  ["Option", { key: "ø", altKey: true }],
  ["a space (which scrolls)", { key: " " }],
  ["a key that writes nothing", { key: "Tab" }],
  ["an arrow", { key: "ArrowDown" }],
])("the box is left alone by %s", async (_name, init) => {
  const box = await listed();
  press(init);
  expect(document.activeElement).not.toBe(box);
});

test("the box is left alone while typing somewhere else", async () => {
  const other = document.createElement("textarea");
  document.body.append(other);
  const box = await listed();
  other.focus();
  press({ key: "a" }, other);
  expect(document.activeElement).toBe(other);
  expect(box.selectionStart).toBe(0);
});

test("the box is left alone by a key something has already dealt with", async () => {
  const button = document.createElement("button");
  button.addEventListener("keydown", (event) => event.preventDefault());
  document.body.append(button);
  const box = await listed();
  press({ key: "a" }, button);
  expect(document.activeElement).not.toBe(box);
});

test("the box is left alone while a dialog is open", async () => {
  const dialog = document.createElement("div");
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  document.body.append(dialog);
  const box = await listed();
  press({ key: "a" });
  expect(document.activeElement).not.toBe(box);
});

test("the button of the search form is there only for a list that has one; while it is in use, Deep search cannot be", () => {
  const host = document.createElement("div");
  document.body.append(host);
  const [open, setOpen] = createSignal(false);
  const [structured, setStructured] = createSignal(false);
  let toggled = 0;
  dispose = render(
    () => (
      <ConsoleSearch
        onToggleForm={() => {
          toggled += 1;
          setOpen(!open());
        }}
        formOpen={open()}
        structured={structured()}
      />
    ),
    host,
  );
  const form = () => host.querySelector<HTMLButtonElement>('button[aria-label^="Search by fields"]')!;
  const deep = () => host.querySelector<HTMLButtonElement>('button[aria-label="Deep search"]')!;
  expect(form().getAttribute("aria-pressed")).toBe("false");
  form().click();
  flush();
  expect(toggled).toBe(1);
  expect(form().getAttribute("aria-pressed")).toBe("true");
  expect(deep().disabled).toBe(false);
  expect(host.querySelector("[data-in-use]")).toBeNull();
  setStructured(true);
  flush();
  expect(form().getAttribute("aria-label")).toBe("Search by fields (in use)");
  expect(host.querySelector("[data-in-use]")).not.toBeNull();
  expect(deep().disabled).toBe(true);
});

test("without a search form there is no button for one", () => {
  const host = document.createElement("div");
  document.body.append(host);
  dispose = render(() => <ConsoleSearch />, host);
  expect(host.querySelector('button[aria-label^="Search by fields"]')).toBeNull();
});
