import { useApi, useComponent, useTranslations } from "@pangloss/interface-core";
import { useSearchParams } from "@solidjs/router";
import { createMemo, Errored, For, Loading, Show } from "solid-js";
import { getSettings, getYears, isCalendar } from "../api";
import type { CalendarName, CalendarSettings, YearsReport } from "../api";
import { monthHref, monthNames, sayCalendar, yearsHref } from "../days";
import { CalendarConsole, CalendarPage } from "./Chrome";

const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value);

/** The years as a table: each with how many dates meet it and its months, each a link to the month's page */
export function YearsTable(props: { report: YearsReport }) {
  const { t, language } = useTranslations();
  const months = () => monthNames(language(), "short");
  return (
    <table class="w-full border-collapse text-sm" data-testid="calendar-years">
      <thead>
        <tr class="border-b-[0.5px] border-slate-400/70 text-left text-xs font-semibold text-slate-500 uppercase">
          <th class="py-2 pr-4 font-semibold">{t("calendar_year", "Year")}</th>
          <th class="py-2 pr-4 text-right font-semibold">{t("calendar_dated", "Dated")}</th>
          <th class="py-2 font-semibold">{t("calendar_months", "Months")}</th>
        </tr>
      </thead>
      <tbody>
        <For each={props.report.years}>
          {(year) => (
            <tr
              class={["border-b-[0.5px] border-slate-300 hover:bg-slate-50", { "text-slate-400": year.count === 0 }]}
              data-testid="calendar-year"
            >
              <th scope="row" class="py-1.5 pr-4 text-left font-semibold">
                <a href={monthHref(props.report.calendar, year.year, 1)} class="hover:underline">
                  {year.year}
                </a>
              </th>
              <td class="py-1.5 pr-4 text-right tabular-nums">{year.count}</td>
              <td class="py-1.5">
                <div class="flex flex-wrap gap-x-2 gap-y-0.5">
                  <For each={months()}>
                    {(name, index) => (
                      <a
                        href={monthHref(props.report.calendar, year.year, index() + 1)}
                        class="rounded-sm px-1 text-xs hover:bg-slate-200"
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
  const calendar = (): CalendarName => {
    const asked = first(search.calendar);
    return isCalendar(asked) ? asked : props.settings.calendar;
  };
  const span = () =>
    props.settings.first_year !== null && props.settings.last_year !== null
      ? { first: props.settings.first_year, last: props.settings.last_year }
      : undefined;
  const report = createMemo(() => {
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
            <Show when={report()}>{(found) => <YearsTable report={found()} />}</Show>
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
