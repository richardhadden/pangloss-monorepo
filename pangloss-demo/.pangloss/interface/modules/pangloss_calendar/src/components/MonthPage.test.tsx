// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { day, month, ref } from "./fixtures";
import { MonthFoot } from "./MonthPage";

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

test("a date known only roughly, beyond the month, is listed under the grid as between its days", () => {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <MonthFoot
        report={month(
          {},
          {
            roughly: [
              {
                ref: ref("b1", "Alcuin of York", "Person", "born"),
                first: { ...day(1), jdn: day(1).jdn - 59, julian: "J1500-01-01", gregorian: "G1500-01-11" },
                last: { ...day(31), jdn: day(31).jdn + 275, julian: "J1500-12-31", gregorian: "G1501-01-10" },
              },
            ],
          },
        )}
      />
    ),
    container,
  );
  const rows = [...document.body.querySelectorAll<HTMLElement>('[data-testid="calendar-roughly"]')];
  expect(rows.length).toBe(1);
  expect(rows[0]!.querySelector("a")!.textContent).toBe("born · Alcuin of York");
  expect(rows[0]!.querySelector("a")!.getAttribute("href")).toBe("/Person/b1");
  expect(rows[0]!.textContent).toContain("between 1 January 1500 and 31 December 1500");
  expect(document.body.textContent).toContain("Sometime in or around this month");
});
