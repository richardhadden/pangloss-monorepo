import { expect, test } from "vitest";
import { formatDate } from "./format";

const exact = (year: number, month?: number, day?: number) => ({
  type: "ExactDate",
  calendar: "julian",
  year,
  month,
  day,
});

test("an exact date is said as far as it is known", () => {
  expect(
    formatDate({
      type: "ExactDate",
      calendar: "gregorian",
      year: 800,
      month: 12,
      day: 25,
    }),
  ).toBe("25 December 800");
  expect(
    formatDate({
      type: "ExactDate",
      calendar: "gregorian",
      year: 800,
      month: 12,
      day: null,
    }),
  ).toBe("December 800");
  expect(
    formatDate({ type: "ExactDate", calendar: "gregorian", year: 800 }),
  ).toBe("800");
});

test("a calendar other than the Gregorian is named, once", () => {
  expect(formatDate(exact(1500, 3, 2))).toBe("2 March 1500 (julian)");
  expect(
    formatDate({
      type: "DateRange",
      calendar: "julian",
      earliest: exact(1500),
      latest: exact(1502),
    }),
  ).toBe("1500 to 1502 (julian)");
});

test("a period, with an end that is ongoing or unknown", () => {
  const period = (end: unknown) => ({
    type: "Period",
    calendar: "gregorian",
    start: exact(1500),
    end,
  });
  expect(formatDate(period({ type: "OngoingDate" }))).toBe(
    "1500 – ongoing",
  );
  expect(formatDate(period({ type: "UnknownDate" }))).toBe("1500 – unknown");
});

test("EDTF is as written, and what the source said follows", () => {
  expect(
    formatDate({
      type: "EDTFDate",
      calendar: "gregorian",
      edtf: "075X",
      sourceText: "8th century",
    }),
  ).toBe("075X “8th century”");
});

test("a recurrence", () => {
  expect(
    formatDate({
      type: "Recurrence",
      calendar: "gregorian",
      frequency: "weekly",
      weekdays: [0],
      start: exact(1500),
      end: { type: "OngoingDate" },
    }),
  ).toBe("every Sunday, 1500 – ongoing");
});

test("something that is not a date is not said", () => {
  expect(formatDate({ type: "Person" })).toBeUndefined();
  expect(formatDate(null)).toBeUndefined();
});
