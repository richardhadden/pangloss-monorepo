import { useApi, useComponent, useTranslations } from "@pangloss/interface-core";
import { createMemo, Errored, For, Loading, Show } from "solid-js";
import { getMonth } from "../api";
import type { CalendarName, Characterised, MonthReport } from "../api";
import {
  itemHref,
  monthFromParams,
  monthHref,
  nameOf,
  nextMonth,
  previousMonth,
  sayBetween,
  sayCalendar,
  sayDate,
  sayMonth,
  sayRef,
} from "../days";
import { Arrows, BadAddress, CalendarConsole, CalendarPage } from "./Chrome";
import { MonthGrid } from "./MonthGrid";

/**
 * Under the grid: the dates known only roughly, within a range that reaches beyond the month (a birth "in 735": said as
 * "between these days", not drawn on every day); the characterisations attached to the month, its year or a span (not
 * to a day); and a note if the month was cut
 */
export function MonthFoot(props: { report: MonthReport }) {
  const { t, language, fieldName } = useTranslations();
  const range = (on: Characterised) =>
    on.first && on.last
      ? `${sayDate(nameOf(on.first, props.report.calendar), language(), t)} – ${sayDate(nameOf(on.last, props.report.calendar), language(), t)}`
      : "";
  return (
    <>
      <Show when={props.report.roughly.length > 0}>
        <section class="mt-6" aria-labelledby="calendar-roughly">
          <h2 id="calendar-roughly" class="mb-2 text-xs font-semibold text-slate-500 uppercase">
            {t("calendar_roughly", "Sometime in or around this month")}
          </h2>
          <ul class="flex flex-col gap-1 text-sm">
            <For each={props.report.roughly}>
              {(item) => (
                <li class="flex min-w-0 items-center gap-3" data-testid="calendar-roughly">
                  <a href={itemHref(item.ref.type, item.ref.id)} class="truncate hover:underline">
                    {sayRef(item.ref, fieldName)}
                  </a>
                  <span class="shrink-0 text-xs text-slate-500 italic">
                    {sayBetween(nameOf(item.first, props.report.calendar), nameOf(item.last, props.report.calendar), language(), t)}
                  </span>
                </li>
              )}
            </For>
          </ul>
        </section>
      </Show>
      <Show when={props.report.characterised_spans.length > 0}>
        <section class="mt-6" aria-labelledby="calendar-over-month">
          <h2 id="calendar-over-month" class="mb-2 text-xs font-semibold text-slate-500 uppercase">
            {t("calendar_over_month", "Over the month")}
          </h2>
          <ul class="flex flex-col gap-1 text-sm">
            <For each={props.report.characterised_spans}>
              {(on) => (
                <li class="flex items-center gap-3">
                  <a
                    href={itemHref(on.characterisation.type, on.characterisation.id)}
                    class="text-amber-800 italic hover:underline"
                  >
                    {on.characterisation.label}
                  </a>
                  <span class="text-xs text-slate-500">{range(on)}</span>
                </li>
              )}
            </For>
          </ul>
        </section>
      </Show>
      <Show when={props.report.truncated}>
        <p class="mt-4 text-xs font-semibold text-red-700 uppercase">
          {t("calendar_truncated", "More dates were found than are shown")}
        </p>
      </Show>
    </>
  );
}

function MonthOf(props: { calendar: CalendarName; year: number; month: number }) {
  const api = useApi();
  const ErrorMessage = useComponent("ErrorMessage");
  const { t, language } = useTranslations();
  const report = createMemo(() => getMonth(api, props.calendar, props.year, props.month));
  const title = () => sayMonth(props.year, props.month, language(), t);
  const previous = () => previousMonth(props.year, props.month);
  const next = () => nextMonth(props.year, props.month);
  return (
    <CalendarPage>
      <CalendarConsole
        calendar={props.calendar}
        label={title()}
        hrefOf={(calendar) => monthHref(calendar, props.year, props.month)}
      />
      <div class="mb-4 flex items-center gap-4">
        <Arrows
          previous={monthHref(props.calendar, ...previous())}
          next={monthHref(props.calendar, ...next())}
          previousLabel={t("calendar_previous_month", "Previous month")}
          nextLabel={t("calendar_next_month", "Next month")}
        />
        <h1 class="text-2xl font-semibold">
          {title()}
          <span class="ml-3 text-base font-normal text-slate-500">{sayCalendar(props.calendar, t)}</span>
        </h1>
      </div>
      <Errored fallback={(error) => <ErrorMessage error={error()} />}>
        <Loading fallback={<p>{t("loading", "Loading…")}</p>}>
          <MonthGrid report={report()} />
          <MonthFoot report={report()} />
        </Loading>
      </Errored>
    </CalendarPage>
  );
}

/** A month of the calendar: /calendar/julian/1500/3 */
export default function MonthPage(props: { params: Record<string, string | undefined> }) {
  const asked = () => monthFromParams(props.params);
  return (
    <Show when={asked()} fallback={<BadAddress />}>
      {(month) => <MonthOf calendar={month().calendar} year={month().year} month={month().month} />}
    </Show>
  );
}
