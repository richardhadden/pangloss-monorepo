import { PickOrCreate, ReferenceChip, useTranslations } from "@pangloss/interface-core";
import { For, Show } from "solid-js";
import type { CalendarName, Characterised, CharacterisationOut, DayReport, Hit } from "../api";
import { dayHref, itemHref, nameOf, sayBetween, sayCalendar, sayDate, weekdayNames } from "../days";
import type { Say } from "../days";
import { Arrows, Breadcrumbs, onTheDay, useCharacterisationTypes } from "./Chrome";


export interface DayViewProps {
  report: DayReport;
  /** The calendar the page is read in */
  calendar: CalendarName;
  /**
   * Whether someone is logged in: then a characterisation can be found and attached to the day, or made (starting on
   * the day), and one attached by hand taken away
   */
  loggedIn: boolean;
  onAttach: (characterisation: { id: string; label: string }) => void | Promise<void>;
  onDetach: (characterisation: CharacterisationOut) => void | Promise<void>;
  /** A new characterisation was made (on the day, unless its form was changed): the day is to be read again */
  onCreated: () => void;
}

/** How a characterisation comes to be on the day, in words */
function how(on: Characterised, calendar: CalendarName, language: string, t: Say): string {
  switch (on.via) {
    case "rule":
      return t("calendar_by_rule", "by rule");
    case "day":
      return t("calendar_attached_day", "attached to this day");
    case "month":
      return t("calendar_attached_month", "attached to the month");
    case "year":
      return t("calendar_attached_year", "attached to the year");
    case "span":
      return t("calendar_attached_span", "attached to {first} – {last}", {
        first: on.first ? sayDate(nameOf(on.first, calendar), language, t) : "",
        last: on.last ? sayDate(nameOf(on.last, calendar), language, t) : "",
      });
  }
}

/** A date on the day: what it is (its field) and what it is in; one only `possible` says the days it could be on */
function HitRow(props: { hit: Hit; calendar: CalendarName }) {
  const { t, language, fieldName } = useTranslations();
  const range = () =>
    props.hit.first && props.hit.last && props.hit.first.jdn !== props.hit.last.jdn
      ? sayBetween(nameOf(props.hit.first, props.calendar), nameOf(props.hit.last, props.calendar), language(), t)
      : "";
  return (
    // (a row of the list's grid: the field, the chip, then whether it is only possible and on which days)
    <li class="col-span-3 grid min-w-0 grid-cols-subgrid items-center" data-mark={props.hit.mark}>
      <span class="text-xs font-semibold text-slate-500 uppercase">{fieldName(props.hit.ref.type, props.hit.ref.field)}</span>
      <span class="flex min-w-0">
        <ReferenceChip type={props.hit.ref.type} label={props.hit.ref.label} href={itemHref(props.hit.ref.type, props.hit.ref.id)} />
      </span>
      <span class="flex min-w-0 items-center gap-3">
        <Show when={props.hit.mark === "possible"}>
          <span class="shrink-0 rounded-sm bg-amber-400/25 px-1.5 py-0.5 text-[0.65rem] font-semibold text-amber-950 uppercase">
            {t("calendar_possible", "possible")}
          </span>
          <Show when={range()}>
            <span class="truncate text-xs text-slate-500 italic">{range()}</span>
          </Show>
        </Show>
      </span>
    </li>
  );
}

/**
 * A day: where it is (its year and month, links), its weekday and its name in both calendars, the way to the days
 * before and after; the feasts and other characterisations on it as chips, with how each comes to be there (for someone
 * logged in, one attached by hand has a remove button, and under them is the search that finds one to attach, with a +
 * that makes a new one starting on the day, as in a form); and everything dated on it, `stated` by its date or only
 * `possible`.
 */
