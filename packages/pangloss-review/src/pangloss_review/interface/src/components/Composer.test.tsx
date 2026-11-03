// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test, vi } from "vitest";
import { shorten } from "../parts";
import type { Part } from "../parts";
import { Composer } from "./Composer";

const PARTS: Part[] = [
  { id: "s1", type: "Statement", label: "Charles was crowned in Aachen in the year 800, by the pope" },
  { id: "s2", type: "Statement", label: "Another statement" },
  { id: "m1", type: "MemberOf", label: null },
];

const settle = async () => {
  for (let i = 0; i < 3; i++) await new Promise((resolve) => setTimeout(resolve));
};

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

// (`parts: null`: not read yet)
function show(parts: Part[] | null = PARTS) {
  const onSend = vi.fn(async (_text: string, _part?: Part) => undefined);
  const onWantParts = vi.fn();
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(() => <Composer parts={parts ?? undefined} onSend={onSend} onWantParts={onWantParts} />, container);
  const box = container.querySelector("textarea")!;
  return { onSend, onWantParts, box, container };
}

async function type(box: HTMLTextAreaElement, text: string) {
  box.value = text;
  box.setSelectionRange(text.length, text.length);
  box.dispatchEvent(new Event("input", { bubbles: true }));
  await settle();
}

async function key(box: HTMLTextAreaElement, name: string, more: KeyboardEventInit = {}) {
  const event = new KeyboardEvent("keydown", { key: name, bubbles: true, cancelable: true, ...more });
  box.dispatchEvent(event);
  await settle();
  return event;
}

const options = () => [...document.querySelectorAll<HTMLElement>('[role="option"]')];
const chip = () => document.querySelector('[data-testid="review-about"]');

test("# opens the list of parts, with type and shortened label, and asks for the parts", async () => {
  const { box, onWantParts } = show();
  await type(box, "Look at #");
  expect(onWantParts).toHaveBeenCalled();
  expect(box.getAttribute("aria-expanded")).toBe("true");
  expect(options().map((o) => o.textContent)).toEqual([
    `Statement${shorten(PARTS[0]!.label!)}`,
    "StatementAnother statement",
    "MemberOfm1",
  ]);
  expect(options()[0]!.getAttribute("aria-selected")).toBe("true");
});

test("what is typed after # filters; arrows and Enter choose, the #word goes, and the chip says what it is about", async () => {
  const { box, onSend } = show();
  await type(box, "Look at #stat");
  expect(options()).toHaveLength(2);
  await key(box, "ArrowDown");
  expect(options()[1]!.getAttribute("aria-selected")).toBe("true");
  const enter = await key(box, "Enter");
  expect(enter.defaultPrevented).toBe(true);
  expect(options()).toHaveLength(0);
  expect(box.value).toBe("Look at ");
  expect(chip()?.textContent).toContain("About: Statement · Another statement");
  await type(box, "Look at this");
  await key(box, "Enter", { ctrlKey: true });
  expect(onSend).toHaveBeenCalledWith("Look at this", PARTS[1]);
  // (sent: the chip goes with the text)
  expect(chip()).toBeNull();
  expect(box.value).toBe("");
});

test("a click chooses too; the chip's ✕ makes it not about a part", async () => {
  const { box, onSend } = show();
  await type(box, "#");
  options()[2]!.click();
  await settle();
  expect(chip()?.textContent).toContain("MemberOf · m1");
  chip()!.querySelector("button")!.click();
  await settle();
  expect(chip()).toBeNull();
  await type(box, "General remark");
  document.querySelector<HTMLButtonElement>('button[type="submit"]')!.click();
  await settle();
  expect(onSend).toHaveBeenCalledWith("General remark", undefined);
});

test("Escape closes the list and is used up (the panel stays open)", async () => {
  const { box } = show();
  await type(box, "#");
  const escape = await key(box, "Escape");
  expect(escape.defaultPrevented).toBe(true);
  expect(options()).toHaveLength(0);
  // (with the list closed, Escape is the panel's)
  expect((await key(box, "Escape")).defaultPrevented).toBe(false);
});

test("words after the # keep the list open while a part matches them", async () => {
  const { box } = show();
  await type(box, "#another st");
  expect(options().map((o) => o.textContent)).toEqual(["StatementAnother statement"]);
  await type(box, "#another statement is wrong");
  expect(document.querySelector('[role="listbox"]')).toBeNull();
});

test("a # in a word is not a mention; nothing matching says so; while the parts are read, it says that", async () => {
  const { box } = show();
  await type(box, "issue#3");
  expect(document.querySelector('[role="listbox"]')).toBeNull();
  await type(box, "#zzz");
  expect(document.querySelector('[role="listbox"]')?.textContent).toBe("No parts match");
  dispose?.();
  const loading = show(null);
  await type(loading.box, "#");
  expect(document.querySelector('[role="listbox"]')?.textContent).toBe("Loading…");
});

test("the button puts a # where the caret is, which opens the list", async () => {
  const { box } = show();
  await type(box, "See");
  [...document.querySelectorAll("button")].find((b) => b.textContent?.includes("About a part"))!.click();
  await settle();
  expect(box.value).toBe("See #");
  expect(options()).toHaveLength(3);
});

test("what was written, and the part, are put back if the comment was not made", async () => {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => <Composer parts={PARTS} onSend={() => Promise.reject(new Error("no"))} />,
    container,
  );
  const box = container.querySelector("textarea")!;
  await type(box, "#");
  options()[0]!.click();
  await settle();
  await type(box, "Keep me");
  await key(box, "Enter", { metaKey: true });
  await settle();
  expect(box.value).toBe("Keep me");
  expect(chip()).not.toBeNull();
});
