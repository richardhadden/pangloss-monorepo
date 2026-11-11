import { tableCellClass, tableClass, tableHeadCellClass, tableHeadRowClass, useApi, useComponent, useSessionKey, useTranslations, firstParam } from "@pangloss/interface-core";
import { useLocation, useSearchParams } from "@solidjs/router";
import { createEffect, createMemo, Errored, For, Loading, Show } from "solid-js";
import { getSettings, getYears, isCalendar } from "../api";
import type { CalendarName, CalendarSettings, YearsReport } from "../api";
import { monthHref, monthNames, sayCalendar, yearsHref } from "../days";
import { CalendarConsole, CalendarPage } from "./Chrome";


/**
 * The years as a table: each with its months (links to their pages) and, at the end, how many dates meet it. The year
 * gone to (`current`, from a link `#year-1500` of a day or a month) is marked, and scrolled to.
 */
export function YearsTable(props: { report: YearsReport; current?: number }) {
  const { t, language } = useTranslations();
  const months = () => monthNames(language(), "short");
  createEffect(
    () => props.current,
    (year) => {
      if (year !== undefined) document.getElementById(`year-${year}`)?.scrollIntoView({ block: "center" });
    },
  );
  return (
    <table class="w-full border-collapse text-sm" data-testid="calendar-years">
      <thead>
        <tr class={tableHeadRowClass}>
          <th class={tableHeadCellClass}>{t("calendar_year", "Year")}</th>
          <th class={tableHeadCellClass}>{t("calendar_months", "Months")}</th>
          <th class={[tableHeadCellClass, "w-32 text-left"]}>{t("calendar_events", "Events")}</th>
        </tr>
      </thead>
      <tbody>
        <For each={props.report.years}>
          {(year) => (
            <tr
              id={`year-${year.year}`}
              class={[
                "scroll-mt-24 border-b-[0.5px] border-slate-500/30",
                {
                  "text-slate-400": year.count === 0,
                  "bg-amber-100/70": props.current === year.year,
                  "hover:bg-slate-50": props.current !== year.year,
                },
              ]}
              data-testid="calendar-year"
              aria-current={props.current === year.year ? "true" : undefined}
            >
              <th scope="row" class={[tableCellClass, "text-left font-semibold"]}>
                <a href={monthHref(props.report.calendar, year.year, 1)} class="hover:underline">
                  {year.year}
                </a>
              </th>
              <td class={tableCellClass}>
                <div class="flex flex-wrap gap-x-2 gap-y-0.5">
                  <For each={months()}>
                    {(name, index) => (
                      <a
                        href={monthHref(props.report.calendar, year.year, index() + 1)}
                        class="rounded-xs px-1 text-xs hover:bg-slate-200"
                        aria-label={t("calendar_month_year", "{month} {year}", {
                          month: monthNames(language())[index()] ?? name,
                          year: year.year,
                        })}
                      >
                        {name}
                      </a>
                    )}
                  </For>
                </div>
              </td>
              {/* (how many dated things meet the year: the number in a circle, in a slot of its own so that the circles of
                   every row line up, then the word, left-aligned after it, whether it is "event" or "events") */}
              <td class={[tableCellClass, "w-32 whitespace-nowrap"]} data-testid="calendar-year-count">
                <span class="flex items-center">
                <span class="flex w-9 shrink-0 justify-center">
                <span
                  class={[
                    "inline-flex h-6 min-w-6 items-center justify-center rounded-full px-1.5 text-xs font-semibold tabular-nums",
                    { "bg-sky-600": year.count > 0, "text-white": year.count > 0, "bg-slate-200": year.count === 0 },
                  ]}
                >
                  {year.count}
                </span>
                </span>
                <span class="text-xs text-slate-500">
                  <Show when={year.count === 1} fallback={t("calendar_events_word", "events")}>
                    {t("calendar_event_word", "event")}
                  </Show>
                </span>
                </span>
              </td>
            </tr>
          )}
        </For>
      </tbody>
    </table>
  );
}

function YearsOf(props: { settings: CalendarSettings }) {
  const api = useApi();
  const ErrorMessage = useComponent("ErrorMessage");
  const { t } = useTranslations();
  const [search] = useSearchParams();
  const location = useLocation();
  // (the year a link went to: `#year-1500`)
  const current = () => {
    const found = /^#year-(-?\d+)$/.exec(location.hash);
    return found ? Number(found[1]) : undefined;
  };
  const calendar = (): CalendarName => {
    const asked = firstParam(search.calendar);
    return isCalendar(asked) ? asked : props.settings.calendar;
  };
  const span = () =>
    props.settings.first_year !== null && props.settings.last_year !== null
      ? { first: props.settings.first_year, last: props.settings.last_year }
      : undefined;
  // (asked again when someone logs in or out: what is dated may be more, or less)
  const session = useSessionKey();
  const report = createMemo(() => {
    session();
    const years = span();
    return years ? getYears(api, calendar(), years.first, years.last) : undefined;
  });
  return (
    <CalendarPage>
      <CalendarConsole calendar={calendar()} hrefOf={yearsHref} />
      <h1 class="mb-6 border-b-[0.5px] border-slate-400/70 pt-1 pb-2 text-2xl font-semibold">
        {t("calendar_years", "Years")}
        <span class="ml-3 text-base font-normal text-slate-500">{sayCalendar(calendar(), t)}</span>
      </h1>
      <Show
        when={span()}
        fallback={
          <p class="text-slate-700">
            {t(
              "calendar_no_span",
              "Set CALENDAR_FIRST_YEAR and CALENDAR_LAST_YEAR in the settings of the project to list its years.",
            )}
          </p>
        }
      >
        <Errored fallback={(error) => <ErrorMessage error={error()} />}>
          <Loading fallback={<p>{t("loading", "Loading…")}</p>}>
            <Show when={report()}>{(found) => <YearsTable report={found()} current={current()} />}</Show>
            <Show when={report()?.truncated}>
              <p class="mt-4 text-xs font-semibold text-red-700 uppercase">
                {t("calendar_truncated", "More dates were found than are shown")}
              </p>
            </Show>
          </Loading>
        </Errored>
      </Show>
    </CalendarPage>
  );
}

/** The years of the project's calendar: /calendar (`?calendar=gregorian` to read them in the other calendar) */
export default function YearsPage() {
  const api = useApi();
  const ErrorMessage = useComponent("ErrorMessage");
  const { t } = useTranslations();
  const settings = createMemo(() => getSettings(api));
  return (
    <Errored fallback={(error) => <CalendarPage><ErrorMessage error={error()} /></CalendarPage>}>
      <Loading fallback={<CalendarPage><p>{t("loading", "Loading…")}</p></CalendarPage>}>
        <YearsOf settings={settings()} />
      </Loading>
    </Errored>
  );
}