export function DayView(props: DayViewProps) {
  const { t, language } = useTranslations();
  const types = useCharacterisationTypes();
  const name = () => nameOf(props.report.day, props.calendar);
  const other = (): CalendarName => (props.calendar === "julian" ? "gregorian" : "julian");
  const weekday = () => weekdayNames(language())[props.report.day.weekday] ?? props.report.day.weekday_name;
  return (
    <>
      <Breadcrumbs calendar={props.calendar} year={name().year} month={name().month} />
      <div class="mb-1 flex items-center gap-4">
        <Arrows
          previous={dayHref(nameOf(props.report.previous, props.calendar))}
          next={dayHref(nameOf(props.report.next, props.calendar))}
          previousLabel={t("calendar_previous_day", "Previous day")}
          nextLabel={t("calendar_next_day", "Next day")}
        />
        <h1 class="text-2xl font-semibold">
          {t("calendar_weekday_date", "{weekday} {date}", { weekday: weekday(), date: sayDate(name(), language(), t) })}
          <span class="ml-3 text-base font-normal text-slate-500">{sayCalendar(props.calendar, t)}</span>
        </h1>
      </div>
      <p class="mb-6 text-sm text-slate-600">
        <a href={dayHref(nameOf(props.report.day, other()))} class="hover:underline" data-testid="calendar-other-name">
          {t("calendar_other_name", "{date} ({calendar})", {
            date: sayDate(nameOf(props.report.day, other()), language(), t),
            calendar: sayCalendar(other(), t),
          })}
        </a>
      </p>
      <Show when={props.report.characterisations.length > 0 || props.loggedIn}>
        <section class="mb-8" aria-labelledby="calendar-characterisations">
          <h2 id="calendar-characterisations" class="mb-2 border-b-[0.5px] border-slate-400/70 pb-1 text-xs font-semibold text-slate-500 uppercase">
            {t("calendar_characterisations", "Feasts and characterisations")}
          </h2>
          <Show
            when={props.report.characterisations.length > 0}
            fallback={<p class="text-sm text-slate-500">{t("calendar_no_characterisations", "None on this day")}</p>}
          >
            <ul class="grid grid-cols-[fit-content(26rem)_minmax(0,1fr)] gap-x-4 gap-y-2">
              <For each={props.report.characterisations}>
                {(on) => (
                  <li class="col-span-2 grid min-w-0 grid-cols-subgrid items-center" data-testid="calendar-characterisation" data-via={on.via}>
                    <span class="flex min-w-0">
                    <ReferenceChip
                      type={on.characterisation.type}
                      label={on.characterisation.label}
                      href={itemHref(on.characterisation.type, on.characterisation.id)}
                      // (one attached to the day by hand can be taken away, as a chip in a form is)
                      onRemove={
                        props.loggedIn && on.origin === "manual" && on.via === "day"
                          ? () => void props.onDetach(on.characterisation)
                          : undefined
                      }
                      removeLabel={t("calendar_detach", "Detach {label}", { label: on.characterisation.label })}
                    />
                    </span>
                    <span class="flex min-w-0 items-center gap-3">
                      <span class="text-xs text-slate-500 italic">{how(on, props.calendar, language(), t)}</span>
                      <Show when={on.characterisation.repeated}>
                        <span class="shrink-0 rounded-sm bg-slate-400/25 px-1.5 py-0.5 text-[0.65rem] font-semibold text-slate-700 uppercase">
                          {t("calendar_repeats", "repeats")}
                        </span>
                      </Show>
                    </span>
                  </li>
                )}
              </For>
            </ul>
          </Show>
          <Show when={props.loggedIn && types().length > 0}>
            <div class="mt-3 max-w-xl" data-testid="calendar-attach">
              <PickOrCreate
                types={types()}
                placeholder={t("calendar_attach_placeholder", "Find one to attach to this day, or + to make one")}
                initial={onTheDay(name())}
                onPick={(found) => void props.onAttach(found)}
                onCreated={() => props.onCreated()}
              />
            </div>
          </Show>
        </section>
      </Show>
      <section aria-labelledby="calendar-on-day">
        <h2 id="calendar-on-day" class="mb-2 border-b-[0.5px] border-slate-400/70 pb-1 text-xs font-semibold text-slate-500 uppercase">
          {t("calendar_on_this_day", "On this day")}
        </h2>
        <Show
          when={props.report.hits.length > 0}
          fallback={<p class="text-sm text-slate-500">{t("calendar_nothing_on_day", "Nothing is dated on this day")}</p>}
        >
          <ul class="grid grid-cols-[max-content_fit-content(26rem)_minmax(0,1fr)] gap-x-4 gap-y-2">
            <For each={props.report.hits}>{(hit) => <HitRow hit={hit} calendar={props.calendar} />}</For>
          </ul>
        </Show>
        <Show when={props.report.truncated}>
          <p class="mt-4 text-xs font-semibold text-red-700 uppercase">
            {t("calendar_truncated", "More dates were found than are shown")}
          </p>
        </Show>
      </section>
    </>
  );
}
