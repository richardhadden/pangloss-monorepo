import { createMemo, createSignal, For, onCleanup, Show } from "solid-js";
import type { Accessor } from "solid-js";
import { fieldRuleClass, ItemValue, SectionBar, useTranslations, VirtualRows } from "@pangloss/interface-core";
import type { IncomingEntry, IncomingViewProps, VirtualRowsControls } from "@pangloss/interface-core";
import { arrangeByDate, byYear, dateInWords, yearSpan } from "../dating";
import { Timeline } from "./Timeline";

// (the band near the top of the page in which a year's heading is the one the timeline is at: below the bars)
const READING_BAND = "-112px 0px -60% 0px";
// (what is fixed over the top of the window: a heading scrolled to goes under it, as `scroll-mt-28`)
const BAR_HEIGHT = 112;
/** From how many lines on (years and items) only those on show are rendered: thousands locked the page for seconds */
export const BY_DATE_VIRTUAL_FROM = 200;
// (the height of a line before it is measured: an item's row, two lines of small text)
const LINE_HEIGHT = 56;

/** One line of the list: a year, an item under it, the heading of those whose date is not known, or one of them */
type Line =
  | { kind: "year"; year: number }
  | { kind: "dated"; entry: IncomingEntry }
  | { kind: "unknown" }
  | { kind: "undated"; entry: IncomingEntry };

/**
 * What refers to the item and can have a date (the view `incomingViews.ByDate`, chosen by `SortByDate` in the
 * console), a section of its own after the item's facts: in order of date under the year it is in, each with its date
 * in words and its field on the left and its chip on the right, and last those whose date is not known. A timeline
 * beside them, with a bar for how many each year has, scrolls to a year (and follows the page as it is scrolled).
 * A long list is rendered only as it comes on show (`VirtualRows`).
 */
export default function ByDate(props: IncomingViewProps) {
  const { t, language } = useTranslations();
  const arranged = createMemo(() => arrangeByDate(props.entries));
  const span = createMemo(() => yearSpan(arranged().dated));
  const years = createMemo(() => byYear(arranged().dated));
  const counts = createMemo(() => years().map(([year, group]): [number, number] => [year, group.length]));
  const lines = createMemo<Line[]>(() => {
    const made: Line[] = [];
    for (const [year, group] of years()) {
      made.push({ kind: "year", year });
      for (const entry of group) made.push({ kind: "dated", entry });
    }
    if (arranged().unknown.length > 0) {
      made.push({ kind: "unknown" });
      for (const entry of arranged().unknown) made.push({ kind: "undated", entry });
    }
    return made;
  });

  // The timeline: the year it is at, and the headings of the years it scrolls to
  const [at, setAt] = createSignal<number>();
  const position = () => at() ?? years()[0]?.[0] ?? 0;
  let controls: VirtualRowsControls | undefined;
  let dragging = false;
  let observer: IntersectionObserver | undefined;
  // (the page scrolled: the timeline is at the year whose heading is near the top, unless it is being dragged)
  const headings: Headings = {
    watch: (element) => {
      if (typeof IntersectionObserver === "undefined") return;
      observer ??= new IntersectionObserver(
        (seen) => {
          if (dragging) return;
          const year = seen.find((entry) => entry.isIntersecting)?.target.getAttribute("data-year");
          if (year) setAt(Number(year));
        },
        { rootMargin: READING_BAND },
      );
      observer.observe(element);
    },
    forget: (element) => observer?.unobserve(element),
  };
  onCleanup(() => observer?.disconnect());
  // (the first year from `year` on that has something; the last, if none has)
  const yearWithItems = (year: number) => years().find(([some]) => some >= year)?.[0] ?? years().at(-1)?.[0];
  const goTo = (year: number) => {
    setAt(year);
    const target = yearWithItems(year);
    if (target === undefined) return;
    const index = lines().findIndex((line) => line.kind === "year" && line.year === target);
    if (index >= 0) controls?.scrollToIndex(index);
  };
  // (a drag that ends on a year with nothing in it: the thumb goes to the year the page went to)
  const onDrag = (now: boolean) => {
    dragging = now;
    if (!now) setAt(yearWithItems(position()));
  };

  return (
    <section>
      <SectionBar>{t("incoming_timeline", "Timeline")}</SectionBar>
      <div class="flex items-start gap-8">
        <div class="grid min-w-0 flex-1 grid-cols-[10rem_minmax(0,1fr)] gap-x-6" data-testid="incoming-by-date">
          <VirtualRows
            rows={lines()}
            virtual={lines().length >= BY_DATE_VIRTUAL_FROM}
            estimateSize={LINE_HEIGHT}
            scrollPaddingStart={BAR_HEIGHT}
            class="col-span-2"
            rowClass="grid grid-cols-[10rem_minmax(0,1fr)] gap-x-6"
            controls={(given) => (controls = given)}
          >
            {(line, index) => <LineOf line={line} index={index} headings={headings} language={language()} t={t} />}
          </VirtualRows>
        </div>
        <Show when={span() && span()![0] < span()![1]}>
          {/* (as tall as the list, but no taller than the window, in which it stays while the list scrolls) */}
          <div class="shrink-0 self-stretch">
            <div class="sticky top-28 h-full max-h-[calc(100vh-10rem)] min-h-40 py-2">
              <Timeline
                from={span()![0]}
                to={span()![1]}
                value={position()}
                onChange={goTo}
                onDrag={onDrag}
                counts={counts()}
                label={t("incoming_go_to_year", "Go to year")}
              />
            </div>
          </div>
        </Show>
      </div>
    </section>
  );
}

