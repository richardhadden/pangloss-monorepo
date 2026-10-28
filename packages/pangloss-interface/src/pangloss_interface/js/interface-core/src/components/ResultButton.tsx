import { Show } from "solid-js";
import type { ParentProps } from "solid-js";
import { useModels } from "../context";
import { colourTint, kindTint } from "../primitives";
import { getModel } from "../schema";
import type { ResultButtonProps } from "../types";

// The bands of the semantic spaces, by how deep they are (whole class names, so that Tailwind finds them)
// (for a space that has no colour of its own; see InterfaceMeta)
const BANDS = [
  "bg-amber-400/25 text-amber-950",
  "bg-violet-400/25 text-violet-950",
  "bg-rose-400/25 text-rose-950",
  "bg-teal-400/25 text-teal-950",
];

/**
 * What is in the semantic spaces `spaces` (outermost first): each is a band round the next,
 * with the name of the space at its left, so the names stand side by side from the outside in.
 */
function Wrapped(props: ParentProps<{ spaces: string[]; depth: number }>) {
  const definitions = useModels();
  const tint = () =>
    colourTint(getModel(definitions, props.spaces[0] ?? "")?.interfaceMeta?.colour) ||
    BANDS[props.depth % BANDS.length];
  return (
    <Show when={props.spaces.length > 0} fallback={props.children}>
      <div
        class={[
          "flex items-stretch rounded-sm border-[0.5px] border-slate-400/70",
          tint(),
        ]}
      >
        <span class="flex shrink-0 items-center px-3 text-xs font-semibold uppercase select-none">
          {props.spaces[0]}
        </span>
        <div class="min-w-0 flex-1 p-1">
          <Wrapped spaces={props.spaces.slice(1)} depth={props.depth + 1}>
            {props.children}
          </Wrapped>
        </div>
      </div>
    </Show>
  );
}

/**
 * A result of a list: a button as wide as what holds it, with the type of the item on the
 * left (tinted by its kind, and only as wide as the type, so labels do not line up in a column)
 * and its label, on one line: what does not fit ends in "…". An item in semantic spaces is
 * wrapped in a band for each.
 */
export function ResultButton(props: ResultButtonProps) {
  const definitions = useModels();
  const model = () => getModel(definitions, props.type);
  return (
    <Wrapped spaces={props.spaces ?? []} depth={0}>
    <a
      href={props.href}
      class="flex w-full items-stretch overflow-hidden rounded-sm border-[0.5px] border-slate-400/70 bg-slate-100 hover:bg-slate-200 active:bg-slate-300"
    >
      <span
        class={[
          "flex shrink-0 items-center border-r-[0.5px] border-slate-400/70 px-4 py-3 text-xs font-semibold uppercase select-none",
          kindTint(model()?.kind, model()?.interfaceMeta?.colour),
        ]}
      >
        <span class="min-w-0 truncate">{props.type}</span>
      </span>
      {/* (a block, not a flex container, so that what does not fit ends in "…"; the line breaks of a label are spaces here) */}
      <span class="min-w-0 flex-1 self-center truncate px-4 py-3 text-sm">{props.label}</span>
    </a>
    </Wrapped>
  );
}
