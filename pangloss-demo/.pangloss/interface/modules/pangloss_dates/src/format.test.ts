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

test("in another language: its month and weekday names, its order and words, and the names of the calendar and frequency", () => {
  const texts: Record<string, Record<string, string>> = {
    de: { date_day_month_year: "{day}. {month} {year}", date_range: "{from} bis {to}", date_ongoing: "laufend", date_every: "jeden {what}" },
    fr: { date_range: "de {from} à {to}", date_unknown: "inconnue", date_every_n: "tous les {n} {what}" },
  };
  const words = (language: string) => ({
    language,
    t: (key: string, english: string, params: Record<string, string | number> = {}) =>
      (texts[language]?.[key] ?? english).replace(/\{(\w+)\}/g, (_, name: string) => String(params[name])),
    memberName: (name: string, member: string) => {
      const names: Record<string, string> = {
        "Calendar.JULIAN": language === "de" ? "Julianisch" : "julien",
        "Frequency.WEEKLY": "hebdomadaire",
      };
      return names[`${name}.${member}`] ?? member;
    },
  });
  const christmas = { type: "ExactDate", calendar: "gregorian", year: 800, month: 12, day: 25 };
  expect(formatDate(christmas, words("de"))).toBe("25. Dezember 800");
  expect(formatDate(christmas, words("fr"))).toBe("25 décembre 800");
  expect(formatDate({ ...christmas, day: undefined }, words("fr"))).toBe("décembre 800");
  expect(formatDate(exact(1500, 3, 2), words("fr"))).toBe("2 mars 1500 (julien)");
  expect(
    formatDate({ type: "DateRange", calendar: "julian", earliest: exact(1500), latest: exact(1502) }, words("de")),
  ).toBe("1500 bis 1502 (Julianisch)");
  expect(
    formatDate({ type: "Period", calendar: "gregorian", start: exact(1500), end: { type: "UnknownDate" } }, words("fr")),
  ).toBe("1500 – inconnue");
  const recurrence = { type: "Recurrence", calendar: "gregorian", start: exact(1500), end: exact(1510) };
  expect(formatDate({ ...recurrence, weekdays: [0] }, words("de"))).toBe("jeden Sonntag, 1500 – 1510");
  expect(formatDate({ ...recurrence, frequency: "weekly", interval: 2 }, words("fr"))).toBe(
    "tous les 2 hebdomadaire, 1500 – 1510",
  );
});
