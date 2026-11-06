// @vitest-environment happy-dom
import { render } from "@solidjs/web";
import { afterEach, expect, test } from "vitest";
import { YearsTable } from "./YearsPage";

let dispose: (() => void) | undefined;
afterEach(() => {
  dispose?.();
  document.body.innerHTML = "";
});

test("each year is a row with its count and its months, each a link to the month", () => {
  const container = document.createElement("div");
  document.body.append(container);
  dispose = render(
    () => (
      <YearsTable
        report={{
          calendar: "julian",
          first_year: 1499,
          last_year: 1502,
          years: [
            { year: 1499, count: 0 },
            { year: 1500, count: 12 },
            { year: 1501, count: 3 },
            { year: 1502, count: 1 },
          ],
          truncated: false,
        }}
      />
    ),
    container,
  );
  const rows = [...document.body.querySelectorAll<HTMLElement>('[data-testid="calendar-year"]')];
  expect(rows.length).toBe(4);
  expect(rows[3]!.querySelector('[data-testid="calendar-year-count"]')!.textContent).toBe("1event");
  expect(rows[1]!.querySelector("th a")!.getAttribute("href")).toBe("/calendar/julian/1500/1");
  // (the count at the end: a number in a circle, then the word)
  expect(rows[1]!.querySelector('[data-testid="calendar-year-count"]')!.textContent).toBe("12events");
  expect(rows[2]!.querySelector('[data-testid="calendar-year-count"]')!.textContent).toBe("3events");
  expect(rows[1]!.id).toBe("year-1500");
  expect(rows.every((row) => row.getAttribute("aria-current") === null)).toBe(true);
  const months = [...rows[1]!.querySelectorAll<HTMLAnchorElement>("td a")];
  expect(months.length).toBe(12);
  expect(months[2]!.getAttribute("href")).toBe("/calendar/julian/1500/3");
  expect(months[2]!.textContent).toBe("Mar");
  expect(months[2]!.getAttribute("aria-label")).toBe("March 1500");
  // (a year with nothing in it is greyed)
  expect(rows[0]!.className).toContain("text-slate-400");
  expect(rows[1]!.className).not.toContain("text-slate-400");
});
