import { NewEntityDialog, ReferenceChip, useApi, useComponent, userIsLoggedIn, useSessionKey, useTranslations } from "@pangloss/interface-core";
import { createMemo, createSignal, Errored, For, Loading, Show } from "solid-js";
import { getMonth } from "../api";
import type { CalendarName, Characterised, DayOut, MonthReport } from "../api";
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
} from "../days";
import {
  Arrows,
  BadAddress,
  Breadcrumbs,
  CalendarConsole,
  CalendarPage,
  useCharacterisationTypes,
  useDatedDocumentTypes,
  useOnTheDayFill,
} from "./Chrome";
import { Covering } from "./Covering";
import { MonthGrid } from "./MonthGrid";

/**
 * Under the grid: the dates known only roughly, within a range that reaches beyond the month (a birth "in 735": said as
 * "between these days", not drawn on every day); the characterisations attached to the month, its year or a span (not
 * to a day); how many long periods run over the whole month, which are read when asked for (`Covering`); and a note
 * if the month was cut
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
          <ul class="grid grid-cols-[max-content_fit-content(26rem)_minmax(0,1fr)] gap-x-4 gap-y-2">
            <For each={props.report.roughly}>
              {(item) => (
                <li class="col-span-3 grid min-w-0 grid-cols-subgrid items-center" data-testid="calendar-roughly">
                  <span class="text-xs font-semibold text-slate-500 uppercase">
                    {fieldName(item.ref.type, item.ref.field)}
                  </span>
                  <span class="flex min-w-0">
                    <ReferenceChip type={item.ref.type} label={item.ref.label} href={itemHref(item.ref.type, item.ref.id)} />
                  </span>
                  <span class="truncate text-xs text-slate-500 italic">
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
          <ul class="grid grid-cols-[fit-content(26rem)_minmax(0,1fr)] gap-x-4 gap-y-2">
            <For each={props.report.characterised_spans}>
              {(on) => (
                <li class="col-span-2 grid min-w-0 grid-cols-subgrid items-center">
                  <span class="flex min-w-0">
                    <ReferenceChip
                      type={on.characterisation.type}
                      label={on.characterisation.label}
                      href={itemHref(on.characterisation.type, on.characterisation.id)}
                    />
                  </span>
                  <span class="truncate text-xs text-slate-500">{range(on)}</span>
                </li>
              )}
            </For>
          </ul>
        </section>
      </Show>
      <Covering
        count={props.report.covering ?? 0}
        first={props.report.first}
        last={props.report.last}
        calendar={props.report.calendar}
        heading={t("calendar_covering_month", "Long periods over the whole month")}
      />
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
  const loggedIn = createMemo(() => userIsLoggedIn());
  const characterisations = useCharacterisationTypes();
  const documents = useDatedDocumentTypes();
  // (what a day's + makes: a feast or the like, or a document with a date that can be the day, a factoid)
  const types = () => [...characterisations(), ...documents()];
  const onTheDay = useOnTheDayFill();
  // (the day something is being made on, from its +; the month is read again when it is made)
  const [adding, setAdding] = createSignal<DayOut>();
  const [version, setVersion] = createSignal(0);
  // (and when someone logs in or out: what is dated may be more, or less)
  const session = useSessionKey();
  const report = createMemo(() => {
    version();
    session();
    return getMonth(api, props.calendar, props.year, props.month);
  });
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
      <Breadcrumbs calendar={props.calendar} year={props.year} />
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
          <MonthGrid report={report()} onAdd={loggedIn() && types().length > 0 ? setAdding : undefined} />
          <MonthFoot report={report()} />
        </Loading>
      </Errored>
      <Show when={adding()}>
        {(day) => (
          <NewEntityDialog
            types={types()}
            fill={onTheDay(day(), props.calendar)}
            onClose={() => setAdding(undefined)}
            onCreated={() => {
              setAdding(undefined);
              setVersion((n) => n + 1);
            }}
          />
        )}
      </Show>
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
