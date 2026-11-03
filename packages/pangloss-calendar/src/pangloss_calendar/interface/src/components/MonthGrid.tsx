import { getModel, kindTint, useModels, useTranslations } from "@pangloss/interface-core";
import { For, Show } from "solid-js";
import type { CalendarName, Characterised, Hit, MonthDayOut, MonthReport, Spanning } from "../api";
import { dayHref, itemHref, nameOf, sayDate, weekHeadings } from "../days";
import { weekBars, weekStart } from "../lanes";
import type { Bar, Ranged } from "../lanes";

/** How many dates a day of the grid shows before "+N more" (the day's page has them all) */
export const HITS_SHOWN = 3;

/** The tint of what a date is in: by the kind of its model, or the colour the model chose */
function useTint() {
  const definitions = useModels();
  return (type: string) => {
    const model = getModel(definitions, type);
    return kindTint(model?.kind, model?.interfaceMeta?.colour);
  };
}

/** A date on a day: a small chip, a link to what it is in; one that is only `possible` is fainter and dashed */
function HitChip(props: { hit: Hit }) {
  const tint = useTint();
  const possible = () => props.hit.mark === "possible";
  return (
    <a
      href={itemHref(props.hit.ref.type, props.hit.ref.id)}
      title={props.hit.ref.label}
      data-mark={props.hit.mark}
      class={[
        "block min-w-0 truncate rounded-sm px-1 text-[0.7rem] leading-5",
        tint(props.hit.ref.type),
        { "opacity-70": possible(), border: possible(), "border-dashed": possible(), "border-slate-500/60": possible() },
      ]}
    >
      {props.hit.ref.label}
    </a>
  );
}

/** A feast or other characterisation on a day: its name, a link to it */
function CharacterisationLine(props: { on: Characterised }) {
  return (
    <a
      href={itemHref(props.on.characterisation.type, props.on.characterisation.id)}
      title={props.on.characterisation.label}
      class="block min-w-0 truncate text-[0.7rem] leading-5 text-amber-800 italic hover:underline"
    >
      {props.on.characterisation.label}
    </a>
  );
}

/** What is on one day of the month, under its number: the characterisations, then up to `HITS_SHOWN` dates and "+N more" */
function DayContents(props: { entry: MonthDayOut; calendar: CalendarName }) {
  const { t } = useTranslations();
  const hidden = () => Math.max(0, props.entry.hits.length - HITS_SHOWN);
  return (
    <>
      <For each={props.entry.characterisations}>{(on) => <CharacterisationLine on={on} />}</For>
      <For each={props.entry.hits.slice(0, HITS_SHOWN)}>{(hit) => <HitChip hit={hit} />}</For>
      <Show when={hidden() > 0}>
        <a
          href={dayHref(nameOf(props.entry.day, props.calendar))}
          class="block px-1 text-[0.7rem] leading-5 font-semibold text-slate-500 hover:underline"
        >
          {t("calendar_more", "+{count} more", { count: hidden() })}
        </a>
      </Show>
    </>
  );
}

/** A bar across the days a date covers in a week: open at the end where it goes on into another week */
function SpanBar(props: { bar: Bar<Spanning> }) {
  const tint = useTint();
  return (
    <a
      href={itemHref(props.bar.item.ref.type, props.bar.item.ref.id)}
      title={props.bar.item.ref.label}
      data-testid="calendar-bar"
      data-lane={props.bar.lane}
      style={{
        "grid-row": String(props.bar.lane + 2),
        "grid-column": `${props.bar.start + 1} / span ${props.bar.end - props.bar.start + 1}`,
      }}
      class={[
        "mb-0.5 min-w-0 truncate px-1.5 text-[0.7rem] leading-5 font-medium",
        tint(props.bar.item.ref.type),
        {
          "ml-0.5": props.bar.startsHere,
          "rounded-l-sm": props.bar.startsHere,
          "mr-0.5": props.bar.endsHere,
          "rounded-r-sm": props.bar.endsHere,
        },
      ]}
    >
      {props.bar.item.ref.label}
    </a>
  );
}

/**
 * A week of the grid: seven columns. Behind, the cells (a rule between them; shaded outside the month). In front, a grid
 * of the same columns with the day numbers in its first row, a row for each lane of bars, and what is on each day last.
 */
function WeekRow(props: { week: (number | null)[]; report: MonthReport; ranges: Ranged<Spanning>[] }) {
  const { t, language } = useTranslations();
  const bars = () => weekBars(props.ranges, weekStart(props.week));
  const lanes = () => bars().reduce((most, bar) => Math.max(most, bar.lane + 1), 0);
  const entry = (jdn: number) => props.report.days[jdn - props.report.first.jdn];
  const name = (jdn: number) => nameOf(entry(jdn)!.day, props.report.calendar);
  return (
    <div class="relative border-t border-slate-300" data-testid="calendar-week">
      <div aria-hidden="true" class="pointer-events-none absolute inset-0 grid grid-cols-7">
        <For each={props.week}>
          {(jdn) => (
            <div class={["border-l border-slate-300 first:border-l-0", { "bg-slate-100/70": jdn === null }]} />
          )}
        </For>
      </div>
      <div class="relative grid grid-cols-7">
        <For each={props.week}>
          {(jdn, index) => (
            <div style={{ "grid-row": "1", "grid-column": String(index() + 1) }} class="h-7 px-1.5 pt-1">
              <Show when={jdn !== null && entry(jdn!)}>
                <a
                  href={dayHref(name(jdn!))}
                  aria-label={sayDate(name(jdn!), language(), t)}
                  class="inline-flex size-5 items-center justify-center rounded-full text-xs font-semibold text-slate-700 hover:bg-slate-200"
                >
                  {name(jdn!).day}
                </a>
              </Show>
            </div>
          )}
        </For>
        <For each={bars()}>{(bar) => <SpanBar bar={bar} />}</For>
        <For each={props.week}>
          {(jdn, index) => (
            <div
              style={{ "grid-row": String(lanes() + 2), "grid-column": String(index() + 1) }}
              class="min-h-14 min-w-0 px-1 pb-1"
            >
              <Show when={jdn !== null && entry(jdn!)}>
                {(found) => <DayContents entry={found()} calendar={props.report.calendar} />}
              </Show>
            </div>
          )}
        </For>
      </div>
    </div>
  );
}

/**
 * A month as a calendar page: the weekdays across the top (Monday first), a row for each week. A date that states a
 * day is a chip on it (one that states a few days, on each of them, fainter: it was on one of them); a date that
 * states a longer range is a bar across the days it covers (`spanning`); feasts and the like are named on their days.
 */
export function MonthGrid(props: { report: MonthReport }) {
  const { language } = useTranslations();
  const ranges = (): Ranged<Spanning>[] =>
    props.report.spanning.map((item) => ({
      item,
      first: Math.max(item.first.jdn, props.report.first.jdn),
      last: Math.min(item.last.jdn, props.report.last.jdn),
      trueFirst: item.first.jdn,
      trueLast: item.last.jdn,
    }));
  return (
    <div class="overflow-hidden rounded-sm border border-slate-300 bg-white" data-testid="calendar-month">
      <div class="grid grid-cols-7 bg-slate-100/80 text-xs font-semibold text-slate-500 uppercase">
        <For each={weekHeadings(language())}>
          {(day) => <div class="border-l border-slate-300 px-2 py-1.5 first:border-l-0">{day}</div>}
        </For>
      </div>
      <For each={props.report.weeks}>{(week) => <WeekRow week={week} report={props.report} ranges={ranges()} />}</For>
    </div>
  );
}
