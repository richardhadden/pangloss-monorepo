import { createMemo, For, Show, untrack } from "solid-js";
import type { Accessor } from "solid-js";
import type { JSX } from "@solidjs/web";
import { createWindowVirtualizer } from "../primitives";

/** How a list of rows is scrolled to: given to `VirtualRows`'s `controls` */
export interface VirtualRowsControls {
  /** Scrolls the window so that the row is at the top (under `scrollPaddingStart`) */
  scrollToIndex: (index: number) => void;
}

export interface VirtualRowsProps<T> {
  rows: T[];
  /**
   * Whether only the rows on show are rendered. The caller decides (by how many rows, or how much is in them): a
   * list rendered whole is in flow, laid out as it always was, and does not move as rows are measured
   */
  virtual: boolean;
  /** The height of a row before it is measured, in pixels */
  estimateSize: number;
  /** The space between rows, in pixels (virtual; in flow, the parent's gap) */
  gap?: number;
  /** What is fixed over the top of the window, in pixels: a row scrolled to goes under it */
  scrollPaddingStart?: number;
  /** The list's own classes (virtual: it is `relative`, as tall as every row; in flow: `contents`, the rows are the parent's) */
  class?: string;
  /** (virtual) the classes of the box each row is in: a row that is a `grid-cols-subgrid` row needs a grid round it */
  rowClass?: string;
  /** Gets the controls (scrolling to a row) as the list is made */
  controls?: (controls: VirtualRowsControls) => void;
  testId?: string;
  children: (row: T, index: Accessor<number>) => JSX.Element;
}

/**
 * The rows of a list that can be long: what refers to an entity can be thousands of rows, which took seconds to
 * make and locked the page. Rendered `virtual`, only the rows on show (and a few beyond) are made, measured as they
 * come (they need not be the same height), and the rest of the height is kept with a box, as the list page does
 * (`createWindowVirtualizer`); on the server, and before the browser has measured anything, as many as fill an
 * ordinary window. Not `virtual`, every row is rendered in flow as if the list were not there (`display: contents`):
 * a short list keeps its layout, as a row of a grid round it.
 *
 * Each row is drawn by `children`, given the row and its index; it is a block of its own in either mode, so it
 * must not rely on its siblings for its layout.
 */
export function VirtualRows<T>(props: VirtualRowsProps<T>) {
  return (
    <Show when={props.virtual} fallback={<InFlow {...props} />}>
      <Virtualised {...props} />
    </Show>
  );
}

function InFlow<T>(props: VirtualRowsProps<T>) {
  let list: HTMLDivElement | undefined;
  props.controls?.({
    scrollToIndex: (index) => list?.children[index]?.scrollIntoView?.({ block: "start" }),
  });
  return (
    <div ref={list} class={[props.class, "contents"]} data-testid={props.testId}>
      <For each={props.rows}>{(row, index) => props.children(row, index)}</For>
    </div>
  );
}

function Virtualised<T>(props: VirtualRowsProps<T>) {
  const virtual = createWindowVirtualizer({
    count: () => props.rows.length,
    estimateSize: props.estimateSize,
    gap: props.gap,
    overscan: 5,
    scrollPaddingStart: props.scrollPaddingStart,
  });
  props.controls?.({ scrollToIndex: virtual.scrollToIndex });
  // (the row at an index, as the list stands now)
  const rowAt = createMemo(() => (index: number) => props.rows[index]);
  return (
    <div
      ref={virtual.setList}
      class={[props.class, "relative w-full"]}
      style={{ height: `${virtual.totalSize()}px` }}
      data-testid={props.testId}
      data-virtual
    >
      <For each={virtual.items()} keyed={(row) => row.key}>
        {(row) => (
          <div
            // (the index is set before it is measured, which reads it; measured once it is rendered, as what that
            // changes is not written while rendering; the measure follows the row's size from then on)
            ref={(element) => {
              element.dataset.index = String(untrack(row).index);
              queueMicrotask(() => virtual.measure(element));
            }}
            data-index={row().index}
            class={[props.rowClass, "absolute top-0 left-0 w-full"]}
            style={{ transform: `translateY(${row().start - virtual.scrollMargin()}px)` }}
          >
            <Show when={rowAt()(row().index) !== undefined}>
              {props.children(rowAt()(row().index)!, () => row().index)}
            </Show>
          </div>
        )}
      </For>
    </div>
  );
}
