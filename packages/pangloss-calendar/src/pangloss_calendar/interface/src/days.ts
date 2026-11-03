import type { CalendarName, DayOut } from "./api";

/** A day named in a calendar: what the addresses of the pages carry */
export interface DayName {
  calendar: CalendarName;
  year: number;
  month: number;
  day: number;
}

const REF = /^([JG])(-?\d+)-(\d{1,2})-(\d{1,2})$/;

/** `J1500-03-02` or `G1500-03-12` (as the API writes a day) as a name; undefined for anything else */
export function parseRef(ref: string): DayName | undefined {
  const found = REF.exec(ref);
  if (!found) return undefined;
  return {
    calendar: found[1] === "J" ? "julian" : "gregorian",
    year: Number(found[2]),
    month: Number(found[3]),
    day: Number(found[4]),
  };
}

const two = (n: number) => String(n).padStart(2, "0");

/** The name as the API reads it: `J1500-03-02` */
export function refOf(name: DayName): string {
  return `${name.calendar === "julian" ? "J" : "G"}${name.year}-${two(name.month)}-${two(name.day)}`;
}

/** The name of a day the API sent, in a calendar */
export function nameOf(day: DayOut, calendar: CalendarName): DayName {
  // (the API always writes a day it can parse; the fallback is for a malformed one)
  return parseRef(calendar === "julian" ? day.julian : day.gregorian) ?? { calendar, year: 0, month: 1, day: 1 };
}

/** The parts of an address (`/calendar/julian/1500/3/2`) as a name; undefined if they are not a day */
export function nameFromParams(params: Record<string, string | undefined>): DayName | undefined {
  const month = monthFromParams(params);
  const day = Number(params.day);
  if (!month || !Number.isInteger(day) || day < 1 || day > 31) return undefined;
  return { ...month, day };
}

/** The parts of an address (`/calendar/julian/1500/3`) as a month; undefined if they are not one */
export function monthFromParams(
  params: Record<string, string | undefined>,
): { calendar: CalendarName; year: number; month: number } | undefined {
  const calendar = params.calendar;
  const year = Number(params.year);
  const month = Number(params.month);
  if (calendar !== "julian" && calendar !== "gregorian") return undefined;
  if (!/^-?\d+$/.test(params.year ?? "") || !Number.isInteger(year)) return undefined;
  if (!Number.isInteger(month) || month < 1 || month > 12) return undefined;
  return { calendar, year, month };
}

export const yearsHref = (calendar: CalendarName) => `/calendar?calendar=${calendar}`;
/** A year in the list of years: its row, which is marked when it is gone to */
export const yearHref = (calendar: CalendarName, year: number) => `/calendar?calendar=${calendar}#year-${year}`;
export const monthHref = (calendar: CalendarName, year: number, month: number) => `/calendar/${calendar}/${year}/${month}`;
export const dayHref = (name: DayName) => `/calendar/${name.calendar}/${name.year}/${name.month}/${name.day}`;
/** The page of what a date is in */
export const itemHref = (type: string, id: string) => `/${type}/${encodeURIComponent(id)}`;

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

/** The names of the months, January first, in the language (English if it cannot be told) */
export function monthNames(language: string, style: "long" | "short" = "long"): string[] {
  try {
    const format = new Intl.DateTimeFormat(language, { month: style, timeZone: "UTC" });
    return MONTHS.map((_, index) => format.format(Date.UTC(2000, index, 1)));
  } catch {
    return style === "long" ? MONTHS : MONTHS.map((name) => name.slice(0, 3));
  }
}

/** The names of the weekdays, Sunday first (as the API numbers them), in the language */
export function weekdayNames(language: string, style: "long" | "short" = "long"): string[] {
  try {
    const format = new Intl.DateTimeFormat(language, { weekday: style, timeZone: "UTC" });
    // (2 January 2000 was a Sunday)
    return WEEKDAYS.map((_, index) => format.format(Date.UTC(2000, 0, 2 + index)));
  } catch {
    return style === "long" ? WEEKDAYS : WEEKDAYS.map((name) => name.slice(0, 3));
  }
}

/** The weekdays as the grid has them, Monday first */
export function weekHeadings(language: string, style: "long" | "short" = "short"): string[] {
  const names = weekdayNames(language, style);
  return [...names.slice(1), names[0]!];
}

export type Say = (key: string, english: string, params?: Record<string, string | number>) => string;

/** "2 March 1500", in the order and the words of the language (the `date_day_month_year` slot of the dates) */
export function sayDate(name: DayName, language: string, t: Say): string {
  return t("date_day_month_year", "{day} {month} {year}", {
    day: name.day,
    month: monthNames(language)[name.month - 1] ?? String(name.month),
    year: name.year,
  });
}

/** "March 1500" */
export function sayMonth(year: number, month: number, language: string, t: Say): string {
  return t("calendar_month_year", "{month} {year}", {
    month: monthNames(language)[month - 1] ?? String(month),
    year,
  });
}

/** The name of a calendar: "Julian", "Gregorian" */
export function sayCalendar(calendar: CalendarName, t: Say): string {
  return calendar === "julian" ? t("calendar_julian", "Julian") : t("calendar_gregorian", "Gregorian");
}

export const previousMonth = (year: number, month: number): [number, number] =>
  month === 1 ? [year - 1, 12] : [year, month - 1];
export const nextMonth = (year: number, month: number): [number, number] =>
  month === 12 ? [year + 1, 1] : [year, month + 1];

/** "Born · Alcuin of York": what a date is, then what it is in (a person's name alone says nothing of why it is here) */
export function sayRef(ref: { label: string; type: string; field: string }, fieldName: (model: string, field: string) => string): string {
  return `${fieldName(ref.type, ref.field)} · ${ref.label}`;
}

/** "between 2 March 1500 and 4 March 1500" */
export function sayBetween(first: DayName, last: DayName, language: string, t: Say): string {
  return t("calendar_between", "between {first} and {last}", {
    first: sayDate(first, language, t),
    last: sayDate(last, language, t),
  });
}
