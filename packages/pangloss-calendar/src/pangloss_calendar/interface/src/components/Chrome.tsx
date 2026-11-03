import { ConsoleButton, getModel, useComponent, useModels, useNavExpanded, useTranslations } from "@pangloss/interface-core";
import { Loading, Show } from "solid-js";
import type { ParentProps } from "solid-js";
import type { CalendarName } from "../api";
import { monthHref, sayCalendar, sayMonth, yearHref, yearsHref } from "../days";
import type { DayName } from "../days";

/** The `main` of a calendar page, inset as the other pages are */
export function CalendarPage(props: ParentProps) {
  const { navPinned } = useNavExpanded();
  return (
    <main class={["w-full py-8", { "px-8": navPinned(), "px-20": !navPinned() }]}>{props.children}</main>
  );
}

/** The abstract entity of pangloss_calendar that feasts and the like are types of */
export const CHARACTERISATION_MODEL = "DateCharacterisation";

/** The types of characterisation the project has that can be made (none if it has no subclass of `DateCharacterisation`) */
export function useCharacterisationTypes(): () => string[] {
  const definitions = useModels();
  return () => getModel(definitions, CHARACTERISATION_MODEL)?.concreteTypes ?? [];
}

/** What a new characterisation made on a day starts with: that day, as its `when` (it can be made a rule in the form) */
export function onTheDay(name: DayName): () => Record<string, unknown> {
  return () => ({
    when: { type: "ExactDate", calendar: name.calendar, year: name.year, month: name.month, day: name.day },
  });
}

/**
 * The console of a calendar page: "Calendar" and the page's `label` on the left; on the right the way to the years,
 * and one button with the calendar the page is read in, which shows the same page in the other. `hrefOf` gives the same
 * page in a calendar (it may read what the page is still loading: the button waits for it, the rest of the console does
 * not).
 */
export function CalendarConsole(props: {
  label?: string;
  calendar: CalendarName;
  hrefOf: (calendar: CalendarName) => string | undefined;
}) {
  const Console = useComponent("Console");
  const { t } = useTranslations();
  const other = (): CalendarName => (props.calendar === "julian" ? "gregorian" : "julian");
  const toggle = (hrefOf: (calendar: CalendarName) => string | undefined) => (
    <ConsoleButton label={sayCalendar(props.calendar, t)} href={hrefOf(other())} disabled={hrefOf(other()) === undefined} text>
      {/* (two arrows: the button goes to the other calendar) */}
      <svg
        viewBox="0 0 24 24"
        class="size-4 select-none fill-none stroke-current stroke-2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="M4 8h14l-3-3M20 16H6l3 3" />
      </svg>
    </ConsoleButton>
  );
  return (
    <Console type={t("calendar", "Calendar")} label={props.label}>
      <ConsoleButton label={t("calendar_years", "Years")} href={yearsHref(props.calendar)} text>
        <svg
          viewBox="0 0 24 24"
          class="size-4 select-none fill-none stroke-current stroke-2"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <rect x="3" y="5" width="18" height="16" rx="1" />
          <path d="M3 10h18M8 3v4M16 3v4" />
        </svg>
      </ConsoleButton>
      <Loading fallback={toggle(() => undefined)}>{toggle(props.hrefOf)}</Loading>
    </Console>
  );
}

/** Where a page is: the year (a link to it in the list of years), and the month, before the page's own heading */
export function Breadcrumbs(props: { calendar: CalendarName; year: number; month?: number }) {
  const { t, language } = useTranslations();
  const link = "hover:underline";
  return (
    <nav aria-label={t("calendar_where", "Where in the calendar")} class="mb-2 flex items-center gap-2 text-sm text-slate-600">
      <a href={yearHref(props.calendar, props.year)} class={link}>
        {props.year}
      </a>
      <Show when={props.month}>
        {(month) => (
          <>
            <span class="text-slate-400" aria-hidden="true">
              ›
            </span>
            <a href={monthHref(props.calendar, props.year, month())} class={link}>
              {sayMonth(props.year, month(), language(), t)}
            </a>
          </>
        )}
      </Show>
    </nav>
  );
}

/** The buttons that step back and forward (a month, a day): links, or disabled while where they go is not known */
export function Arrows(props: { previous?: string; next?: string; previousLabel: string; nextLabel: string }) {
  const classes = (href: string | undefined) => [
    "flex size-8 shrink-0 items-center justify-center rounded-sm border-[0.5px] border-slate-400/70 bg-white select-none",
    { "cursor-pointer": href !== undefined, "hover:bg-slate-100": href !== undefined, "opacity-40": href === undefined },
  ];
  return (
    <div class="flex items-center gap-1">
      <a href={props.previous} aria-label={props.previousLabel} title={props.previousLabel} class={classes(props.previous)}>
        <svg viewBox="0 0 24 24" class="size-4 fill-none stroke-current stroke-2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M15 5l-7 7 7 7" />
        </svg>
      </a>
      <a href={props.next} aria-label={props.nextLabel} title={props.nextLabel} class={classes(props.next)}>
        <svg viewBox="0 0 24 24" class="size-4 fill-none stroke-current stroke-2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M9 5l7 7-7 7" />
        </svg>
      </a>
    </div>
  );
}

/** What a page says when its address is not a day or a month of the calendar */
export function BadAddress() {
  const { t } = useTranslations();
  return (
    <CalendarPage>
      <p role="alert" class="text-slate-700">
        {t("calendar_bad_address", "That is not a day of the calendar: the address is /calendar/julian/1500/3/2 (or gregorian).")}
      </p>
    </CalendarPage>
  );
}
