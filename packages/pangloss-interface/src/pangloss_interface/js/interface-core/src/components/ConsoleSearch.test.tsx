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
