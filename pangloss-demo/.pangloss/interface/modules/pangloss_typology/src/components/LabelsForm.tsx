import { smallButtonClass, useTranslations } from "@pangloss/interface-core";
import { For, Show, untrack } from "solid-js";
import type { Edit } from "../api";

export const termClass = "text-xs font-semibold text-slate-500 uppercase";
const inputClass =
  "rounded-xs border-[0.5px] border-slate-400/70 bg-white px-2 py-1 text-sm outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-400/60";

/**
 * The labels of a type, in each language its model has, and its description: to change a type's (on its page), or to
 * give a new one (in the dialog of the tree). Saved with `onSave`; `saveLabel` is the save button's words (Save).
 *
 * The boxes are given `initial` **once**, when the form is made, and are the reader's from then on. Written as
 * `value={props.initial.label}` they were given it again whenever anything else of theirs was drawn again (their
 * placeholder, when the language changes) and whenever `initial` was a new object (the type's page follows a live
 * feed), and what was being typed was lost.
 */
export function LabelsForm(props: {
  initial: { label: string; labels: Record<string, string>; description: string | null };
  languages: string[];
  onCancel: () => void;
  onSave: (edit: Edit & { label: string }) => void;
  saveLabel?: string;
  /** While it is being saved: the buttons wait */
  busy?: boolean;
  autofocus?: boolean;
}) {
  const { t } = useTranslations();
  let form!: HTMLFormElement;
  // (plain names, each read once: not `props.initial…` in the markup)
  const startingLabel = untrack(() => props.initial.label);
  const startingLabels = untrack(() => ({ ...props.initial.labels }));
  const startingDescription = untrack(() => props.initial.description ?? "");
  return (
    <form
      ref={form}
      class="flex max-w-xl flex-col gap-3 text-sm"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(form);
        const labels: Record<string, string> = {};
        for (const code of props.languages) {
          const text = String(data.get(`label_${code}`) ?? "").trim();
          if (text !== "") labels[code] = text;
        }
        props.onSave({
          label: String(data.get("label") ?? ""),
          description: String(data.get("description") ?? ""),
          labels,
        });
      }}
    >
      <label class="flex flex-col gap-1">
        <span class={termClass}>{t("typology_default_label", "default")}</span>
        <input name="label" required autofocus={props.autofocus} value={startingLabel} class={inputClass} />
      </label>
      <For each={props.languages}>
        {(code) => {
          const starting = startingLabels[code] ?? "";
          return (
            <label class="flex flex-col gap-1">
              <span class={termClass}>{code}</span>
              <input
                name={`label_${code}`}
                value={starting}
                placeholder={t("typology_not_translated", "(not translated)")}
                class={inputClass}
              />
            </label>
          );
        }}
      </For>
      <label class="flex flex-col gap-1">
        <span class={termClass}>{t("typology_description", "description")}</span>
        <textarea name="description" rows="3" class={inputClass}>
          {startingDescription}
        </textarea>
      </label>
      <div class="flex gap-2">
        <button type="submit" class={smallButtonClass} disabled={props.busy}>
          <Show when={props.saveLabel} fallback={t("save", "Save")}>
            {props.saveLabel}
          </Show>
        </button>
        <button type="button" class={smallButtonClass} onClick={props.onCancel}>
          {t("cancel", "Cancel")}
        </button>
      </div>
    </form>
  );
}
