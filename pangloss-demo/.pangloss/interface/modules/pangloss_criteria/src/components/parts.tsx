// (what the editor and the card both draw)
import { useTranslations } from "@pangloss/interface-core";
import { Show } from "solid-js";
import type { Broken } from "../value";

/** The name of a part of a dialog or form, as the frame's text is */
export const labelClass = "text-xs font-semibold text-slate-500 uppercase";

/**
 * A button at the right end of a description's head bar: square, as wide as the bar is tall (`h-9`, as tall as a
 * chip and its frame), with a hairline before it, as `headButtonClass` has
 */
export const BAR_BUTTON =
  "flex w-9 shrink-0 cursor-pointer items-center justify-center border-l-[0.5px] border-slate-400/70 text-xs select-none";

/**
 * A button in a description's head bar that says what it does in words ("This is…"): first after the type, as tall
 * as the bar, with a hairline after it, before what follows in the bar
 */
export const BAR_WORD_BUTTON =
  "flex shrink-0 cursor-pointer items-center border-r-[0.5px] border-slate-400/70 px-3 text-xs font-semibold whitespace-nowrap uppercase select-none";

/** The pencil of editing, drawn as the interface's icons are (as the label's and the typology tree's pencils) */
export function PencilIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      class="size-4 fill-none stroke-current stroke-[1.75] select-none"
      stroke-linecap="square"
      aria-hidden="true"
    >
      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
    </svg>
  );
}

/**
 * That a description is out of date: "Out of date since migration …" with the reason under it, smaller; or, with no
 * migration to name (the worker found it so), "Out of date: …" and the reason. Its candidates are the last found
 */
export function BrokenNotice(props: { broken: Broken }) {
  const { t } = useTranslations();
  return (
    <div class="flex flex-col gap-0.5 text-red-800" data-testid="criteria-broken">
      <Show
        when={props.broken.since}
        fallback={<p class="text-sm">{t("criteria_broken", "Out of date: {reason}", { reason: props.broken.reason })}</p>}
      >
        {(since) => (
          <>
            <p class="text-sm">{t("criteria_broken_since", "Out of date since migration {migration}", { migration: since() })}</p>
            <p class="text-xs" data-testid="criteria-broken-reason">
              {props.broken.reason}
            </p>
          </>
        )}
      </Show>
    </div>
  );
}
