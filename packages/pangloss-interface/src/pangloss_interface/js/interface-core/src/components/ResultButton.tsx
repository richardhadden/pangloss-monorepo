import { useModels } from "../context";
import { kindTint } from "../primitives";
import { getModel } from "../schema";
import type { ResultButtonProps } from "../types";

/**
 * A result of a list: a button as wide as what holds it, with the type of the item on the
 * left (tinted by its kind, and only as wide as the type, so labels do not line up in a column)
 * and its label, on one line: what does not fit ends in "…".
 */
export function ResultButton(props: ResultButtonProps) {
  const definitions = useModels();
  const kind = () => getModel(definitions, props.type)?.kind;
  return (
    <a
      href={props.href}
      class="flex w-full items-stretch overflow-hidden rounded-sm border-[0.5px] border-slate-400/70 bg-slate-100 hover:bg-slate-200 active:bg-slate-300"
    >
      <span
        class={[
          "flex shrink-0 items-center border-r-[0.5px] border-slate-400/70 px-4 py-3 text-xs font-semibold uppercase select-none",
          kindTint(kind()),
        ]}
      >
        <span class="min-w-0 truncate">{props.type}</span>
      </span>
      {/* (a block, not a flex container, so that what does not fit ends in "…"; the line breaks of a label are spaces here) */}
      <span class="min-w-0 flex-1 self-center truncate px-4 py-3 text-sm">{props.label}</span>
    </a>
  );
}
