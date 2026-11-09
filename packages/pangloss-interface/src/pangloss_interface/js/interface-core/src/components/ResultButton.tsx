import { For, Show } from "solid-js";
import { useModels, useModules, useTranslations } from "../context";
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
 * far right, which the bands do not wrap. What the interface modules add (`resultMarks`) is at the right end of the
 * row, inside its link.
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
        selected: props.selected,
      }}
      fallback={<DefaultResultButton {...props} />}
    />
  );
}

function DefaultResultButton(props: ResultButtonProps) {
  const definitions = useModels();
  const { t, modelName } = useTranslations();
  const model = () => getModel(definitions, props.type);
  const marks = useModules().resultMarks();
  return (
    // (an item inside a document has a button to it, always at the right end: the button's colour is the whole
    // row's, under the rounded corners of what is next to it)
    <div
      class={[
        "flex items-stretch rounded-xs",
        // (its hairlines too, top, bottom and right, as the tab of a space has them: drawn over its edges, under
        // what is next, which hides them but at its rounded corners)
        {
          "relative isolate bg-slate-100/70 after:pointer-events-none after:absolute after:inset-0 after:-z-10 after:rounded-xs after:border-y-[0.5px] after:border-r-[0.5px] after:border-slate-400/70":
            !!props.head,
        },
      ]}
    >
      <div class="min-w-0 flex-1 rounded-xs bg-white">
        <SpaceBands spaces={props.spaces ?? []} depth={0} fill>
          <a
            href={props.href}
            aria-current={props.selected ? "true" : undefined}
            class={[
              // (framed on its right only: its type has a frame in its own colour, as a chip's has, and the label top and bottom)
              "flex w-full items-stretch overflow-hidden rounded-xs border-r-[0.5px] border-slate-400/70 hover:bg-slate-200/70 active:bg-slate-300/70",
              { "bg-slate-200/70": !!props.selected, "bg-slate-100/70": !props.selected },
            ]}
          >
            <span
              class={[
                "flex shrink-0 items-center border-[0.5px] px-4 py-3 text-xs font-semibold uppercase select-none",
                "rounded-l-xs",
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
            <Show when={props.useCount !== undefined}>
              <span class="flex shrink-0 items-center border-y-[0.5px] border-slate-400/70 pr-3 select-none">
                <span
                  data-testid="use-count"
                  title={t("use_count", "Referred to by {count}", { count: props.useCount ?? 0 })}
                  class={[
                    "inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[0.65rem] font-bold tabular-nums",
                    { "bg-sky-600 text-white": (props.useCount ?? 0) > 0, "bg-slate-200 text-slate-600": props.useCount === 0 },
                  ]}
                >
                  {String(props.useCount)}
                </span>
              </span>
            </Show>
            <Show when={marks.length > 0 && props.item}>
              {(item) => (
                <span class="flex shrink-0 items-center border-y-[0.5px] border-slate-400/70">
                  <For each={marks}>{(Mark) => <Mark type={props.type} item={item()} />}</For>
                </span>
              )}
            </Show>
          </a>
        </SpaceBands>
      </div>
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
            class="flex w-10 shrink-0 items-center justify-center rounded-r-xs text-slate-500 select-none hover:bg-slate-200/70 active:bg-slate-300/70"
          >
            {/* (layers: the context the item is in) */}
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.75"
              stroke-linecap="square"
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
    </div>
  );
}
