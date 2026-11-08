import type { Accessor } from "solid-js";
import type { JSX } from "@solidjs/web";

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
  /** That the list may soon be `virtual`, as more of it is read: its code is fetched now */
  soon?: boolean;
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
