import { Show } from "solid-js";
import type { ParentProps } from "solid-js";
import { useModels, useTranslations } from "../context";
import { kindRule, kindTint } from "../primitives";
import { getModel } from "../schema";
import type { ResultButtonProps } from "../types";
import { Customised } from "./Customised";
import { SpaceBands } from "./SpaceBands";

/**
 * A result of a list: a button as wide as what holds it, with the type of the item on the
 * left (tinted by its kind, and only as wide as the type, so labels do not line up in a column)
 * and its label, on one line: what does not fit ends in "…". An item in semantic spaces is
 * wrapped in a band for each; one inside another document has a button to that document at the
 * far left, which the bands do not wrap.
 */
export function ResultButton(props: ResultButtonProps) {
  // (a model may name a card of an interface module for itself: it is used instead, wherever this is)
  return (
    <Customised
      slot="viewCard"
      type={props.type}
      props={{
        type: props.type,
        label: props.label,
        href: props.href,
        spaces: props.spaces,
        context: "result",
      }}
      fallback={<DefaultResultButton {...props} />}
    />
  );
}

function DefaultResultButton(props: ResultButtonProps) {
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const model = () => getModel(definitions, props.type);
  return (
    // (an item inside a document has a button to it, always at the left end: what is next to it is in it, as the
    // spaces are in each other: the button's colour is the whole row's, under the rounded corners of what is next)
    <div
      class={[
        "flex items-stretch rounded-sm",
        // (its hairlines too, top, bottom and left, as the tab of a space has them: drawn over its edges, under
        // what is next, which hides them but at its rounded corners)
        {
          "relative isolate bg-slate-100/70 after:pointer-events-none after:absolute after:inset-0 after:-z-10 after:rounded-sm after:border-y-[0.5px] after:border-l-[0.5px] after:border-slate-400/70":
            !!props.head,
        },
      ]}
    >
      <Show when={props.head}>
        {(head) => (
          <a
            href={`/${head().type}/${head().id}`}
            aria-label={t("go_to_head", "Go to the {type}", {
              type: modelName(head().type),
            })}
            title={t("go_to_head", "Go to the {type}", {
              type: modelName(head().type),
            })}
            class="flex w-10 shrink-0 items-center justify-center rounded-l-sm text-slate-500 select-none hover:bg-slate-200/70 active:bg-slate-300/70"
          >
            {/* (layers: the context the item is in) */}
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              class="size-4 select-none"
              aria-hidden="true"
            >
              <polygon points="12 2 2 7 12 12 22 7 12 2" />
              <polyline points="2 17 12 22 22 17" />
              <polyline points="2 12 12 17 22 12" />
            </svg>
          </a>
        )}
      </Show>
      <div class="min-w-0 flex-1 rounded-sm bg-white">
        <SpaceBands spaces={props.spaces ?? []} depth={0} fill>
          <a
            href={props.href}
            class={[
              // (framed on its right only: its type has a frame in its own colour, as a chip's has, and the label top and bottom)
              "flex w-full items-stretch overflow-hidden rounded-sm border-r-[0.5px] border-slate-400/70 bg-slate-100/70 hover:bg-slate-200/70 active:bg-slate-300/70",
            ]}
          >
            <span
              class={[
                "flex shrink-0 items-center border-[0.5px] px-4 py-3 text-xs font-semibold uppercase select-none",
                "rounded-l-sm",
                kindTint(model()?.kind, model()?.interfaceMeta?.colour),
                kindRule(model()?.kind, model()?.interfaceMeta?.colour),
              ]}
            >
              <span class="min-w-0 truncate">{modelName(props.type)}</span>
            </span>
            {/* (a block, not a flex container, so that what does not fit ends in "…"; the line breaks of a label are spaces here) */}
            <span class="min-w-0 flex-1 truncate border-y-[0.5px] border-slate-400/70 px-4 py-3 text-sm">
              {props.label}
            </span>
          </a>
        </SpaceBands>
      </div>
    </div>
  );
}
