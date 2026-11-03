// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import DateCard from "./DateCard";

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

test("a date is only said, none of the bounds and sort days worked out for it", () => {
  const host = document.createElement("div");
  document.body.append(host);
  const item = {
    type: "ExactDate", calendar: "julian", year: 1500, month: 3, day: 2,
    precision: "day", earliestFuzzy: 1994996, sortDay: 1994996, edtf: "075X",
  };
  dispose = render(() => <DateCard type="ExactDate" label="" item={item} context="embedded" />, host);
  expect(host.textContent).toBe("2 March 1500 (julian)");
});
