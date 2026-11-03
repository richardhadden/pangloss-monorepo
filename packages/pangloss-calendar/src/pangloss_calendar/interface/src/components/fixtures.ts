// Julian March 1500 as the API describes it: the 1st is a Sunday (day number 2268993), so the grid has six rows
import type { Characterised, DayOut, Hit, MonthReport, Ref } from "../api";

export const FIRST = 2268993;

const two = (n: number) => String(n).padStart(2, "0");

/** The day `n` of Julian March 1500 (the Gregorian name is ten days on: 1 March is 11 March) */
export function day(n: number): DayOut {
  const g = n + 10;
  return {
    jdn: FIRST + n - 1,
    julian: `J1500-03-${two(n)}`,
    gregorian: g <= 31 ? `G1500-03-${two(g)}` : `G1500-04-${two(g - 31)}`,
    weekday: (n - 1) % 7,
    weekday_name: ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"][(n - 1) % 7]!,
  };
}

export const WEEKS: (number | null)[][] = [
  [null, null, null, null, null, null, FIRST],
  ...[1, 8, 15, 22].map((start) => Array.from({ length: 7 }, (_, i) => FIRST + start + i)),
  [FIRST + 29, FIRST + 30, null, null, null, null, null],
];

export const ref = (id: string, label: string, type = "Statement", field = "date"): Ref => ({ id, label, type, field });

export const hit = (id: string, label: string, mark: "stated" | "possible" = "stated", type = "Statement"): Hit => ({
  ref: ref(id, label, type),
  mark,
});

export const feast = (id: string, label: string, via: Characterised["via"] = "rule"): Characterised => ({
  characterisation: { id, label, type: "FeastDay", use: "sarum", rank: null },
  origin: via === "rule" ? "rule" : "manual",
  via,
  ...(via === "month" || via === "year" || via === "span" ? { first: day(1), last: day(31) } : {}),
});

/** The month, with what is on some days */
export function month(on: Record<number, { hits?: Hit[]; characterisations?: Characterised[] }> = {}, more: Partial<MonthReport> = {}): MonthReport {
  return {
    calendar: "julian",
    year: 1500,
    month: 3,
    first: day(1),
    last: day(31),
    previous: [1500, 2],
    next: [1500, 4],
    weeks: WEEKS,
    days: Array.from({ length: 31 }, (_, i) => ({
      day: day(i + 1),
      characterisations: on[i + 1]?.characterisations ?? [],
      hits: on[i + 1]?.hits ?? [],
    })),
    spanning: [],
    characterised_spans: [],
    truncated: false,
    ...more,
  };
}
