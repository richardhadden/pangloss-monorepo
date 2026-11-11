// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { expect, test } from "vitest";
import { CloseIcon } from "./icons";

test("the ✕ is drawn as every icon is, as heavy on screen at each size", () => {
  const drawn = (size?: "5" | "4" | "3.5") => {
    const host = document.createElement("div");
    render(() => <CloseIcon size={size} />, host);
    return host.querySelector("svg")!;
  };
  for (const [size, classes] of [
    [undefined, ["size-5", "stroke-[1.5]"]],
    ["4", ["size-4", "stroke-[1.75]"]],
    ["3.5", ["size-3.5", "stroke-2"]],
  ] as const) {
    const icon = drawn(size);
    for (const name of [...classes, "select-none", "fill-none", "stroke-current"]) {
      expect(icon.classList.contains(name)).toBe(true);
    }
    expect(icon.getAttribute("aria-hidden")).toBe("true");
    expect(icon.getAttribute("stroke-linecap")).toBe("square");
  }
});
