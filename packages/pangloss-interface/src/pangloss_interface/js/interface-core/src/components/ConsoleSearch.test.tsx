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
