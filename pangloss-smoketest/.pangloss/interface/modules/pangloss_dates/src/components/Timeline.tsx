import { createMemo, For, Show } from "solid-js";

const clamp = (value: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, value));

/**
 * A vertical timeline of the years from `from` (at the top) to `to`: a track with a thumb on the year chosen (`value`,
 * owned by the one who uses it, told of each change by `onChange`), the year beside the thumb, and for each year that has
 * something a bar as long as how much it has (`counts`; the year with most has the longest). Pressing anywhere on the
 * track takes the thumb there and drags it; `onDrag` is told when a drag starts and ends. With the keys the thumb goes
 * from one year that has something to the next (Home and End to the first and the last). Adapted from manmax-frontend's
 * `VerticalTimeline` (acdh-oeaw). It has no height of its own: it fills what it is in.
 */
export function Timeline(props: {
  from: number;
  to: number;
  value: number;
  onChange: (year: number) => void;
  onDrag?: (dragging: boolean) => void;
  counts: [number, number][];
  label: string;
}) {
  const lo = () => Math.min(props.from, props.to);
  const hi = () => Math.max(props.from, props.to);
  const value = () => clamp(Math.round(props.value), lo(), hi());
  // (from the top: the earlier year above)
  const percent = (year: number) => (hi() === lo() ? 0 : ((year - lo()) / (hi() - lo())) * 100);
  const shown = createMemo(() => props.counts.filter(([year]) => year >= lo() && year <= hi()));
  const most = () => Math.max(1, ...shown().map(([, count]) => count));

  let track: HTMLDivElement | undefined;
  const yearAt = (clientY: number) => {
    const rect = track?.getBoundingClientRect();
    // (not measured yet, or no height: where it is)
    if (!rect || rect.height === 0) return value();
    return Math.round(lo() + clamp((clientY - rect.top) / rect.height, 0, 1) * (hi() - lo()));
  };

  // (the pointer is captured, so the drag goes on outside the track. The page scrolls as the thumb moves, and the track,
  // which sticks to the window, can move with it: so after the first press the year follows how far the pointer has
  // gone, not where it is on the track)
  const startDrag = (event: PointerEvent) => {
    const element = event.currentTarget as HTMLDivElement;
    element.setPointerCapture?.(event.pointerId);
    props.onDrag?.(true);
    const startYear = yearAt(event.clientY);
    const startY = event.clientY;
    const height = track?.getBoundingClientRect().height ?? 0;
    props.onChange(startYear);
    const move = (moved: PointerEvent) => {
      if (height === 0) return;
      const year = startYear + ((moved.clientY - startY) / height) * (hi() - lo());
      props.onChange(Math.round(clamp(year, lo(), hi())));
    };
    const up = (ended: PointerEvent) => {
      element.releasePointerCapture?.(ended.pointerId);
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerup", up);
      element.removeEventListener("pointercancel", up);
      props.onDrag?.(false);
    };
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerup", up);
    element.addEventListener("pointercancel", up);
  };

  const onKeyDown = (event: KeyboardEvent) => {
    const years = shown().map(([year]) => year);
    if (years.length === 0) return;
    let next: number | undefined;
    if (event.key === "ArrowDown" || event.key === "ArrowRight") next = years.find((year) => year > value());
    else if (event.key === "ArrowUp" || event.key === "ArrowLeft") next = years.findLast((year) => year < value());
    else if (event.key === "Home") next = years[0];
    else if (event.key === "End") next = years.at(-1);
    else return;
    event.preventDefault();
    if (next !== undefined) props.onChange(next);
  };

  // Each column keeps 1rem at the top and the bottom (`top-4 bottom-4`, `h-4`), so that a percent from the top is the
  // same height in all three.
  return (
    <div class="flex h-full items-stretch gap-2 text-xs select-none">
      {/* (the year chosen, beside the thumb; the first and the last, where the thumb is not near them) */}
      <div class="relative w-10">
        <div class="absolute inset-x-0 top-4 bottom-4 text-[0.65rem] text-slate-400 tabular-nums">
          <Show when={percent(value()) > 8}>
            <span class="absolute top-0 right-0 -translate-y-1/2">{lo()}</span>
          </Show>
          <Show when={percent(value()) < 92}>
            <span class="absolute top-full right-0 -translate-y-1/2">{hi()}</span>
          </Show>
          <span
            class="absolute right-0 -translate-y-1/2 rounded-xs bg-slate-600 px-1 py-0.5 font-medium text-white tabular-nums"
            style={{ top: `${percent(value())}%` }}
          >
            {value()}
          </span>
        </div>
      </div>
      <div class="flex flex-col items-center">
        <span class="h-4" />
        <div class="relative w-1 flex-1 rounded-full bg-slate-200" ref={track}>
          <div class="absolute inset-x-0 top-0 rounded-full bg-slate-400" style={{ height: `${percent(value())}%` }} />
          {/* (wider than the track, to be easy to press) */}
          <div class="absolute inset-y-0 left-1/2 w-6 -translate-x-1/2 cursor-pointer touch-none" onPointerDown={startDrag}>
            <div
              role="slider"
              tabindex={0}
              aria-orientation="vertical"
              aria-label={props.label}
              aria-valuemin={lo()}
              aria-valuemax={hi()}
              aria-valuenow={value()}
              class="absolute left-1/2 size-4 -translate-x-1/2 -translate-y-1/2 cursor-grab rounded-full border-2 border-slate-600 bg-white shadow-sm focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:outline-none active:cursor-grabbing"
              style={{ top: `${percent(value())}%` }}
              onKeyDown={onKeyDown}
            />
          </div>
        </div>
        <span class="h-4" />
      </div>
      {/* (how much each year has) */}
      <div class="relative w-14" aria-hidden="true">
        <div class="absolute inset-x-0 top-4 bottom-4">
          <For each={shown()}>
            {([year, count]) => (
              <div
                class={[
                  "absolute left-0 h-1.5 min-w-0.5 -translate-y-1/2 rounded-r-xs",
                  year === value() ? "bg-slate-700" : "bg-slate-400/70",
                ]}
                style={{ top: `${percent(year)}%`, width: `${(count / most()) * 100}%` }}
                data-bar={year}
              />
            )}
          </For>
        </div>
      </div>
    </div>
  );
}
