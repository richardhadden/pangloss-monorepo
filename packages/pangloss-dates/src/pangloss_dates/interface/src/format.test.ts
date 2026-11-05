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
      notBefore: exact(1500),
      notAfter: exact(1502),
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
  ).toBe("every week on Sunday, 1500 – ongoing");
  const yearly = (rule: Record<string, unknown>) =>
    formatDate({ type: "Recurrence", calendar: "gregorian", frequency: "yearly", weekdays: [], start: exact(1450), end: exact(1530), ...rule });
  expect(yearly({ month: 3, monthDay: 21 })).toBe("every year on 21 March, 1450 – 1530");
  expect(yearly({ month: 3, nth: 3, weekdays: [0] })).toBe("every year on the third Sunday of March, 1450 – 1530");
  expect(yearly({ month: 3, nth: -1, weekdays: [5], interval: 2 })).toBe("every 2 years on the last Friday of March, 1450 – 1530");
  expect(yearly({ easterOffset: 49 })).toBe("every year on Easter + 49 days, 1450 – 1530");
  expect(yearly({ easterOffset: 0 })).toBe("every year on Easter, 1450 – 1530");
  expect(yearly({ frequency: "monthly", monthDay: 21 })).toBe("every month on the 21., 1450 – 1530");
});

test("something that is not a date is not said", () => {
  expect(formatDate({ type: "Person" })).toBeUndefined();
  expect(formatDate(null)).toBeUndefined();
});

test("in another language: its month and weekday names, its order and words, and the names of the calendar and frequency", () => {
  const texts: Record<string, Record<string, string>> = {
    de: {
      date_day_month_year: "{day}. {month} {year}",
      date_range: "{from} bis {to}",
      date_ongoing: "laufend",
      date_every: "jede {what}",
      date_unit_week: "Woche",
      date_every_on: "{every} am {on}",
    },
    fr: { date_range: "de {from} à {to}", date_unknown: "inconnue", date_every_n: "tous les {n} {what}", date_unit_weeks: "semaines" },
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
    formatDate({ type: "DateRange", calendar: "julian", notBefore: exact(1500), notAfter: exact(1502) }, words("de")),
  ).toBe("1500 bis 1502 (Julianisch)");
  expect(
    formatDate({ type: "Period", calendar: "gregorian", start: exact(1500), end: { type: "UnknownDate" } }, words("fr")),
  ).toBe("1500 – inconnue");
  const recurrence = { type: "Recurrence", calendar: "gregorian", start: exact(1500), end: exact(1510) };
  expect(formatDate({ ...recurrence, frequency: "weekly", weekdays: [0] }, words("de"))).toBe("jede Woche am Sonntag, 1500 – 1510");
  expect(formatDate({ ...recurrence, frequency: "weekly", interval: 2 }, words("fr"))).toBe(
    "tous les 2 semaines, 1500 – 1510",
  );
});

test("a range with one end not known is said by the other", () => {
  const range = (notBefore: unknown, notAfter: unknown) => ({
    type: "DateRange",
    calendar: "gregorian",
    notBefore,
    notAfter,
  });
  expect(formatDate(range(exact(1500), { type: "UnknownDate" }))).toBe("not before 1500");
  expect(formatDate(range({ type: "UnknownDate" }, exact(1502)))).toBe("not after 1502");
});
