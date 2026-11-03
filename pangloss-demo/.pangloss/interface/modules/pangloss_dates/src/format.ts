type Data = Record<string, unknown>;

/**
 * The words a date is said in: the language (month and weekday names come from `Intl` in it), the
 * interface's texts (`t`, the `date_*` slots: the order of day, month and year, "to", "ongoing"...),
 * and the names of the members of an enum (the calendar, the frequency). Without them it is English.
 */
export interface DateWords {
  language: string;
  t: (key: string, english: string, params?: Record<string, string | number>) => string;
  memberName?: (name: string, member: string) => string;
}

const fill = (text: string, params: Record<string, string | number> = {}) =>
  text.replace(/\{(\w+)\}/g, (whole, name: string) => (name in params ? String(params[name]) : whole));

const ENGLISH: DateWords = { language: "en", t: (_key, english, params) => fill(english, params) };

export const MONTHS = [
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
const WEEKDAYS = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];

/** The names of the months, January first, in `language` (the English ones if it cannot be told) */
export function monthNames(language = "en"): string[] {
  try {
    const format = new Intl.DateTimeFormat(language, { month: "long", timeZone: "UTC" });
    return MONTHS.map((_, index) => format.format(Date.UTC(2000, index, 1)));
  } catch {
    return MONTHS;
  }
}

function weekdayNames(language: string): string[] {
  try {
    const format = new Intl.DateTimeFormat(language, { weekday: "long", timeZone: "UTC" });
    // (2 January 2000 was a Sunday)
    return WEEKDAYS.map((_, index) => format.format(Date.UTC(2000, 0, 2 + index)));
  } catch {
    return WEEKDAYS;
  }
}

/** A member of an enum by its value ("julian"), in the words given: as it is, if they have no name for it */
function member(words: DateWords, name: string, value: string): string {
  const code = value.toUpperCase();
  const named = words.memberName?.(name, code);
  return named && named !== code ? named : value;
}

const isData = (value: unknown): value is Data =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const num = (value: unknown) => (typeof value === "number" ? value : undefined);

/** 25 December 800; December 800; 800 (the order, and the words, of the language) */
function exact(date: Data, words: DateWords): string {
  const month = num(date.month);
  const day = num(date.day);
  const year = num(date.year);
  const monthName = month !== undefined ? (monthNames(words.language)[month - 1] ?? String(month)) : undefined;
  if (day !== undefined && monthName !== undefined && year !== undefined)
    return words.t("date_day_month_year", "{day} {month} {year}", { day, month: monthName, year });
  if (monthName !== undefined && year !== undefined)
    return words.t("date_month_year", "{month} {year}", { month: monthName, year });
  return [day, monthName, year].filter((part) => part !== undefined).join(" ");
}

function recurrence(date: Data, words: DateWords): string {
  const names = weekdayNames(words.language);
  const weekdays = (Array.isArray(date.weekdays) ? date.weekdays : []).map((w) => names[w as number] ?? w);
  const what =
    Array.isArray(date.weekdays) && weekdays.length > 0
      ? weekdays.join(", ")
      : typeof date.frequency === "string"
        ? member(words, "Frequency", date.frequency)
        : "";
  const n = num(date.interval);
  return (
    n && n !== 1
      ? words.t("date_every_n", "every {n} {what}", { n, what })
      : words.t("date_every", "every {what}", { what })
  ).trim();
}

/**
 * A date as a person would say it, from the JSON of any of the date models of `pangloss_dates`
 * (`undefined` for something that is not a date it knows). The calendar is named only if it is not the
 * Gregorian, and what the source said (`sourceText`) follows in quotes.
 */
export function formatDate(date: unknown, words: DateWords = ENGLISH): string | undefined {
  return say(date, true, words);
}

// (the ends of a period or a range are in its calendar: they do not say it again)
function say(date: unknown, outer: boolean, words: DateWords): string | undefined {
  if (!isData(date)) return undefined;
  const inner = (part: unknown) => String(say(part, false, words));
  let text: string | undefined;
  switch (date.type) {
    case "ExactDate":
      text = exact(date, words);
      break;
    case "EDTFDate":
      text = typeof date.edtf === "string" ? date.edtf : undefined;
      break;
    case "DateRange":
      text = words.t("date_range", "{from} to {to}", { from: inner(date.earliest), to: inner(date.latest) });
      break;
    case "OngoingDate":
      text = words.t("date_ongoing", "ongoing");
      break;
    case "UnknownDate":
      text = words.t("date_unknown", "unknown");
      break;
    case "Period":
      text = `${inner(date.start)} – ${inner(date.end)}`;
      break;
    case "Recurrence":
      text = `${recurrence(date, words)}, ${inner(date.start)} – ${inner(date.end)}`;
      break;
    default:
      return undefined;
  }
  if (text === undefined) return undefined;
  if (
    typeof date.calendar === "string" &&
    date.calendar !== "gregorian" &&
    outer
  ) {
    text += ` (${member(words, "Calendar", date.calendar)})`;
  }
  if (outer && typeof date.sourceText === "string" && date.sourceText)
    text += ` “${date.sourceText}”`;
  return text;
}
