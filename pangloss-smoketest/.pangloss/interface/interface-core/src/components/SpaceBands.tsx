import { Show } from "solid-js";
import type { ParentProps } from "solid-js";
import { useModels, useTranslations } from "../context";
import { spaceTint } from "../primitives";
import { getModel } from "../schema";
import { spacePaddingClass } from "./form/styles";

/**
 * What is in the semantic spaces `spaces` (outermost first). Beside a chip or a row of a list, the
 * names of the spaces go before it, from the outside in, each a muted tab rounded on its left, with
 * no line round what is in it; but each is a box of its colour that what is in it is inside (so the
 * rounded corners of what comes next are on that colour, not on the page). `fill`: as wide as what
 * holds it (a row of a list), not as wide as itself (a chip). `stacked` (round something bigger than
 * a chip, such as a block with fields): each is a band as wide as what holds it, round the next,
 * with its name above what is in it, as a space is in an item's contents.
 */
export function SpaceBands(
  props: ParentProps<{
    spaces: string[];
    depth: number;
    stacked?: boolean;
    fill?: boolean;
  }>,
) {
  return (
    <Show when={props.spaces.length > 0} fallback={props.children}>
      <Show
        when={props.stacked}
        fallback={
          <div class={["min-w-0", { "inline-flex max-w-full": !props.fill, "flex w-full": props.fill }]}>
            <SpaceTabs spaces={props.spaces} depth={props.depth} fill={props.fill}>
              {props.children}
            </SpaceTabs>
          </div>
        }
      >
        <StackedBands spaces={props.spaces} depth={props.depth}>
          {props.children}
        </StackedBands>
      </Show>
    </Show>
  );
}

// (on white, so that the colours of the spaces round it do not show through: only at its rounded corners; nor
// their text colour, which would tint the label of a chip in them)
const opaqueClass = "flex min-w-0 items-stretch rounded-xs bg-white text-black";

// (hairlines top, bottom and left, drawn over a box's own edges but under what is in it, so that they
// take no room: what is inside is on the same edges, and its own hairlines on the same lines, and it
// hides these but at its rounded corners, where they go on behind it with no gap)
const tabLinesClass =
  "after:pointer-events-none after:absolute after:inset-0 after:-z-10 after:rounded-xs after:border-y-[0.5px] after:border-l-[0.5px] after:border-slate-400/70";

/**
 * The first of `spaces` as a box of its colour, rounded as a chip is, with no borders or padding of
 * its own (`tabLinesClass`): its name as a tab at its left, then the rest of the spaces, or what is
 * in them, inside it.
 */
function SpaceTabs(props: ParentProps<{ spaces: string[]; depth: number; fill?: boolean }>) {
  const definitions = useModels();
  const { modelName } = useTranslations();
  return (
    <Show
      when={props.spaces.length > 0}
      fallback={<div class={[opaqueClass, { "flex-1": props.fill }]}>{props.children}</div>}
    >
      <div class={[opaqueClass, { "flex-1": props.fill }]}>
        <div
          class={[
            "relative isolate flex min-w-0 flex-1 items-stretch rounded-xs",
            tabLinesClass,
            // (quieter than the chip: a veil over the tint, under what is in it)
            "before:pointer-events-none before:absolute before:inset-0 before:-z-10 before:rounded-xs before:bg-white/30",
            spaceTint(getModel(definitions, props.spaces[0] ?? "")?.interfaceMeta?.colour, props.depth),
          ]}
        >
          <span class="flex shrink-0 items-center px-2 text-xs font-medium uppercase select-none">
            <span class="opacity-70">{modelName(props.spaces[0] ?? "")}</span>
          </span>
          <SpaceTabs spaces={props.spaces.slice(1)} depth={props.depth + 1} fill={props.fill}>
            {props.children}
          </SpaceTabs>
        </div>
      </div>
    </Show>
  );
}

// (bands round something bigger than a chip, each with its name above what is in it)
function StackedBands(props: ParentProps<{ spaces: string[]; depth: number }>) {
  const definitions = useModels();
  const { modelName } = useTranslations();
  return (
    <Show when={props.spaces.length > 0} fallback={props.children}>
      <div
        class={[
          "flex w-full min-w-0 flex-col rounded-xs",
          spaceTint(getModel(definitions, props.spaces[0] ?? "")?.interfaceMeta?.colour, props.depth),
        ]}
      >
        <span class="flex shrink-0 items-center px-3 pt-2 text-xs font-semibold uppercase select-none @max-md:px-1.5 @max-sm:px-1">
          {modelName(props.spaces[0] ?? "")}
        </span>
        <div class={["min-w-0 flex-1", spacePaddingClass]}>
          <StackedBands spaces={props.spaces.slice(1)} depth={props.depth + 1}>
            {props.children}
          </StackedBands>
        </div>
      </div>
    </Show>
  );
}
