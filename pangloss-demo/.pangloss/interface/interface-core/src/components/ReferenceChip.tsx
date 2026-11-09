import { For, lazy, Loading, Show } from "solid-js";
import { useModels, useTranslations } from "../context";
import { kindRule, kindTint } from "../primitives";
import { getModel } from "../schema";
import type { ReferenceChipProps } from "../types";
import { Customised } from "./Customised";
import { SpaceBands } from "./SpaceBands";
import { typeChipClass } from "./form/styles";

// (a chip has them only in a form: a chip on any other page does not need the clipboard's code)
const ClipButtons = lazy(() => import("./form/ClipButtons"));

/**
 * A small chip for something that is referred to: its type on the left (tinted by its kind or
 * the colour of its model, and framed in it, as the type at the head of a block is) and its label
 * on the right, as tall as the head of a block. A link if it has an `href`. The
 * properties of the edge to it, if any, are its end: each a part of the chip, as its edge model writes it.
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
  const { fieldName } = useTranslations();
  // (a value with a unit is the value and the unit, `19%`; another, its field's name and the value)
  const properties = () => {
    const edge = props.edgeModel ? getModel(definitions, props.edgeModel) : undefined;
    return Object.entries(props.edgeProperties ?? {})
      .filter(([, value]) => value !== null && value !== undefined && value !== "")
      .map(([key, value]) => {
        const field = (edge?.fields ?? []).find((each) => each.key === key);
        const marker = field?.kind === "literal" ? field.markers?.find((each) => each.name === "Slider") : undefined;
        if (typeof marker?.unit === "string") return { key, text: `${String(value)}${marker.unit}` };
        const name = field && edge ? fieldName(edge.name, field.name) : key;
        return { key, text: `${name} ${String(value)}` };
      });
  };
  const body = () => (
    <>
      {/* (`data-tint`: what was just added flashes in its colour: `revealAdded`) */}
      <span
        data-type-info={props.type}
        data-tint
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
    "inline-flex max-w-full min-w-0 items-stretch overflow-hidden rounded-xs border-r-[0.5px] border-slate-400/70 bg-slate-100/70";
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
          <For each={properties()}>
            {(property) => (
              <span
                class="flex shrink-0 items-center border-y-[0.5px] border-l-[0.5px] border-slate-400/70 bg-white/70 px-2 text-sm text-slate-600 tabular-nums"
                data-edge-property={property.key}
              >
                {property.text}
              </span>
            )}
          </For>
          <Show when={props.onCopy}>
            <Loading fallback={null}>
            <ClipButtons
              name={props.label}
              buttonClass="flex w-7 shrink-0 cursor-pointer items-center justify-center border-y-[0.5px] border-l-[0.5px] border-slate-400/70 text-slate-500 select-none hover:bg-slate-300/60"
              onCopy={() => props.onCopy?.()}
              onCut={props.onCut}
            />
            </Loading>
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
      </span>
    </SpaceBands>
  );
}
