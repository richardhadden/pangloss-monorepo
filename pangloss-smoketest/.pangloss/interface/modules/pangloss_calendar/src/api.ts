import type { ApiClient } from "@pangloss/interface-core";

// What `/api/calendar` of pangloss-calendar sends and takes (packages/pangloss-calendar/src/pangloss_calendar/service.py)

export type CalendarName = "julian" | "gregorian";

export const CALENDARS: readonly CalendarName[] = ["julian", "gregorian"];

export const isCalendar = (value: unknown): value is CalendarName => value === "julian" || value === "gregorian";

/** A day: its number, and its name in each calendar (`J1500-03-02`, `G1500-03-12`); `weekday` 0 is Sunday */
export interface DayOut {
  jdn: number;
  julian: string;
  gregorian: string;
  weekday: number;
  weekday_name: string;
}

export interface CharacterisationOut {
  id: string;
  label: string;
  type: string;
  easter_offset?: number | null;
  /** The kind of its `when` (`Recurrence`, `JulianExactDate`, `Period`, ...); null for one with no rule */
  kind?: string | null;
  /** Whether it falls again and again (a rule), rather than once */
  repeated?: boolean;
}

export type Via = "rule" | "day" | "month" | "year" | "span";

/** A characterisation on a day (or over a range), and how it comes to be there */
export interface Characterised {
  characterisation: CharacterisationOut;
  origin: "rule" | "manual";
  via: Via;
  /** For one attached to a month, a year or a span: the range it covers */
  first?: DayOut | null;
  last?: DayOut | null;
}

/** A document (or entity) with a date: which, and in which of its fields */
export interface Ref {
  id: string;
  label: string;
  type: string;
  field: string;
}

export type Mark = "stated" | "possible";

export interface Hit {
  ref: Ref;
  mark: Mark;
  /** One day (an exact date, a range, an EDTF date, a day of a repeated event), as against a period over its days */
  single?: boolean;
  /** The range the date states (for a single date: the days it could be on) */
  first?: DayOut | null;
  last?: DayOut | null;
}

export interface DayReport {
  day: DayOut;
  calendar: CalendarName;
  previous: DayOut;
  next: DayOut;
  characterisations: Characterised[];
  hits: Hit[];
  truncated: boolean;
}

export interface MonthDayOut {
  day: DayOut;
  characterisations: Characterised[];
  hits: Hit[];
}

/** A date that states a range too wide to be drawn on each of its days */
export interface Spanning {
  ref: Ref;
  first: DayOut;
  last: DayOut;
}

export interface MonthReport {
  calendar: CalendarName;
  year: number;
  month: number;
  first: DayOut;
  last: DayOut;
  previous: [number, number];
  next: [number, number];
  /** Day numbers, seven to a row, Monday first (null outside the month); the days are in `days` */
  weeks: (number | null)[][];
  days: MonthDayOut[];
  /** Periods wider than `CALENDAR_NARROW_DAYS`: a bar across their days */
  spanning: Spanning[];
  /** Single dates known only within a range that lies in the month: "between these days", a hollow bar */
  between: Spanning[];
  /** Single dates known only within a range that reaches beyond the month: listed, not drawn */
  roughly: Spanning[];
  /** Characterisations attached to the month, its year or a span, not to a day */
  characterised_spans: Characterised[];
  truncated: boolean;
}

export interface CalendarSettings {
  /** The calendar a view opens in */
  calendar: CalendarName;
  /** The span of years (null: not set) */
  first_year: number | null;
  last_year: number | null;
  narrow_days: number;
  extend_margin_years: number;
}

export interface YearCount {
  year: number;
  count: number;
}

export interface YearsReport {
  calendar: CalendarName;
  first_year: number;
  last_year: number;
  years: YearCount[];
  truncated: boolean;
}

export const getSettings = (api: ApiClient): Promise<CalendarSettings> => api.get("/calendar/settings");

/** The years of the span (or from `from` to `to`) with how many dates meet each */
export const getYears = (api: ApiClient, calendar: CalendarName, from?: number, to?: number): Promise<YearsReport> =>
  api.get(`/calendar/years/${calendar}`, { from, to });

export const getMonth = (api: ApiClient, calendar: CalendarName, year: number, month: number): Promise<MonthReport> =>
  api.get(`/calendar/month/${calendar}/${year}/${month}`);

/** A day by its name in a calendar (`J1500-03-02`), read in `calendar` */
export const getDay = (api: ApiClient, ref: string, calendar: CalendarName): Promise<DayReport> =>
  api.get(`/calendar/day/${encodeURIComponent(ref)}`, { calendar });

/** Attach a characterisation to a day by hand (logged in) */
export const attachToDay = (api: ApiClient, characterisation: string, day: string): Promise<{ attached: boolean }> =>
  api.post("/calendar/attach", { characterisation, day });

/** Take away what was attached to the day by hand */
export const detachFromDay = (api: ApiClient, characterisation: string, day: string): Promise<{ removed: number }> =>
  api.post("/calendar/detach", { characterisation, day });