/** The headings of the years, watched for which is near the top of the window */
interface Headings {
  watch: (element: HTMLElement) => void;
  forget: (element: HTMLElement) => void;
}

/** One line of the list, by its kind */
function LineOf(props: {
  line: Line;
  index: Accessor<number>;
  headings: Headings;
  language: string;
  t: ReturnType<typeof useTranslations>["t"];
}) {
  return (
    <>
      <Show when={props.line.kind === "year" ? props.line : undefined}>
        {(line) => <YearLine year={line().year} first={props.index() === 0} headings={props.headings} />}
      </Show>
      <Show when={props.line.kind === "dated" ? props.line : undefined}>
        {(line) => (
          <DatedRow
            entry={line().entry}
            date={dateInWords(String(line().entry.item.dateText ?? ""), { language: props.language, t: props.t })}
          />
        )}
      </Show>
      <Show when={props.line.kind === "unknown"}>
        <div
          class="col-span-2 pt-5 pb-1 text-xs font-semibold text-slate-400"
          data-testid="incoming-date-unknown"
        >
          {props.t("incoming_date_unknown", "Date unknown")}
        </div>
      </Show>
      <Show when={props.line.kind === "undated" ? props.line : undefined}>
        {(line) => <DatedRow entry={line().entry} undated />}
      </Show>
    </>
  );
}

/** The heading of a year: watched while it is in the page (a line is taken out as the list scrolls) */
function YearLine(props: { year: number; first: boolean; headings: Headings }) {
  let element: HTMLElement | undefined;
  onCleanup(() => element && props.headings.forget(element));
  return (
    <div
      ref={(found) => {
        element = found;
        props.headings.watch(found);
      }}
      data-year={props.year}
      class={[
        "col-span-2 scroll-mt-28 pb-1 text-xs font-semibold text-slate-400 tabular-nums",
        { "pt-5": !props.first },
      ]}
    >
      {props.year}
    </div>
  );
}

/** What refers to the item, dated: the field it is in and, under it, its date (in words) on the left, its chip on the right */
function DatedRow(props: { entry: IncomingEntry; date?: string; undated?: boolean }) {
  return (
    <div
      class={["col-span-2 grid grid-cols-subgrid items-center border-t py-2.5", fieldRuleClass]}
      data-testid="dated-item"
      data-undated={props.undated ? "" : undefined}
    >
      <div class="flex flex-col gap-0.5">
        <span class="text-xs font-semibold text-slate-500 uppercase">{props.entry.name}</span>
        <Show when={props.date}>
          <span class="text-[0.7rem] text-slate-500">{props.date}</span>
        </Show>
      </div>
      <div class="flex min-w-0 flex-wrap items-center gap-2">
        <ItemValue value={props.entry.item} depth={0} asChip />
      </div>
    </div>
  );
}
