import {
  headBarClass,
  headButtonClass,
  inputClass,
  kindRule,
  kindTint,
  ModelFields,
  nestedClass,
  plainTint,
  typeChipClass,
  useItemForm,
  useTranslations,
} from "@pangloss/interface-core";
import type { EditCardProps } from "@pangloss/interface-core";
import { For, onSettled, Show, untrack } from "solid-js";
import { ReconcileButton } from "./ReconcileButton";

/**
 * An unreconciled mention in a form, in place of the box a document has: its type at the left, what the source calls
 * it, which entity type it would be (of those the relation takes), a spanner that reconciles it, and its URIs under
 * it. Its `unreconciledType` is one of the types the relation's option stands in for (`standsInFor`).
 */
export default function UnreconciledEditor(props: EditCardProps) {
  const form = useItemForm();
  const { t, modelName } = useTranslations();
  const types = () => (props.option && "standsInFor" in props.option ? (props.option.standsInFor ?? []) : []);
  const type = () => (typeof props.value.unreconciledType === "string" ? props.value.unreconciledType : "");
  const id = () => (typeof props.value.id === "string" ? props.value.id : undefined);
  const set = (key: string, value: string) => form.set([...props.path, key], value);
  // (a new one is of the relation's first type until the reader says otherwise: said once it is on the page, in the
  // browser, as nothing is written to the form while it is drawn)
  onSettled(() => {
    untrack(() => {
      const first = types()[0];
      if (!type() && first) set("unreconciledType", first);
    });
  });
  // (the reader's own once it is drawn: see the skill's note on boxes)
  const starting = untrack(() => (typeof props.value.label === "string" ? props.value.label : ""));
  const tint = () => kindTint("Document", props.model.interfaceMeta?.colour) || plainTint;
  const rule = () => kindRule("Document", props.model.interfaceMeta?.colour);
  return (
    <div class="flex w-full min-w-0 flex-col" data-item-id={id()} data-testid="unreconciled-editor">
      <div class={headBarClass}>
        <span data-type-info={props.type} data-tint class={[typeChipClass, tint(), rule()]}>
          {modelName(props.type)}
        </span>
        <div class="flex min-w-0 flex-1 items-stretch gap-1 rounded-r-xs border-y-[0.5px] border-r-[0.5px] border-slate-400/70 p-1">
          <input
            class={[inputClass, "min-w-0 flex-1"]}
            aria-label={t("review_mention_label", "What the source calls it")}
            placeholder={t("review_mention_label", "What the source calls it")}
            value={starting}
            onInput={(event) => set("label", event.currentTarget.value)}
          />
          <Show when={types().length > 1}>
            <select
              class={[inputClass, "w-auto"]}
              aria-label={t("review_mention_type", "What kind of thing it is")}
              value={type()}
              onChange={(event) => set("unreconciledType", event.currentTarget.value)}
            >
              <For each={types()}>{(name) => <option value={name} textContent={modelName(name)} />}</For>
            </select>
          </Show>
        </div>
        <Show when={id()}>
          {(found) => (
            <ReconcileButton
              id={found()}
              label={typeof props.value.label === "string" ? props.value.label : ""}
              class={[headButtonClass, "text-slate-600 hover:bg-slate-400/30"].join(" ")}
              changed={form.changed}
            />
          )}
        </Show>
        <Show when={props.onRemove}>
          <button
            type="button"
            class={[headButtonClass, "text-red-800 hover:bg-red-400/30"]}
            aria-label={t("remove_item", "Remove {name}", { name: modelName(props.type) })}
            onClick={() => props.onRemove?.()}
          >
            ✕
          </button>
        </Show>
      </div>
      <div class={["ml-2 pt-4", nestedClass, rule()]}>
        <ModelFields model={props.model} path={() => props.path} env={{}} skip={["unreconciledType"]} />
      </div>
    </div>
  );
}
