import { Show } from "solid-js";
import type { ParentProps } from "solid-js";
import { useModels, useTranslations } from "../context";
import { spaceTint } from "../primitives";
import { getModel } from "../schema";

/**
 * What is in the semantic spaces `spaces` (outermost first): each is a band round the next,
 * with the name of the space at its left, so the names stand side by side from the outside in.
 * `stacked` (round something bigger than a chip, such as a block with fields): each band is as
 * wide as what holds it, with its name above what is in it, as a space is in an item's contents.
 */
export function SpaceBands(
  props: ParentProps<{ spaces: string[]; depth: number; flushLeft?: boolean; stacked?: boolean }>,
) {
  const definitions = useModels();
  const { modelName } = useTranslations();
  const tint = () =>
    spaceTint(
      getModel(definitions, props.spaces[0] ?? "")?.interfaceMeta?.colour,
      props.depth,
    );
  return (
    <Show when={props.spaces.length > 0} fallback={props.children}>
      <div
        class={[
          "flex border-[0.5px] border-slate-400/70",
          // (round a chip, the context is quieter than the chip: a veil over the tint, under what is in it)
          {
            "relative isolate before:pointer-events-none before:absolute before:inset-0 before:-z-10 before:bg-white/30":
              !props.stacked,
          },
          {
            "items-stretch": !props.stacked,
            "w-full": props.stacked,
            "min-w-0": props.stacked,
            "flex-col": props.stacked,
          },
          { "rounded-sm": !props.flushLeft, "rounded-r-sm": props.flushLeft },
          tint(),
        ]}
      >
        <span
          class={[
            "flex shrink-0 items-center uppercase select-none",
            // (round a chip, as big as the chip's type but quieter, lighter in weight and colour: the spaces are its context)
            { "px-3 pt-2 text-xs font-semibold": props.stacked, "px-2 text-xs font-medium opacity-70": !props.stacked },
          ]}
        >
          {modelName(props.spaces[0] ?? "")}
        </span>
        <div class={["min-w-0 flex-1", { "p-1": !props.stacked, "p-3": props.stacked }]}>
          <SpaceBands spaces={props.spaces.slice(1)} depth={props.depth + 1} stacked={props.stacked}>
            {props.children}
          </SpaceBands>
        </div>
      </div>
    </Show>
  );
}
