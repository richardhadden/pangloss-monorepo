import { createSignal, Show, untrack } from "solid-js";
import { useComponent, useTranslations } from "../../context";
import { inputClass } from "./styles";
import { buttonClass } from "../../primitives";

// (the footer of a dialog: buttons of the larger size)
const footerButtonClass = buttonClass("ordinary", "md");
const dangerButtonClass = buttonClass("danger", "md");
// (stashing is what the dialog is for)
const stashButtonClass = buttonClass("primary", "md");

/**
 * Asks what to do with a form that has changes in it. `leaving`: the page is being left, and the choices are Stay,
 * Leave without saving and (with `canStash`) Stash and leave. Without it, the item is being stashed (the Stash button),
 * and the choices are Stash and Cancel. Something stashed needs a label: if the item has none (`label`), there is a
 * field for one, and stashing waits for it.
 */
export function StashDialog(props: {
  type: string;
  label: string | undefined;
  leaving: boolean;
  canStash: boolean;
  onStash: (label: string) => void;
  onLeave?: () => void;
  onClose: () => void;
}) {
  const Modal = useComponent("Modal");
  const { t, modelName } = useTranslations();
  const needsLabel = untrack(() => !props.label);
  const [label, setLabel] = createSignal(untrack(() => props.label ?? ""));
  const ready = () => label().trim() !== "";
  const named = () => ({ type: modelName(props.type) });
  const stash = () => {
    if (ready()) props.onStash(label().trim());
  };
  return (
    <Modal
      title={
        props.leaving
          ? t("leave_title", "Leave without saving?")
          : t("stash_title", "Stash this {type}", named())
      }
      onClose={props.onClose}
      size="fit"
    >
      <form
        class="flex flex-col gap-4 p-4 text-sm"
        onSubmit={(event) => {
          event.preventDefault();
          if (props.canStash) stash();
        }}
      >
        {/* (the text wraps at the width of the buttons, and does not set it) */}
        <Show when={props.leaving}>
          <p class="w-0 min-w-full">
            <Show
              when={props.canStash}
              fallback={t("leave_lost", "The changes in this form are not saved: they will be lost.")}
            >
              {t(
                "leave_or_stash",
                "The changes in this form are not saved. Stash it to finish it later, or leave it and lose them.",
              )}
            </Show>
          </p>
        </Show>
        <Show when={!props.leaving}>
          <p class="w-0 min-w-full">
            {t(
              "stash_explain",
              "A stashed {type} is kept in this browser, to be finished later: it is offered where a new one is made.",
              named(),
            )}
          </p>
        </Show>
        <Show when={props.canStash && needsLabel}>
          <label class="flex flex-col gap-1">
            <span class="text-xs font-semibold text-slate-600 uppercase select-none">
              {t("stash_label", "A label, to know it by")}
            </span>
            <input
              class={inputClass}
              value={label()}
              autofocus
              onInput={(event) => setLabel(event.currentTarget.value)}
            />
          </label>
        </Show>
        <div class="flex flex-wrap justify-end gap-2">
          <button type="button" class={footerButtonClass} onClick={props.onClose} autofocus={props.canStash && needsLabel ? undefined : true}>
            <Show when={props.leaving} fallback={t("cancel", "Cancel")}>
              {t("leave_stay", "Stay")}
            </Show>
          </button>
          <Show when={props.leaving}>
            <button type="button" class={dangerButtonClass} onClick={() => props.onLeave?.()}>
              {t("leave_discard", "Leave without saving")}
            </button>
          </Show>
          <Show when={props.canStash}>
            <button type="submit" class={stashButtonClass} disabled={!ready()}>
              <Show when={props.leaving} fallback={t("stash", "Stash")}>
                {t("stash_and_leave", "Stash and leave")}
              </Show>
            </button>
          </Show>
        </div>
      </form>
    </Modal>
  );
}
