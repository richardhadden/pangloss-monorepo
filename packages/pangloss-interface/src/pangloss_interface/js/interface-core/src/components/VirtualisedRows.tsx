import { createMemo, For, Show, untrack } from "solid-js";
import { createWindowVirtualizer } from "../primitives";
import type { VirtualRowsProps } from "./virtualRowsProps";

// (apart from `VirtualRows`, which is on the page of every item: only a long list needs this, and the virtualiser)
export default function Virtualised<T>(props: VirtualRowsProps<T>) {
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
