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
            "flex shrink-0 items-center px-3 text-xs font-semibold uppercase select-none",
            { "pt-2": props.stacked },
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
