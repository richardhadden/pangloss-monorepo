import type { NavIconCellProps } from "../types";

/**
 * A square cell for an icon in the navigation bar, as wide as the retracted bar (`w-12`, and as high as its row).
 * With `onClick` it is a button; without, it is only an icon with a label.
 */
export function NavIconCell(props: NavIconCellProps) {
  return props.onClick ? (
    <button
      type="button"
      aria-label={props.label}
      aria-expanded={props.expanded === undefined ? undefined : props.expanded ? "true" : "false"}
      onClick={props.onClick}
      class="flex h-full w-12 shrink-0 select-none cursor-pointer items-center justify-center hover:bg-slate-400/40 active:bg-slate-400/60"
    >
      {props.children}
    </button>
  ) : (
    <span role="img" aria-label={props.label} class="flex h-full w-12 shrink-0 select-none items-center justify-center">
      {props.children}
    </span>
  );
}
