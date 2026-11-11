// The one look of a button that stands by itself (not one in the console, a head bar or a chip, which
// are parts of their bar): five kinds and two sizes (implementation_docs/look-and-feel.md). `Button` draws it; a
// `<button>` or link that needs to be itself (a ref, a test id, a link) takes the classes. Whole class
// names, so that Tailwind finds them.

import type { ButtonKind, ButtonSize } from "../types";

const BASE =
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-1 rounded-xs border-[0.5px] text-xs font-semibold whitespace-nowrap uppercase select-none focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-slate-500/60 disabled:cursor-default disabled:opacity-40 aria-disabled:pointer-events-none aria-disabled:opacity-40";

const SIZES: Record<ButtonSize, string> = {
  sm: "h-6.5 px-2.5",
  md: "h-8 px-3.5",
};
const ICON_SIZES: Record<ButtonSize, string> = {
  sm: "h-6.5 w-7",
  md: "size-8",
};

const KINDS: Record<ButtonKind, string> = {
  ordinary:
    "border-slate-400/70 bg-white text-slate-800 not-disabled:hover:bg-slate-100 not-disabled:active:bg-slate-200",
  primary:
    "border-transparent bg-slate-700 text-white not-disabled:hover:bg-slate-800 not-disabled:active:bg-slate-900",
  danger:
    "border-red-700/60 bg-red-100 text-red-900 not-disabled:hover:bg-red-200 not-disabled:active:bg-red-300",
  quiet: "border-transparent text-slate-600 not-disabled:hover:bg-slate-100 not-disabled:hover:text-slate-900 not-disabled:active:bg-slate-200",
  add: "border-dashed border-slate-400/80 text-slate-500 not-disabled:hover:border-slate-600 not-disabled:hover:bg-slate-50 not-disabled:hover:text-slate-800 not-disabled:active:bg-slate-200",
};

/** The classes of a button of a kind and size; `icon` for one with only an icon (square: 28 × 26 at `sm`) */
export function buttonClass(kind: ButtonKind = "ordinary", size: ButtonSize = "sm", icon = false): string {
  return `${BASE} ${icon ? ICON_SIZES[size] : SIZES[size]} ${KINDS[kind]}`;
}

/**
 * A row of buttons of which one is chosen (Julian | Gregorian; the states of a review): joined, the
 * chosen one dark. The row's classes are `segmentedClass`; each button's, `segmentClass(chosen)`.
 */
export const segmentedClass =
  "inline-flex max-w-full shrink-0 flex-wrap rounded-xs [&>*:first-child]:rounded-l-xs [&>*:last-child]:rounded-r-xs [&>*+*]:-ml-[0.5px]";

const SEGMENT =
  "inline-flex cursor-pointer items-center justify-center gap-1.5 border-[0.5px] px-2.5 whitespace-nowrap select-none focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-slate-500/60 disabled:cursor-default disabled:opacity-40";
// (the words of the frame, as a button's; or values of the content, such as the members of an enum, as text is)
const SEGMENT_TEXT = {
  frame: "h-6.5 text-xs font-semibold uppercase",
  content: "h-7 text-sm",
};

/** One button of a `segmentedClass` row: dark if it is the one chosen. `content` for values (an enum's members), in
 *  the case they are written in; otherwise the words of the frame, upper case */
export function segmentClass(chosen: boolean, content = false): string {
  const text = SEGMENT_TEXT[content ? "content" : "frame"];
  return chosen
    ? `${SEGMENT} ${text} relative z-[1] border-slate-700 bg-slate-700 text-white`
    : `${SEGMENT} ${text} border-slate-400/70 bg-white text-slate-800 not-disabled:hover:bg-slate-100 not-disabled:active:bg-slate-200`;
}

const BADGE = "inline-flex shrink-0 items-center rounded-xs px-1.5 py-px text-xs font-semibold whitespace-nowrap select-none";

/** A small label of a state (ADMIN, CURRENT), in a tint (`bg-… text-…`) given with it */
export const badgeClass = `${BADGE} uppercase`;

/** The same, for a number (v2), in the case it is written in */
export const numberBadgeClass = `${BADGE} tabular-nums`;

/**
 * A button that is part of a bar (the head of a panel, a drawer or a dialog): as tall as the bar, with a
 * hairline on its left, as the console's buttons are. `barIconButtonClass` is the square one, for an icon (Close).
 */
export const barButtonClass =
  "flex h-full shrink-0 cursor-pointer items-center justify-center gap-1.5 border-l-[0.5px] border-slate-400/70 px-3 select-none hover:bg-slate-400/30 focus-visible:bg-slate-400/30 focus-visible:outline-none active:bg-slate-400/50";
export const barIconButtonClass =
  "flex aspect-square h-full shrink-0 cursor-pointer items-center justify-center border-l-[0.5px] border-slate-400/70 select-none hover:bg-slate-400/30 focus-visible:bg-slate-400/30 focus-visible:outline-none active:bg-slate-400/50";
