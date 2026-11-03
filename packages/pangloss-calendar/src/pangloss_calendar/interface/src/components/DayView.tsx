import { getModel, inputClass, ReferenceChip, smallButtonClass, useModels, useTranslations } from "@pangloss/interface-core";
import { createMemo, createSignal, For, Loading, Show } from "solid-js";
import type { CalendarName, Characterised, CharacterisationOut, DayReport, Hit } from "../api";
import { dayHref, itemHref, monthHref, nameOf, sayBetween, sayCalendar, sayDate, sayMonth, weekdayNames } from "../days";
import type { Say } from "../days";
import { Arrows, CHARACTERISATION_MODEL } from "./Chrome";


export interface DayViewProps {
  report: DayReport;
  /** The calendar the page is read in */
  calendar: CalendarName;
  /** Whether someone is logged in: then a characterisation can be attached to the day, and one attached by hand taken away */
  loggedIn: boolean;
  find: (q: string) => Promise<CharacterisationOut[]>;
  onAttach: (characterisation: CharacterisationOut) => void | Promise<void>;
  onDetach: (characterisation: CharacterisationOut) => void | Promise<void>;
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

/** A box to find a characterisation by its label and attach it to the day */
function AttachBox(props: { find: DayViewProps["find"]; onAttach: DayViewProps["onAttach"] }) {
  const { t, modelName } = useTranslations();
  const [q, setQ] = createSignal("");
  const found = createMemo(() => {
    const text = q().trim();
    return text ? props.find(text) : Promise.resolve([] as CharacterisationOut[]);
  });
  const choose = async (characterisation: CharacterisationOut) => {
    await props.onAttach(characterisation);
    setQ("");
  };
  return (
    <div class="mt-3 max-w-md" data-testid="calendar-attach">
      <label class="block text-xs font-semibold text-slate-600 uppercase">
        {t("calendar_attach", "Attach a characterisation")}
        <input
          type="search"
          class={[inputClass, "mt-1 font-normal normal-case"]}
          placeholder={t("calendar_attach_search", "Find one by its name")}
          value={q()}
          onInput={(event) => setQ(event.currentTarget.value)}
        />
      </label>
      <Show when={q().trim() !== ""}>
        <Loading fallback={<p class="mt-1 text-xs text-slate-500">{t("loading", "Loading…")}</p>}>
          <Show
            when={found().length > 0}
            fallback={<p class="mt-1 text-xs text-slate-500">{t("calendar_attach_none", "None match")}</p>}
          >
            <ul class="mt-1 flex flex-col gap-1" aria-label={t("calendar_attach_found", "Characterisations found")}>
              <For each={found()}>
                {(characterisation) => (
                  <li>
                    <button
                      type="button"
                      class="flex w-full cursor-pointer items-center gap-2 rounded-sm px-2 py-1 text-left text-sm hover:bg-slate-100"
                      onClick={() => void choose(characterisation)}
                    >
                      <span>{characterisation.label}</span>
                      <span class="text-xs text-slate-500 uppercase">{modelName(characterisation.type)}</span>
                    </button>
                  </li>
                )}
              </For>
            </ul>
          </Show>
        </Loading>
      </Show>
    </div>
  );
}

/** A date on the day: what it is (its field) and what it is in; one only `possible` says the days it could be on */
function HitRow(props: { hit: Hit; calendar: CalendarName }) {
  const { t, language, fieldName } = useTranslations();
  const range = () =>
    props.hit.first && props.hit.last && props.hit.first.jdn !== props.hit.last.jdn
      ? sayBetween(nameOf(props.hit.first, props.calendar), nameOf(props.hit.last, props.calendar), language(), t)
      : "";
  return (
    <li class="flex min-w-0 items-center gap-3" data-mark={props.hit.mark}>
      <span class="shrink-0 text-xs font-semibold text-slate-500 uppercase">{fieldName(props.hit.ref.type, props.hit.ref.field)}</span>
      <ReferenceChip type={props.hit.ref.type} label={props.hit.ref.label} href={itemHref(props.hit.ref.type, props.hit.ref.id)} />
      <Show when={props.hit.mark === "possible"}>
        <span class="shrink-0 rounded-sm bg-amber-400/25 px-1.5 py-0.5 text-[0.65rem] font-semibold text-amber-950 uppercase">
          {t("calendar_possible", "possible")}
        </span>
        <Show when={range()}>
          <span class="truncate text-xs text-slate-500 italic">{range()}</span>
        </Show>
      </Show>
    </li>
  );
}

/**
 * A day: its name in both calendars and its weekday, the way to the days before and after and up to the month; the
 * feasts and other characterisations on it, with how each comes to be there (and, for someone logged in, a box to
 * attach one, a button to take away one attached by hand, and the way to make a new one); and everything dated on
 * it, `stated` by its date or only `possible`.
 */
export function DayView(props: DayViewProps) {
  const definitions = useModels();
  const { t, language, modelName } = useTranslations();
  const name = () => nameOf(props.report.day, props.calendar);
  const other = (): CalendarName => (props.calendar === "julian" ? "gregorian" : "julian");
  const weekday = () => weekdayNames(language())[props.report.day.weekday] ?? props.report.day.weekday_name;
  const makeable = () => getModel(definitions, CHARACTERISATION_MODEL)?.concreteTypes ?? [];
  return (
    <>
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
        <a href={monthHref(props.calendar, name().year, name().month)} class="hover:underline">
          {sayMonth(name().year, name().month, language(), t)}
        </a>
        <span class="mx-2 text-slate-400">·</span>
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
            <ul class="flex flex-col gap-2">
              <For each={props.report.characterisations}>
                {(on) => (
                  <li class="flex min-w-0 items-center gap-3" data-testid="calendar-characterisation" data-via={on.via}>
                    <ReferenceChip
                      type={on.characterisation.type}
                      label={on.characterisation.label}
                      href={itemHref(on.characterisation.type, on.characterisation.id)}
                    />
                    <Show when={on.characterisation.use}>
                      <span class="text-xs text-slate-500">{on.characterisation.use}</span>
                    </Show>
                    <Show when={on.characterisation.repeated}>
                      <span class="rounded-sm bg-slate-400/25 px-1.5 py-0.5 text-[0.65rem] font-semibold text-slate-700 uppercase">
                        {t("calendar_repeats", "repeats")}
                      </span>
                    </Show>
                    <span class="text-xs text-slate-500 italic">{how(on, props.calendar, language(), t)}</span>
                    <Show when={props.loggedIn && on.origin === "manual" && on.via === "day"}>
                      <button
                        type="button"
                        class={[smallButtonClass, "text-red-800"]}
                        onClick={() => void props.onDetach(on.characterisation)}
                      >
                        {t("calendar_detach", "Detach")}
                      </button>
                    </Show>
                  </li>
                )}
              </For>
            </ul>
          </Show>
          <Show when={props.loggedIn}>
            <AttachBox find={props.find} onAttach={props.onAttach} />
            <Show when={makeable().length > 0}>
              <div class="mt-3 flex flex-wrap gap-2">
                <For each={makeable()}>
                  {(type) => (
                    <a href={`/${type}/new`} class={smallButtonClass}>
                      {t("new_item", "New {type}", { type: modelName(type) })}
                    </a>
                  )}
                </For>
              </div>
            </Show>
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
          <ul class="flex flex-col gap-2">
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
