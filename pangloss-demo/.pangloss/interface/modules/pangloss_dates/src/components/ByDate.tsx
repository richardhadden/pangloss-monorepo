import { createMemo, createSignal, For, onCleanup, Show } from "solid-js";
import { fieldRuleClass, ItemValue, SectionBar, useTranslations } from "@pangloss/interface-core";
import type { IncomingEntry, IncomingViewProps } from "@pangloss/interface-core";
import { arrangeByDate, byYear, dateInWords, yearSpan } from "../dating";
import { Timeline } from "./Timeline";

// (the band near the top of the page in which a year's heading is the one the timeline is at: below the bars)
const READING_BAND = "-112px 0px -60% 0px";

/**
 * What refers to the item and can have a date (the view `incomingViews.ByDate`, chosen by `SortByDate` in the
 * console), a section of its own after the item's facts: in order of date under the year it is in, each with its date
 * in words and its field on the left and its chip on the right, and last those whose date is not known. A timeline
 * beside them, with a bar for how many each year has, scrolls to a year (and follows the page as it is scrolled).
 */
export default function ByDate(props: IncomingViewProps) {
  const { t, language } = useTranslations();
  const arranged = createMemo(() => arrangeByDate(props.entries));
  const span = createMemo(() => yearSpan(arranged().dated));
  const years = createMemo(() => byYear(arranged().dated));
  const counts = createMemo(() => years().map(([year, group]): [number, number] => [year, group.length]));

  // The timeline: the year it is at, and the headings of the years it scrolls to
  const [at, setAt] = createSignal<number>();
  const position = () => at() ?? years()[0]?.[0] ?? 0;
  const headings = new Map<number, HTMLElement>();
  let dragging = false;
  let observer: IntersectionObserver | undefined;
  const heading = (year: number) => (element: HTMLElement) => {
    headings.set(year, element);
    if (typeof IntersectionObserver === "undefined") return;
    // (the page scrolled: the timeline is at the year whose heading is near the top, unless it is being dragged)
    observer ??= new IntersectionObserver(
      (seen) => {
        if (dragging) return;
        const year = seen.find((entry) => entry.isIntersecting)?.target.getAttribute("data-year");
        if (year) setAt(Number(year));
      },
      { rootMargin: READING_BAND },
    );
    observer.observe(element);
  };
  onCleanup(() => observer?.disconnect());
  // (the first year from `year` on that has something; the last, if none has)
  const yearWithItems = (year: number) => years().find(([some]) => some >= year)?.[0] ?? years().at(-1)?.[0];
  const goTo = (year: number) => {
    setAt(year);
    const target = yearWithItems(year);
    if (target !== undefined) headings.get(target)?.scrollIntoView?.({ block: "start" });
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
          <For each={years()}>
            {([year, group]) => (
              <>
                <div
                  ref={heading(year)}
                  data-year={year}
                  class="col-span-2 scroll-mt-28 pt-5 pb-1 text-xs font-semibold text-slate-400 tabular-nums first:pt-0"
                >
                  {year}
                </div>
                <For each={group}>
                  {(entry) => (
                    <DatedRow
                      entry={entry}
                      date={dateInWords(String(entry.item.dateText ?? ""), { language: language(), t })}
                    />
                  )}
                </For>
              </>
            )}
          </For>
          <Show when={arranged().unknown.length > 0}>
            <div class="col-span-2 grid grid-cols-subgrid" data-testid="incoming-date-unknown">
              <div class="col-span-2 pt-5 pb-1 text-xs font-semibold text-slate-400">
                {t("incoming_date_unknown", "Date unknown")}
              </div>
              <For each={arranged().unknown}>{(entry) => <DatedRow entry={entry} />}</For>
            </div>
          </Show>
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

/** What refers to the item, dated: the field it is in and, under it, its date (in words) on the left, its chip on the right */
function DatedRow(props: { entry: IncomingEntry; date?: string }) {
  return (
    <div
      class={["col-span-2 grid grid-cols-subgrid items-center border-t py-2.5", fieldRuleClass]}
      data-testid="dated-item"
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
