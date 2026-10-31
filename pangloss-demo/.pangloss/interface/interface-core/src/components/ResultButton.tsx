import { Show } from "solid-js";
import type { ParentProps } from "solid-js";
import { useModels, useTranslations } from "../context";
import { kindTint } from "../primitives";
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
  // (what is next to the button to the head node is square on that side)
  const flushLeft = () => props.head !== undefined;
  const barFlush = () => flushLeft() && (props.spaces ?? []).length === 0;
  return (
    <div class="flex items-stretch">
      {/* (an item inside a document has a button to it, always at the left end: not in the bands) */}
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
            class="flex w-10 shrink-0 items-center justify-center rounded-l-sm border-[0.5px] border-r-0 border-slate-400/70 bg-slate-100/70 text-slate-500 select-none hover:bg-slate-200/70 active:bg-slate-300/70"
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
      <div class="min-w-0 flex-1">
        <SpaceBands spaces={props.spaces ?? []} depth={0} flushLeft={flushLeft()}>
          <a
            href={props.href}
            class={[
              "flex w-full items-stretch overflow-hidden border-[0.5px] border-slate-400/70 bg-slate-100/70 hover:bg-slate-200/70 active:bg-slate-300/70",
              { "rounded-sm": !barFlush(), "rounded-r-sm": barFlush() },
            ]}
          >
            <span
              class={[
                "flex shrink-0 items-center border-r-[0.5px] border-slate-400/70 px-4 py-3 text-xs font-semibold uppercase select-none",
                kindTint(model()?.kind, model()?.interfaceMeta?.colour),
              ]}
            >
              <span class="min-w-0 truncate">{modelName(props.type)}</span>
            </span>
            {/* (a block, not a flex container, so that what does not fit ends in "…"; the line breaks of a label are spaces here) */}
            <span class="min-w-0 flex-1 self-center truncate px-4 py-3 text-sm">
              {props.label}
            </span>
          </a>
        </SpaceBands>
      </div>
    </div>
  );
}
