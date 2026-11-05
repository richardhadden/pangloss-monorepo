/**
 * What refers to an item, by date: the items of a `Dateable` model (pangloss-dates) carry a copy of their
 * date in their reference (`dateSortDay`, `dateEndSortDay`, a day number; `dateText`, the date said with no
 * words), so they can be ordered by it with what the page already has, on the client.
 */
import { getModel } from "@pangloss/interface-core";
import type { IncomingEntry, ModelDefinitions } from "@pangloss/interface-core";
import { monthNames } from "./format";
import type { DateWords } from "./format";

export interface ByDate {
  /** Dated, in order of their date */
  dated: IncomingEntry[];
  /** Of a dateable kind, but nothing is known of when (or their copy of the date was never made) */
  unknown: IncomingEntry[];
}

export const DATEABLE = "Dateable";

/** Whether items of a type can have a date: its model has the `Dateable` trait */
export function isDateable(definitions: ModelDefinitions, type: unknown): boolean {
  return typeof type === "string" && (getModel(definitions, type)?.traits ?? []).includes(DATEABLE);
}

const sortDay = (entry: IncomingEntry) => entry.item.dateSortDay as number;
const endDay = (entry: IncomingEntry) =>
  typeof entry.item.dateEndSortDay === "number" ? entry.item.dateEndSortDay : sortDay(entry);

export function isDated(entry: IncomingEntry): boolean {
  return typeof entry.item.dateSortDay === "number" && entry.item.dateText !== "?";
}

/** The entries (of dateable kinds) in two: dated (by day, then by the day their end sorts by, then by label), and not known */
export function arrangeByDate(entries: IncomingEntry[]): ByDate {
  const arranged: ByDate = { dated: [], unknown: [] };
  for (const entry of entries) (isDated(entry) ? arranged.dated : arranged.unknown).push(entry);
  const label = (entry: IncomingEntry) => String(entry.item.label ?? "");
  arranged.dated.sort(
    (a, b) => sortDay(a) - sortDay(b) || endDay(a) - endDay(b) || label(a).localeCompare(label(b)),
  );
  return arranged;
}

/** The (proleptic Gregorian) year of a day number: for the timeline, which needs no more than the year */
export function yearOfDay(day: number): number {
  // (Richards' algorithm, as in pangloss_dates.calendar)
  const f = day + 1401 + Math.floor((Math.floor((4 * day + 274277) / 146097) * 3) / 4) - 38;
  const e = 4 * f + 3;
  const h = 5 * Math.floor((e % 1461) / 4) + 2;
  const month = (Math.floor(h / 153) + 2) % 12 + 1;
  return Math.floor(e / 1461) - 4716 + Math.floor((12 + 2 - month) / 12);
}

/** The first and the last year of the dated entries (a period to the year its end sorts by): the span of the timeline */
export function yearSpan(dated: IncomingEntry[]): [number, number] | undefined {
  if (dated.length === 0) return undefined;
  const firsts = dated.map((entry) => yearOfDay(sortDay(entry)));
  const lasts = dated.map((entry) => yearOfDay(endDay(entry)));
  return [Math.min(...firsts), Math.max(...lasts)];
}

/** The year an entry is put under in the list (the year of the day it sorts by) */
export function yearOf(entry: IncomingEntry): number {
  return yearOfDay(sortDay(entry));
}

/** The dated entries under their years, in the order they are in */
export function byYear(dated: IncomingEntry[]): [number, IncomingEntry[]][] {
  const years: [number, IncomingEntry[]][] = [];
  for (const entry of dated) {
    const year = yearOf(entry);
    const last = years.at(-1);
    if (last && last[0] === year) last[1].push(entry);
    else years.push([year, [entry]]);
  }
  return years;
}

const EXACT = /^(-?\d+)(?:-(\d{2}))?(?:-(\d{2}))?$/;

/** The two ends of `a–b`, where `a` may be a range in brackets (`[a–b]–c`, the start of a period) */
function ends(text: string): [string, string] | undefined {
  const at = text.startsWith("[") ? text.indexOf("]–") + 1 : text.indexOf("–");
  return at > 0 ? [text.slice(0, at), text.slice(at + 1)] : undefined;
}

/**
 * The date a `Dateable` item carries with no words (its `dateText`: `1500-03-02`, `≥ 1490`, `1500–1502`, `1500–…`,
 * `↻ 1500–1520`, `?`) said in words: "2 March 1500", "not before 1490", "1500 to 1502". What it does not know (an
 * EDTF date) is left as it is.
 */
export function dateInWords(text: string, words: DateWords): string {
  const { t } = words;
  if (text === "?") return t("date_unknown", "unknown");
  if (text === "…") return t("date_ongoing", "ongoing");
  if (text.startsWith("↻ ")) return `↻ ${dateInWords(text.slice(2), words)}`;
  if (text.startsWith("[") && text.endsWith("]") && ends(text) === undefined)
    return `(${dateInWords(text.slice(1, -1), words)})`;
  if (text.startsWith("≥ ")) return t("date_not_before_reads", "not before {date}", { date: dateInWords(text.slice(2), words) });
  if (text.startsWith("≤ ")) return t("date_not_after_reads", "not after {date}", { date: dateInWords(text.slice(2), words) });
  const exact = EXACT.exec(text);
  if (exact) {
    const [, year, month, day] = exact;
    if (day) return t("date_day_month_year", "{day} {month} {year}", { day: Number(day), month: monthNames(words.language)[Number(month) - 1], year: year! });
    if (month) return t("date_month_year", "{month} {year}", { month: monthNames(words.language)[Number(month) - 1], year: year! });
    return year!;
  }
  const both = ends(text);
  if (both) return t("date_range", "{from} to {to}", { from: dateInWords(both[0], words), to: dateInWords(both[1], words) });
  return text;
}
