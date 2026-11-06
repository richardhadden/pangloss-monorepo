import type { ParentProps } from "solid-js";

/**
 * The heading of a section of an item's page (its timeline, what is derived of it): a bar across the page, as the console
 * is, with a hairline round it, well apart from what comes before (the item's own facts have none)
 */
export function SectionBar(props: ParentProps) {
  return (
    <h2 class="mt-16 mb-6 flex h-10 items-center rounded-xs border-[0.5px] border-slate-400/70 bg-slate-200/70 px-4 text-sm font-semibold tracking-wide text-slate-700 uppercase">
      {props.children}
    </h2>
  );
}
