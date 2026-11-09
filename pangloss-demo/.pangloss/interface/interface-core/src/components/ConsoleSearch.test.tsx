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

test("the arrows in the box move through the list, without moving the cursor", async () => {
  const keys: string[] = [];
  const host = document.createElement("div");
  document.body.append(host);
  dispose = render(() => <ConsoleSearch onListKey={(key) => keys.push(key)} />, host);
  await settle();
  const box = host.querySelector("input")!;
  const down = new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true });
  box.dispatchEvent(down);
  box.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true, cancelable: true }));
  expect(keys).toEqual(["next", "previous"]);
  expect(down.defaultPrevented).toBe(true);
  // (with Shift, the arrow selects text as it always does)
  box.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", shiftKey: true, bubbles: true, cancelable: true }));
  expect(keys).toEqual(["next", "previous"]);
});

test("Enter opens the selected item only when the list on show is of what is in the box; otherwise it searches", async () => {
  const [query, setQuery] = createSignal("rome");
  const [pending, setPending] = createSignal(false);
  const keys: string[] = [];
  const asked: string[] = [];
  const host = document.createElement("div");
  document.body.append(host);
  dispose = render(
    () => (
      <ConsoleSearch
        query={query()}
        pending={pending()}
        onSearch={({ query }) => asked.push(query)}
        onListKey={(key) => keys.push(key)}
      />
    ),
    host,
  );
  await settle();
  const box = host.querySelector("input")!;
  const enter = () => box.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  enter();
  expect(keys).toEqual(["open"]);
  expect(asked).toEqual([]);
  // (typed, and not searched for yet)
  box.value = "paris";
  box.dispatchEvent(new InputEvent("input", { bubbles: true }));
  enter();
  expect(keys).toEqual(["open"]);
  expect(asked).toEqual(["paris"]);
  // (asked for, and still being answered: what is on show is the old list)
  setQuery("paris");
  setPending(true);
  flush();
  enter();
  expect(keys).toEqual(["open"]);
  setPending(false);
  flush();
  enter();
  expect(keys).toEqual(["open", "open"]);
});

test("it says when the box has the focus", async () => {
  const focused: boolean[] = [];
  const host = document.createElement("div");
  document.body.append(host);
  dispose = render(() => <ConsoleSearch onFocusChange={(on) => focused.push(on)} />, host);
  await settle();
  const box = host.querySelector("input")!;
  box.focus();
  box.blur();
  expect(focused).toEqual([true, false]);
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

test("a list that can show only what is used has a button that says what it would show next", () => {
  const [all, setAll] = createSignal(false);
  let toggled = 0;
  const host = document.createElement("div");
  document.body.append(host);
  dispose = render(
    () => <ConsoleSearch showingAll={all()} onToggleUsed={() => toggled++} />,
    host,
  );
  const button = () => [...host.querySelectorAll("button")].find((b) => /Show/.test(b.textContent ?? ""))!;
  expect(button().textContent).toBe("Show all");
  button().click();
  expect(toggled).toBe(1);
  setAll(true);
  flush();
  expect(button().textContent).toBe("Show used");
});

test("a list that cannot has no such button", () => {
  const host = document.createElement("div");
  document.body.append(host);
  dispose = render(() => <ConsoleSearch />, host);
  expect([...host.querySelectorAll("button")].some((b) => /Show/.test(b.textContent ?? ""))).toBe(false);
});
