// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { createSignal } from "solid-js";
import { afterEach, expect, test } from "vitest";
import { allowOnly, integerCharacters, NumberInput } from "./NumberInput";

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

const settle = () => new Promise((resolve) => setTimeout(resolve));
const typing = (data: string) => new InputEvent("beforeinput", { data, cancelable: true, bubbles: true });

test("what has a character that is not allowed is refused before it gets in; the rest, and deleting, are let through", () => {
  const refuse = allowOnly(integerCharacters);
  for (const [data, refused] of [
    ["7", false],
    ["-12", false],
    ["e", true],
    ["1.5", true],
    ["12a", true],
  ] as const) {
    const event = typing(data);
    refuse(event);
    expect([data, event.defaultPrevented]).toEqual([data, refused]);
  }
  const deleting = new InputEvent("beforeinput", { inputType: "deleteContentBackward", cancelable: true });
  refuse(deleting);
  expect(deleting.defaultPrevented).toBe(false);
});

test("a number box has its own up and down buttons, which step within its limits, and no spinner of the browser's", async () => {
  const [value, setValue] = createSignal("4");
  const host = document.createElement("div");
  document.body.append(host);
  dispose = render(
    () => <NumberInput label="Year" value={value()} onInput={setValue} min={3} max={5} />,
    host,
  );
  const box = host.querySelector("input")!;
  expect(box.className).toContain("appearance:textfield");
  const up = host.querySelector<HTMLButtonElement>('[aria-label="Increase Year"]')!;
  const down = host.querySelector<HTMLButtonElement>('[aria-label="Decrease Year"]')!;
  // (the buttons are not stops of the Tab key: the Up and Down keys do the same in the box)
  expect(up.getAttribute("tabindex")).toBe("-1");
  const press = async (button: HTMLButtonElement, times = 1) => {
    for (let n = 0; n < times; n++) {
      button.click();
      await settle();
    }
  };
  await press(up);
  expect(value()).toBe("5");
  await press(up);
  expect(value()).toBe("5");
  await press(down, 3);
  expect(value()).toBe("3");
  const refused = typing("x");
  box.dispatchEvent(refused);
  expect(refused.defaultPrevented).toBe(true);
});
