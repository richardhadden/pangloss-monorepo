import { createEffect, For, lazy, Show } from "solid-js";
import type { Accessor } from "solid-js";
import type { JSX } from "@solidjs/web";
import type { VirtualRowsControls, VirtualRowsProps } from "./virtualRowsProps";

// (only a long list needs the virtualiser)
const Virtualised = lazy(() => import("./VirtualisedRows")) as <T>(props: VirtualRowsProps<T>) => JSX.Element;

export type { VirtualRowsControls, VirtualRowsProps };

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
  // (the code is fetched before the list is long, or what is on the page would wait for it at the moment it is)
  createEffect(
    () => !!props.soon,
    (soon) => {
      if (soon) void (Virtualised as unknown as { preload: () => Promise<unknown> }).preload().catch(() => {});
    },
  );
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
