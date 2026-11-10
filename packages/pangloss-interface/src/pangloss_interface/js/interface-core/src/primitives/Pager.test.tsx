// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { createSignal } from "solid-js";
import { expect, test } from "vitest";
import { Pager } from "./Pager";

function mount(page: number, pages: number) {
  const host = document.createElement("div");
  const asked: number[] = [];
  const [at, setAt] = createSignal(page);
  render(() => <Pager page={at()} pages={pages} onPage={(next) => asked.push(next)} />, host);
  const buttons = () => [...host.querySelectorAll("button")];
  return { host, asked, setAt, previous: () => buttons()[0]!, next: () => buttons()[1]! };
}

test("one page has no pager", () => {
  expect(mount(1, 1).host.querySelector("nav")).toBeNull();
  expect(mount(1, 0).host.querySelector("nav")).toBeNull();
});

test("it says which page of how many, and asks for the one before or after", () => {
  const { host, asked, previous, next } = mount(2, 7);
  expect(host.querySelector("nav")?.getAttribute("aria-label")).toBe("Pages");
  expect(host.textContent).toContain("Page 2 of 7");
  expect(previous().textContent).toBe("Previous");
  expect(next().textContent).toBe("Next");
  next().click();
  previous().click();
  expect(asked).toEqual([3, 1]);
});

test("there is nothing before the first page, nor after the last", () => {
  const first = mount(1, 3);
  expect(first.previous().disabled).toBe(true);
  expect(first.next().disabled).toBe(false);
  const last = mount(3, 3);
  expect(last.previous().disabled).toBe(false);
  expect(last.next().disabled).toBe(true);
});

test("it follows the page it is given", async () => {
  const { host, setAt, previous } = mount(1, 3);
  setAt(2);
  await Promise.resolve();
  await new Promise((resolve) => setTimeout(resolve));
  expect(host.textContent).toContain("Page 2 of 3");
  expect(previous().disabled).toBe(false);
});
