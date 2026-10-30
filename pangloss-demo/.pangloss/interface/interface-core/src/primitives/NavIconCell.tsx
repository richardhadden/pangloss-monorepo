import { Show } from "solid-js";
import type { NavIconCellProps } from "../types";

/**
 * A square cell for an icon in the navigation bar, as wide as the retracted bar (`w-12`, and as high as its row).
 * With `onClick` it is a button; without, it is only an icon with a label.
 */
export function NavIconCell(props: NavIconCellProps) {
  return (
    <Show
      when={props.onClick}
      fallback={
        <span
          role="img"
          aria-label={props.label}
          class="flex h-full w-12 shrink-0 items-center justify-center select-none"
        >
          {props.children}
        </span>
      }
    >
      <button
        type="button"
        aria-label={props.label}
        aria-expanded={props.expanded === undefined ? undefined : props.expanded ? "true" : "false"}
        onClick={props.onClick}
        class="flex h-full w-12 shrink-0 cursor-pointer items-center justify-center select-none hover:bg-slate-400/40 active:bg-slate-400/60"
      >
        {props.children}
      </button>
    </Show>
  );
}
