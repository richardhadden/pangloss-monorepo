import type { NavRowProps } from "../types";

/**
 * A row of the navigation bar, one cell high (`h-12`, as high as the console). It has a hairline along its bottom,
 * inside that height, so that the first row's lines up with the bottom of the console; the last thing in the bar has
 * none. Put the `NavIconCell` last: it is what shows when the bar is retracted, and what is before it
 * (shown only when the bar is expanded) fills the rest of the row.
 */
export function NavRow(props: NavRowProps) {
  return (
    <div class="flex h-12 shrink-0 items-center border-b-[0.5px] border-slate-400/70 text-slate-700 last:border-b-0">
      {props.children}
    </div>
  );
}
