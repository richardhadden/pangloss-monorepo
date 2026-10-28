import type { NavRowProps } from "../types";

/**
 * A row of the navigation bar, one cell high (`h-12`, as high as the console), under a rule (unless `ruled` is false, as for the first). Put the
 * `NavIconCell` last: it is what shows when the bar is retracted, and what is before it
 * (shown only when the bar is expanded) fills the rest of the row.
 */
export function NavRow(props: NavRowProps) {
  return (
    <div
      class={[
        "flex h-12 shrink-0 items-center text-slate-700",
        props.ruled !== false && "border-t border-slate-400/70",
      ]}
    >
      {props.children}
    </div>
  );
}
