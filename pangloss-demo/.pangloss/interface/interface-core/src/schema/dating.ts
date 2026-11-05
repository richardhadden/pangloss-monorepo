/**
 * What refers to an item, by date: the items of a `Dateable` model (pangloss-dates) carry a copy of their
 * date in their reference (`dateSortDay`, `dateEndSortDay`, a day number; `dateText`, the date said with no
 * words), so they can be ordered by it with what the page already has, on the client.
 */
import type { ModelDefinitions } from "../types";
import { getModel } from "./lookup";

type Data = Record<string, unknown>;

/** One item that refers to the item of the page, with the name of the field (as the page says it) it is in */
export interface IncomingEntry {
  key: string;
  name: string;
  item: Data;
}

export interface ByDate {
  /** Dated, in order of their date */
  dated: IncomingEntry[];
  /** Of a dateable kind, but nothing is known of when (or their copy of the date was never made) */
  unknown: IncomingEntry[];
  /** Of a kind that has no date: a date means nothing for them */
  undated: IncomingEntry[];
}

export const DATEABLE = "Dateable";

export function isDateable(definitions: ModelDefinitions, type: unknown): boolean {
  return typeof type === "string" && (getModel(definitions, type)?.traits ?? []).includes(DATEABLE);
}

const sortDay = (entry: IncomingEntry) => entry.item.dateSortDay as number;
const endDay = (entry: IncomingEntry) =>
  typeof entry.item.dateEndSortDay === "number" ? entry.item.dateEndSortDay : sortDay(entry);

export function isDated(entry: IncomingEntry): boolean {
  return typeof entry.item.dateSortDay === "number" && entry.item.dateText !== "?";
}

/** The entries in three: dated (by day, then by the day their end sorts by, then by label), not known, not dateable */
export function arrangeByDate(entries: IncomingEntry[], definitions: ModelDefinitions): ByDate {
  const arranged: ByDate = { dated: [], unknown: [], undated: [] };
  for (const entry of entries) {
    if (!isDateable(definitions, entry.item.type)) arranged.undated.push(entry);
    else if (isDated(entry)) arranged.dated.push(entry);
    else arranged.unknown.push(entry);
  }
  const label = (entry: IncomingEntry) => String(entry.item.label ?? "");
  arranged.dated.sort(
    (a, b) => sortDay(a) - sortDay(b) || endDay(a) - endDay(b) || label(a).localeCompare(label(b)),
  );
  return arranged;
}

/** The (proleptic Gregorian) year of a day number: for the year slider, which needs no more than the year */
export function yearOfDay(day: number): number {
  // (Richards' algorithm, as in pangloss_dates.calendar)
  const f = day + 1401 + Math.floor((Math.floor((4 * day + 274277) / 146097) * 3) / 4) - 38;
  const e = 4 * f + 3;
  const h = 5 * Math.floor((e % 1461) / 4) + 2;
  const month = (Math.floor(h / 153) + 2) % 12 + 1;
  return Math.floor(e / 1461) - 4716 + Math.floor((12 + 2 - month) / 12);
}

/** The first and the last year of the dated entries (a period to the year its end sorts by) */
export function yearSpan(dated: IncomingEntry[]): [number, number] | undefined {
  if (dated.length === 0) return undefined;
  const firsts = dated.map((entry) => yearOfDay(sortDay(entry)));
  const lasts = dated.map((entry) => yearOfDay(endDay(entry)));
  return [Math.min(...firsts), Math.max(...lasts)];
}

/** Whether an entry falls in the years from `from` to `to` (a period, if any of it does) */
export function inYears(entry: IncomingEntry, from: number, to: number): boolean {
  return yearOfDay(sortDay(entry)) <= to && yearOfDay(endDay(entry)) >= from;
}
