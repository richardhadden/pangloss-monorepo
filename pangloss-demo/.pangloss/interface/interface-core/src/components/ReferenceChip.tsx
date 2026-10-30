import { For, Show } from "solid-js";
import { useModels } from "../context";
import { kindTint } from "../primitives";
import { getModel } from "../schema";
import type { ReferenceChipProps } from "../types";
import { Customised } from "./Customised";

/**
 * A small chip for something that is referred to: its type on the left (tinted by its kind or
 * the colour of its model) and its label on the right. A link if it has an `href`. The
 * properties of the edge to it, if any, follow as a small pill each (for now).
 */
export function ReferenceChip(props: ReferenceChipProps) {
  // (a card of an interface module that the model names is used instead)
  return (
    <Customised
      slot="viewCard"
      type={props.type}
      props={{ type: props.type, label: props.label, href: props.href, context: "reference" }}
      fallback={<DefaultReferenceChip {...props} />}
    />
  );
}

function DefaultReferenceChip(props: ReferenceChipProps) {
  const definitions = useModels();
  const model = () => getModel(definitions, props.type);
  const properties = () => Object.entries(props.edgeProperties ?? {});
  const body = () => (
    <>
      <span
        class={[
          "flex shrink-0 items-center border-r-[0.5px] border-slate-400/70 px-2 py-0.5 text-xs font-semibold uppercase select-none",
          kindTint(model()?.kind, model()?.interfaceMeta?.colour),
        ]}
      >
        {props.type}
      </span>
      <span class="min-w-0 truncate px-2 py-0.5 text-sm">{props.label}</span>
    </>
  );
  const frame = "inline-flex max-w-full min-w-0 items-stretch overflow-hidden rounded-sm border-[0.5px] border-slate-400/70 bg-slate-100/70";
  return (
    <span class="inline-flex max-w-full min-w-0 items-center gap-2">
      <Show
        when={props.href !== undefined}
        fallback={<span class={frame}>{body()}</span>}
      >
        <a href={props.href} class={[frame, "hover:bg-slate-200/70 active:bg-slate-300/70"]}>
          {body()}
        </a>
      </Show>
      <For each={properties()}>
        {([name, value]) => (
          <span class="shrink-0 rounded-full border-[0.5px] border-slate-400/70 bg-slate-200/70 px-2 py-0.5 text-xs text-slate-600">
            {name} {String(value)}
          </span>
        )}
      </For>
    </span>
  );
}
