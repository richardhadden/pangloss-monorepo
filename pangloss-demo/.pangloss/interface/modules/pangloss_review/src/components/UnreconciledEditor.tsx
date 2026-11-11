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
  useModels,
  useToasts,
  useTranslations,
} from "@pangloss/interface-core";
import type { EditCardProps } from "@pangloss/interface-core";
import { For, onSettled, Show, untrack } from "solid-js";
import type { Ref } from "../api";
import { isSuggestion, UNRECONCILED } from "../parts";
import { confirmedPart, entityInPlace, partAt, pathOf, targetOfOne } from "./confirming";
import { MentionChip, mentionButtonClass } from "./MentionChip";
import { ReconcileButton } from "./ReconcileButton";
import type { DoneHere } from "./ReconcilePanel";

// (a button of the bar of a new mention, which is 40px tall for its box: as `headButtonClass`, and as wide as that)
const NEW_BAR_BUTTON =
  "flex w-10 shrink-0 cursor-pointer items-center justify-center border-l-[0.5px] border-slate-400/70 text-xs select-none";

/**
 * An unreconciled mention in a form, in place of the box a document has.
 *
 * One that is saved is not edited: what the source calls it is what it is known by (and what other mentions are
 * compared with), so it is its chip, as tall as any other, with a spanner that reconciles it and a ✕ that takes it
 * out; its URIs, if it has any, are listed under it. A new one is written: what the source calls it, which entity
 * type it would be (of those the relation takes: `standsInFor` of the relation's option), and its URIs.
 */
export default function UnreconciledEditor(props: EditCardProps) {
  const form = useItemForm();
  const { t, modelName } = useTranslations();
  const types = () => (props.option && "standsInFor" in props.option ? (props.option.standsInFor ?? []) : []);
  const type = () => (typeof props.value.unreconciledType === "string" ? props.value.unreconciledType : "");
  const id = () => (typeof props.value.id === "string" ? props.value.id : undefined);
  const label = () => (typeof props.value.label === "string" ? props.value.label : "");
  const uris = () => (Array.isArray(props.value.uris) ? props.value.uris.filter((uri) => typeof uri === "string") : []);
  const set = (key: string, value: string) => form.set([...props.path, key], value);
  const definitions = useModels();
  const toasts = useToasts();
  // (of this document, in the form: what a dialog may offer to do with this mention)
  const stillThere = (other: string, kind: "mention" | "suggestion") => {
    const root = form.plain();
    const path = pathOf(root, other);
    const part = path && partAt(root, path);
    if (!part) return false;
    return kind === "mention" ? part.type === UNRECONCILED : isSuggestion(definitions, String(part.type));
  };
  // The entity in the mention's place, with the properties of the relation to it, as one more change of the form;
  // and with it what was ticked that is in this document: the mentions of the same, and the suggestions that name
  // its URI, confirmed as the entity
  const reconciled = (entity: Ref, here: DoneHere) => {
    const root = form.plain();
    let done = 0;
    for (const other of here.mentions) {
      const path = pathOf(root, other);
      const part = path && partAt(root, path);
      if (!path || !part || part.type !== UNRECONCILED) continue;
      form.set(path, entityInPlace(part, entity));
      done += 1;
    }
    for (const row of here.suggestions) {
      const path = pathOf(root, row.id);
      const part = path && partAt(root, path);
      if (!path || !part || !isSuggestion(definitions, String(part.type))) continue;
      const given = { ...part, target: targetOfOne(part.target, entity) };
      form.set(path, confirmedPart(definitions, given, row.becomes ?? "Identification"));
      done += 1;
    }
    props.onChange(entityInPlace(props.value, entity));
    if (done > 0)
      toasts?.show(t("review_done_in_form", "{count} more in this document are done with it", { count: String(done) }));
  };
  // (a new one is of the relation's first type until the reader says otherwise: said once it is on the page, in the
  // browser, as nothing is written to the form while it is drawn)
  onSettled(() => {
    untrack(() => {
      const first = types()[0];
      if (!type() && first) set("unreconciledType", first);
    });
  });
  // (the reader's own once it is drawn: see the skill's note on boxes)
  const starting = untrack(label);
  const tint = () => kindTint("Document", props.model.interfaceMeta?.colour) || plainTint;
  const rule = () => kindRule("Document", props.model.interfaceMeta?.colour);
  const remove = () => (
    <Show when={props.onRemove}>
      {(onRemove) => (
        <button
          type="button"
          class={[id() ? mentionButtonClass : NEW_BAR_BUTTON, "text-red-800 hover:bg-red-400/30"]}
          aria-label={t("remove_item", "Remove {name}", { name: modelName(props.type) })}
          title={t("remove_item", "Remove {name}", { name: modelName(props.type) })}
          onClick={() => onRemove()()}
        >
          ✕
        </button>
      )}
    </Show>
  );
  return (
    <div class="flex w-full min-w-0 flex-col" data-item-id={id()} data-testid="unreconciled-editor">
      <Show
        when={id()}
        fallback={
          <>
            {/* (a bar of one height, 40px, so that its button can be as wide as it is tall) */}
            <div class={[headBarClass, "h-10"]}>
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
              {remove()}
            </div>
            <div class={["ml-2 pt-4", nestedClass, rule()]}>
              <ModelFields model={props.model} path={() => props.path} env={{}} skip={["unreconciledType"]} />
            </div>
          </>
        }
      >
        {(found) => (
          <>
            <MentionChip type={type()} label={label()}>
              <ReconcileButton
                id={found()}
                label={label()}
                class={[mentionButtonClass, "text-slate-600 hover:bg-slate-200"].join(" ")}
                stillThere={stillThere}
                onReconciled={reconciled}
              />
              {remove()}
            </MentionChip>
            <Show when={uris().length > 0}>
              <ul class="mt-1 flex flex-col gap-0.5 text-xs text-slate-600" data-testid="unreconciled-uris">
                <For each={uris()}>
                  {(uri) => (
                    <li class="truncate">
                      <a href={uri} class="underline hover:text-slate-900" rel="noreferrer" target="_blank">
                        {uri}
                      </a>
                    </li>
                  )}
                </For>
              </ul>
            </Show>
          </>
        )}
      </Show>
    </div>
  );
}
