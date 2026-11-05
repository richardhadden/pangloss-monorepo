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

export function weekdayNames(language: string): string[] {
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

const NTH_SLOTS: Record<number, [string, string]> = {
  1: ["date_nth_first", "first"],
  2: ["date_nth_second", "second"],
  3: ["date_nth_third", "third"],
  4: ["date_nth_fourth", "fourth"],
  5: ["date_nth_fifth", "fifth"],
  [-1]: ["date_nth_last", "last"],
};

/**
 * "every year on 21 March", "every 2 years on the third Sunday of March", "every year on Easter + 49 days",
 * "every month on the 21st", "every week on Sunday, Monday"
 */
function recurrence(date: Data, words: DateWords): string {
  const names = weekdayNames(words.language);
  const weekdays = (Array.isArray(date.weekdays) ? date.weekdays : []).map((w) => names[w as number] ?? String(w));
  const month = num(date.month);
  const monthName = month !== undefined ? (monthNames(words.language)[month - 1] ?? String(month)) : undefined;
  const nth = num(date.nth);
  const nthWord = nth !== undefined && NTH_SLOTS[nth] ? words.t(...NTH_SLOTS[nth]!) : undefined;
  const monthDay = num(date.monthDay ?? date.month_day);
  const easter = num(date.easterOffset ?? date.easter_offset);
  const frequency = typeof date.frequency === "string" ? date.frequency : "";
  const n = num(date.interval) ?? 1;
  const unit =
    frequency === "weekly"
      ? [words.t("date_unit_week", "week"), words.t("date_unit_weeks", "weeks")]
      : frequency === "monthly"
        ? [words.t("date_unit_month", "month"), words.t("date_unit_months", "months")]
        : [words.t("date_unit_year", "year"), words.t("date_unit_years", "years")];
  let on: string | undefined;
  if (easter !== undefined) {
    on =
      easter === 0
        ? words.t("date_easter", "Easter")
        : words.t("date_from_easter", "Easter {sign} {days} days", {
            sign: easter > 0 ? "+" : "−",
            days: Math.abs(easter),
          });
  } else if (nthWord !== undefined && weekdays.length > 0) {
    on =
      monthName !== undefined
        ? words.t("date_nth_weekday_of", "the {nth} {weekday} of {month}", { nth: nthWord, weekday: weekdays[0]!, month: monthName })
        : words.t("date_nth_weekday", "the {nth} {weekday}", { nth: nthWord, weekday: weekdays[0]! });
  } else if (monthName !== undefined && monthDay !== undefined) {
    on = words.t("date_day_month", "{day} {month}", { day: monthDay, month: monthName });
  } else if (monthName !== undefined) {
    on = monthName;
  } else if (monthDay !== undefined) {
    on = words.t("date_day_of_the_month", "the {day}.", { day: monthDay });
  } else if (weekdays.length > 0) {
    on = weekdays.join(", ");
  }
  const every =
    n !== 1
      ? words.t("date_every_n", "every {n} {what}", { n, what: unit[1]! })
      : words.t("date_every", "every {what}", { what: unit[0]! });
  return on === undefined ? every : words.t("date_every_on", "{every} on {on}", { every, on });
}

/**
 * A date as a person would say it, from the JSON of any of the date models of `pangloss_dates`
 * (`undefined` for something that is not a date it knows). The calendar is named only if it is not the
 * Gregorian, and what the source said (`sourceText`) follows in quotes.
 */
export function formatDate(date: unknown, words: DateWords = ENGLISH): string | undefined {
  return say(date, true, words);
}

const isUnknown = (end: unknown) => isData(end) && end.type === "UnknownDate";

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
      // (one end may be unknown: then it is said by the other)
      if (isUnknown(date.notAfter)) text = words.t("date_not_before_reads", "not before {date}", { date: inner(date.notBefore) });
      else if (isUnknown(date.notBefore)) text = words.t("date_not_after_reads", "not after {date}", { date: inner(date.notAfter) });
      else text = words.t("date_range", "{from} to {to}", { from: inner(date.notBefore), to: inner(date.notAfter) });
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
