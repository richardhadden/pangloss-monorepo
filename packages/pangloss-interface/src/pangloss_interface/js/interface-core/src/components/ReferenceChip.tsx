import { For, Show } from "solid-js";
import { useModels, useTranslations } from "../context";
import { kindRule, kindTint } from "../primitives";
import { getModel } from "../schema";
import type { ReferenceChipProps } from "../types";
import { Customised } from "./Customised";
import { SpaceBands } from "./SpaceBands";
import { ClipButtons } from "./form/Clip";
import { typeChipClass } from "./form/styles";

/**
 * A small chip for something that is referred to: its type on the left (tinted by its kind or
 * the colour of its model, and framed in it, as the type at the head of a block is) and its label
 * on the right, as tall as the head of a block. A link if it has an `href`. The
 * properties of the edge to it, if any, follow as a small pill each (for now).
 */
export function ReferenceChip(props: ReferenceChipProps) {
  // (a card of an interface module that the model names is used instead)
  return (
    <Customised
      slot="viewCard"
      type={props.type}
      skip={props.onRemove !== undefined}
      props={{
        type: props.type,
        label: props.label,
        href: props.href,
        context: "reference",
      }}
      fallback={<DefaultReferenceChip {...props} />}
    />
  );
}

/**
 * The chip itself, never a module's card: for a card that wants to look like the chip where it is a
 * reference (a type of a typology), as it does in a form
 */
export function DefaultReferenceChip(props: ReferenceChipProps) {
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const model = () => getModel(definitions, props.type);
  const properties = () => Object.entries(props.edgeProperties ?? {});
  const body = () => (
    <>
      <span
        class={[
          typeChipClass,
          kindTint(model()?.kind, model()?.interfaceMeta?.colour),
          kindRule(model()?.kind, model()?.interfaceMeta?.colour),
        ]}
      >
        {modelName(props.type)}
      </span>
      <span class="min-w-0 truncate border-y-[0.5px] border-slate-400/70 px-2 py-1 text-sm">{props.label}</span>
    </>
  );
  const frame =
    // (only its right side: the type has a frame of its own colour, and the label and buttons are framed top and bottom)
    "inline-flex max-w-full min-w-0 items-stretch overflow-hidden rounded-sm border-r-[0.5px] border-slate-400/70 bg-slate-100/70";
  return (
    <SpaceBands spaces={props.spaces ?? []} depth={0}>
      <span class="inline-flex max-w-full min-w-0 items-center gap-2">
        {/* (the remove button is the end of the chip, so the link is inside the frame, not the frame itself) */}
        <span class={frame}>
          <Show
            when={props.href !== undefined}
            fallback={<span class="flex min-w-0 items-stretch">{body()}</span>}
          >
            <a
              href={props.href}
              class="flex min-w-0 items-stretch hover:bg-slate-200/70 active:bg-slate-300/70"
            >
              {body()}
            </a>
          </Show>
          <Show when={props.onCopy}>
            <ClipButtons
              name={props.label}
              buttonClass="flex w-7 shrink-0 cursor-pointer items-center justify-center border-y-[0.5px] border-l-[0.5px] border-slate-400/70 text-slate-500 select-none hover:bg-slate-300/60"
              onCopy={() => props.onCopy?.()}
              onCut={props.onCut}
            />
          </Show>
          <Show when={props.onRemove}>
            <button
              type="button"
              class="flex w-7 shrink-0 cursor-pointer items-center justify-center border-y-[0.5px] border-l-[0.5px] border-slate-400/70 text-xs text-red-800 select-none hover:bg-red-400/30"
              aria-label={props.removeLabel ?? t("remove", "Remove")}
              title={props.removeLabel ?? t("remove", "Remove")}
              onClick={() => props.onRemove?.()}
            >
              ✕
            </button>
          </Show>
        </span>
        <For each={properties()}>
          {([name, value]) => (
            <span class="shrink-0 rounded-full border-[0.5px] border-slate-400/70 bg-slate-200/70 px-2 py-0.5 text-xs text-slate-600">
              {name} {String(value)}
            </span>
          )}
        </For>
      </span>
    </SpaceBands>
  );
}
