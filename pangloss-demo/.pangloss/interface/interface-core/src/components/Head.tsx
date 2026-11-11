import type { JSX } from "@solidjs/web";
import { children, Show } from "solid-js";
import { useTranslations } from "../context";
import {
  headBarClass,
  headBarLinkClass,
  headButtonClass,
  headLabelClass,
  headRestClass,
  headRestLinkClass,
  plainTint,
  typeChipClass,
} from "./form/styles";

/**
 * The head of something nested: a bar with its type as a chip at the left end, and its label. If it
 * is an item of its own (`href`), the bar is a link to it, and darkens as a chip does; its buttons are beside the link.
 */
export function Head(props: {
  type: string;
  tint: string;
  /** The colour of the rule that hangs from it, which the frame of its type has too */
  rule: string;
  label?: string;
  href?: string;
  /** Gives the bar a button at its right end that folds it (what is shown whole that can be collapsed) */
  onFold?: () => void;
  /** A block nested deep enough to start folded (`startsFolded`): whether it is open, and the button that opens and folds it */
  open?: boolean;
  onToggle?: () => void;
  /**
   * What leads the bar, straight after its type (what an interface module adds to a part: `partActions`), apart from
   * the buttons at its other end
   */
  lead?: JSX.Element;
}) {
  const { t, modelName } = useTranslations();
  // (folding buttons are never inside the link: a click on one is not to go anywhere)
  // (made once: each read of a prop that is elements makes them again)
  const lead = children(() => props.lead);
  // (together at the right end, whether or not there is a label to push them there)
  const buttons = () => (
    <span class="ml-auto flex shrink-0 items-stretch">
      <Show when={props.onToggle && props.href}>
        <button
          type="button"
          class={[headButtonClass, "ml-auto text-slate-500 hover:bg-slate-400/30"]}
          aria-expanded={props.open ? "true" : "false"}
          aria-label={t("fold", "Fold or unfold {name}", { name: modelName(props.type) })}
          title={t("fold", "Fold or unfold {name}", { name: modelName(props.type) })}
          onClick={() => props.onToggle!()}
        >
          {props.open ? "▾" : "▸"}
        </button>
      </Show>
      <Show when={props.onFold}>
        <button
          type="button"
          class={[headButtonClass, "ml-auto text-slate-500 hover:bg-slate-400/30"]}
          aria-label={t("collapse_fold", "Fold {name}", { name: modelName(props.type) })}
          title={t("collapse_fold", "Fold {name}", { name: modelName(props.type) })}
          onClick={() => props.onFold!()}
        >
          ▾
        </button>
      </Show>
    </span>
  );
  const typeChip = () => (
    <span data-type-info={props.type} class={[typeChipClass, props.tint || plainTint, props.rule]}>
      {modelName(props.type)}
    </span>
  );
  const labelled = () => (
    <Show when={props.label}>
      <span class={headLabelClass}>{props.label}</span>
    </Show>
  );
  const hasButtons = () => Boolean(props.onFold || (props.onToggle && props.href));
  return (
    <Show
      when={props.href}
      fallback={
        <div class={headBarClass}>
          {typeChip()}
          <span class={headRestClass}>
            {lead()}
            <Show when={props.onToggle} fallback={labelled()}>
              {/* (as in the form: the grey of the bar, with the label in it, folds and unfolds it; folded, a ▸ says so) */}
              <button
                type="button"
                class="flex min-w-0 flex-1 cursor-pointer items-center gap-2 px-3 py-1 text-left text-sm hover:bg-slate-400/20 focus-visible:bg-slate-400/20 focus-visible:outline-none"
                aria-expanded={props.open ? "true" : "false"}
                aria-label={t("fold", "Fold or unfold {name}", { name: modelName(props.type) })}
                title={t("fold", "Fold or unfold {name}", { name: modelName(props.type) })}
                onClick={() => props.onToggle!()}
              >
                <Show when={!props.open}>
                  <span aria-hidden="true" class="shrink-0 text-xs text-slate-500">
                    ▸
                  </span>
                </Show>
                <span class="min-w-0 truncate">{props.label}</span>
              </button>
            </Show>
            {buttons()}
          </span>
        </div>
      }
    >
      <div class={headBarClass}>
        <a href={props.href} class={["flex min-w-0 flex-1 items-stretch rounded-xs", headBarLinkClass]}>
          {typeChip()}
          <span class={hasButtons() ? headRestLinkClass : headRestClass}>{labelled()}</span>
        </a>
        <Show when={hasButtons()}>
          <span class="flex shrink-0 items-stretch overflow-hidden rounded-r-xs border-y-[0.5px] border-r-[0.5px] border-slate-400/70">
            {buttons()}
          </span>
        </Show>
      </div>
    </Show>
  );
}
