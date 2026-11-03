import { getModel, kindTint, useModels, useTranslations } from "@pangloss/interface-core";
import { For, Show } from "solid-js";
import type { CalendarName, Characterised, DayOut, Hit, MonthDayOut, MonthReport, Spanning } from "../api";
import { dayHref, itemHref, nameOf, sayBetween, sayDate, sayRef, weekHeadings } from "../days";
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

/** A date on a day: a small chip, a link to what it is in, named by its field ("Born · Alcuin of York") */
function HitChip(props: { hit: Hit }) {
  const tint = useTint();
  const { fieldName } = useTranslations();
  return (
    <a
      href={itemHref(props.hit.ref.type, props.hit.ref.id)}
      title={sayRef(props.hit.ref, fieldName)}
      data-mark={props.hit.mark}
      class={["block min-w-0 truncate rounded-sm px-1 text-[0.7rem] leading-5", tint(props.hit.ref.type)]}
    >
      <span class="font-semibold uppercase opacity-70">{fieldName(props.hit.ref.type, props.hit.ref.field)}</span>
      <span class="opacity-50"> · </span>
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

/** What a bar is for: a period over its days (filled), or one day somewhere between them (hollow, dashed) */
type BarItem = { span: Spanning; between: boolean };

/**
 * A bar across the days a date covers in a week: open at the end where it goes on into another week. A period is
 * filled; a single date known only within the days is hollow and dashed ("between these days"), named as such.
 */
function SpanBar(props: { bar: Bar<BarItem>; calendar: CalendarName }) {
  const tint = useTint();
  const { t, language, fieldName } = useTranslations();
  const ref = () => props.bar.item.span.ref;
  const name = () => sayRef(ref(), fieldName);
  const title = () =>
    props.bar.item.between
      ? `${name()}: ${sayBetween(nameOf(props.bar.item.span.first, props.calendar), nameOf(props.bar.item.span.last, props.calendar), language(), t)}`
      : name();
  return (
    <a
      href={itemHref(ref().type, ref().id)}
      title={title()}
      data-testid="calendar-bar"
      data-lane={props.bar.lane}
      data-between={props.bar.item.between ? "true" : undefined}
      style={{
        "grid-row": String(props.bar.lane + 2),
        "grid-column": `${props.bar.start + 1} / span ${props.bar.end - props.bar.start + 1}`,
      }}
      class={[
        "mb-0.5 min-w-0 truncate px-1.5 text-[0.7rem] leading-5 font-medium",
        {
          border: props.bar.item.between,
          "border-dashed": props.bar.item.between,
          "border-slate-500/70": props.bar.item.between,
          "bg-white/60": props.bar.item.between,
          italic: props.bar.item.between,
        },
        props.bar.item.between ? "" : tint(ref().type),
        {
          "ml-0.5": props.bar.startsHere,
          "rounded-l-sm": props.bar.startsHere,
          "mr-0.5": props.bar.endsHere,
          "rounded-r-sm": props.bar.endsHere,
        },
      ]}
    >
      <span class="font-semibold uppercase not-italic opacity-70">{fieldName(ref().type, ref().field)}</span>
      <span class="opacity-50"> · </span>
      {ref().label}
    </a>
  );
}

/**
 * A week of the grid: seven columns. Behind, the cells (a rule between them; shaded outside the month). In front, a grid
 * of the same columns with the day numbers in its first row, a row for each lane of bars, and what is on each day last.
 */
function WeekRow(props: {
  week: (number | null)[];
  report: MonthReport;
  ranges: Ranged<BarItem>[];
  onAdd?: (day: DayOut) => void;
}) {
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
            <div
              style={{ "grid-row": "1", "grid-column": String(index() + 1) }}
              class="flex h-7 items-start justify-between px-1.5 pt-1"
            >
              <Show when={jdn !== null && entry(jdn!)}>
                <a
                  href={dayHref(name(jdn!))}
                  aria-label={sayDate(name(jdn!), language(), t)}
                  class="inline-flex size-5 items-center justify-center rounded-full text-xs font-semibold text-slate-700 hover:bg-slate-200"
                >
                  {name(jdn!).day}
                </a>
                {/* (a new feast or other characterisation, or a document dated on the day) */}
                <Show when={props.onAdd}>
                  {(add) => (
                    <button
                      type="button"
                      aria-haspopup="dialog"
                      aria-label={t("calendar_add_on", "Add to {date}", { date: sayDate(name(jdn!), language(), t) })}
                      title={t("calendar_add_on", "Add to {date}", { date: sayDate(name(jdn!), language(), t) })}
                      onClick={() => add()(entry(jdn!)!.day)}
                      class="inline-flex size-5 cursor-pointer items-center justify-center rounded-sm text-sm leading-none text-slate-400 select-none hover:bg-slate-200 hover:text-slate-800"
                    >
                      +
                    </button>
                  )}
                </Show>
              </Show>
            </div>
          )}
        </For>
        <For each={bars()}>{(bar) => <SpanBar bar={bar} calendar={props.report.calendar} />}</For>
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
 * day is a chip on it (a short period, up to `CALENDAR_NARROW_DAYS`, on each of its days); a longer period is a filled
 * bar across the days it covers (`spanning`); a single date known only within days of the month is a hollow, dashed bar
 * across them (`between`); feasts and the like are named on their days. (What is known only to a range beyond the month,
 * `roughly`, is listed under the grid by `MonthFoot`.)
 */
export function MonthGrid(props: { report: MonthReport; onAdd?: (day: DayOut) => void }) {
  const { language } = useTranslations();
  const ranged = (span: Spanning, between: boolean): Ranged<BarItem> => ({
    item: { span, between },
    first: Math.max(span.first.jdn, props.report.first.jdn),
    last: Math.min(span.last.jdn, props.report.last.jdn),
    trueFirst: span.first.jdn,
    trueLast: span.last.jdn,
  });
  const ranges = (): Ranged<BarItem>[] => [
    ...props.report.spanning.map((span) => ranged(span, false)),
    ...props.report.between.map((span) => ranged(span, true)),
  ];
  return (
    <div class="overflow-hidden rounded-sm border border-slate-300 bg-white" data-testid="calendar-month">
      <div class="grid grid-cols-7 bg-slate-100/80 text-xs font-semibold text-slate-500 uppercase">
        <For each={weekHeadings(language())}>
          {(day) => <div class="border-l border-slate-300 px-2 py-1.5 first:border-l-0">{day}</div>}
        </For>
      </div>
      <For each={props.report.weeks}>{(week) => <WeekRow week={week} report={props.report} ranges={ranges()} onAdd={props.onAdd} />}</For>
    </div>
  );
}
