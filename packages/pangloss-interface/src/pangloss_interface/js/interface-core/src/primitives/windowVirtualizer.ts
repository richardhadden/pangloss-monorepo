import {
  measureElement,
  observeWindowOffset,
  observeWindowRect,
  Virtualizer,
  windowScroll,
} from "@tanstack/virtual-core";
import type { VirtualItem, VirtualizerOptions } from "@tanstack/virtual-core";
import { createEffect, createSignal, onSettled, untrack } from "solid-js";
import type { Accessor } from "solid-js";

// (the height of the window taken before it can be measured: on the server, and in the first render
// in the browser, which has to be the same)
const UNMEASURED_HEIGHT = 1000;

export interface WindowVirtualizerOptions {
  /** How many rows there are */
  count: Accessor<number>;
  /** The height of a row before it is measured, in pixels */
  estimateSize: number;
  /** The space between rows, in pixels */
  gap?: number;
  /** Rows rendered beyond each end of the window */
  overscan?: number;
  /** What is fixed over the top of the window (a row under it is not on show), in pixels */
  scrollPaddingStart?: number;
  /** The row at the top of the window at first: rendered on the server, and scrolled to in the browser */
  initialIndex?: number;
}

export interface WindowVirtualizer {
  /** The rows to render: `start` is from the top of the document, so less `scrollMargin()` from the top of the list */
  items: Accessor<VirtualItem[]>;
  /** The height of the whole list */
  totalSize: Accessor<number>;
  /** How far the list is from the top of the document */
  scrollMargin: Accessor<number>;
  /** The `ref` of each row (which also has `data-index`): its height is measured, and followed */
  measure: (element: Element) => void;
  /** The first row on show (below `scrollPaddingStart`) */
  firstVisible: () => number;
  /** The `ref` of the list: where it is in the document is measured */
  setList: (element: Element) => void;
  /** Scrolls the window so that the row is at the top (under `scrollPaddingStart`) */
  scrollToIndex: (index: number) => void;
}

/**
 * A list scrolled by the window, of which only the rows on show (and a few beyond) are rendered:
 * TanStack Virtual's core, for Solid 2.0. Rows are measured as they are rendered, so they need
 * not all be the same height. Before the browser has measured anything (and on the server), the
 * rows from `initialIndex` are rendered, as many as fill an ordinary window.
 */
export function createWindowVirtualizer(options: WindowVirtualizerOptions): WindowVirtualizer {
  const gap = options.gap ?? 0;
  const initialIndex = options.initialIndex ?? 0;
  let list: Element | undefined;
  const settings: VirtualizerOptions<Window, Element> = {
    count: untrack(options.count),
    estimateSize: () => options.estimateSize,
    gap,
    overscan: options.overscan ?? 5,
    scrollPaddingStart: options.scrollPaddingStart ?? 0,
    getScrollElement: () => (typeof window === "undefined" ? null : window),
    observeElementRect: observeWindowRect,
    observeElementOffset: observeWindowOffset,
    scrollToFn: windowScroll,
    measureElement,
    initialRect: { width: 0, height: UNMEASURED_HEIGHT },
    initialOffset: initialIndex * (options.estimateSize + gap),
    // (`sync`: the window was scrolled, and the rows follow at once. Otherwise the rows were measured, in the
    // browser's resize observer: the rows that follow from that are made in the next frame, not in the observer's
    // own pass, where making them (and so observing them) is "ResizeObserver loop completed with undelivered
    // notifications", an error in the page)
    onChange: (instance, sync) => {
      if (sync || typeof requestAnimationFrame === "undefined") return apply(instance);
      if (frame !== undefined) return;
      frame = requestAnimationFrame(() => {
        frame = undefined;
        apply(instance);
      });
    },
  };
  let frame: number | undefined;
  const apply = (instance: Virtualizer<Window, Element>) => {
    setItems(instance.getVirtualItems());
    setTotalSize(instance.getTotalSize());
  };
  const virtualizer = new Virtualizer<Window, Element>(settings);
  const [items, setItems] = createSignal<VirtualItem[]>(virtualizer.getVirtualItems());
  const [totalSize, setTotalSize] = createSignal(virtualizer.getTotalSize());
  const [scrollMargin, setScrollMargin] = createSignal(0);

  const update = (changes: Partial<VirtualizerOptions<Window, Element>>) => {
    Object.assign(settings, changes);
    virtualizer.setOptions(settings);
    virtualizer._willUpdate();
    setItems(virtualizer.getVirtualItems());
    setTotalSize(virtualizer.getTotalSize());
  };

  // (more rows: such as a list fetched again)
  createEffect(options.count, (count) => {
    if (count !== settings.count) update({ count });
  });

  // (where the list starts: below what is above it on the page)
  const measureMargin = () => {
    const margin = list ? list.getBoundingClientRect().top + window.scrollY : 0;
    if (margin === settings.scrollMargin) return;
    setScrollMargin(margin);
    update({ scrollMargin: margin });
  };

  onSettled(() => {
    const cleanup = virtualizer._didMount();
    measureMargin();
    // (a list that starts at the top is scrolled there: the window may still be where a list before it was)
    if (initialIndex > 0) virtualizer.scrollToIndex(initialIndex, { align: "start" });
    else if (window.scrollY > 0) window.scrollTo(0, 0);
    // (and again when what it is in changes size: what is above it may have grown, as a panel that opens over it. In
    // the next frame, not in the observer's own pass: rows made there are observed there, which is the "ResizeObserver
    // loop" error, as for `onChange` above)
    const observer =
      typeof ResizeObserver === "undefined" || !list?.parentElement
        ? undefined
        : new ResizeObserver(() => requestAnimationFrame(measureMargin));
    if (observer && list?.parentElement) observer.observe(list.parentElement);
    return () => {
      observer?.disconnect();
      if (frame !== undefined) cancelAnimationFrame(frame);
      cleanup();
    };
  });

  return {
    items,
    totalSize,
    scrollMargin,
    measure: (element) => virtualizer.measureElement(element),
    firstVisible: () =>
      virtualizer.getVirtualItemForOffset(
        (virtualizer.scrollOffset ?? 0) + (settings.scrollPaddingStart ?? 0),
      )?.index ?? 0,
    setList: (element) => {
      list = element;
    },
    scrollToIndex: (index) => virtualizer.scrollToIndex(index, { align: "start" }),
  };
}
