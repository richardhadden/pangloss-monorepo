import { ApiError, ConsoleButton, getItem, useApi, useComponent, useToasts, useTranslations } from "@pangloss/interface-core";
import type { ModelDefinition, NewItemActionProps, NewItemForm } from "@pangloss/interface-core";
import { createMemo, createSignal, Show, untrack } from "solid-js";
import { baseOn, getClasses, itemValues } from "../api";
import type { Summary } from "../api";
import { ItemPicker, ZoteroIcon } from "./ItemPicker";

const reasonOf = (error: unknown) =>
  error instanceof ApiError ? error.detail : error instanceof Error ? error.message : String(error);

/** Picking an item, and then the item the new one is based on, with a way to undo that */
function Based(props: { type: string; model: ModelDefinition; form: NewItemForm; fallback: string }) {
  const api = useApi();
  const toasts = useToasts();
  const { t, modelName } = useTranslations();
  const ReferenceChip = useComponent("ReferenceChip");
  const [picking, setPicking] = createSignal(false);
  const [based, setBased] = createSignal<Summary>();

  const choose = async (picked: Summary) => {
    setPicking(false);
    const type = untrack(() => props.type);
    let item: Record<string, unknown>;
    try {
      item = (await getItem(api, untrack(() => props.fallback), picked.id)) as Record<string, unknown>;
    } catch (error) {
      toasts?.show(t("zotero_not_read", "The item could not be read: {reason}", { reason: reasonOf(error) }), "error");
      return;
    }
    // (the form shows what the item gives; the fields the sync owns are taken from the item when it is saved)
    const keys = untrack(() => props.model.fields)
      .filter((field) => field.kind === "literal")
      .map((field) => field.key);
    props.form.set(["label"], item.label);
    for (const [key, value] of Object.entries(itemValues(item, keys))) props.form.set([key], value);
    props.form.sendBy((body) => baseOn(api, type, picked.id, body));
    setBased(picked);
  };
  const clear = () => {
    props.form.sendBy(undefined);
    setBased(undefined);
  };

  return (
    <>
      <Show
        when={based()}
        fallback={
          <ConsoleButton label={t("zotero_from", "From Zotero")} text onClick={() => setPicking(true)}>
            <span class="flex" data-testid="zotero-from">
              <ZoteroIcon />
            </span>
          </ConsoleButton>
        }
      >
        {(item) => (
          <span class="flex h-full items-center gap-2 border-l-[0.5px] border-slate-400/60 px-3" data-testid="zotero-based-on">
            <span class="text-xs font-semibold uppercase select-none">{t("zotero_based_on", "Based on")}</span>
            <ReferenceChip
              type={item().type}
              label={item().label}
              href={`/${encodeURIComponent(item().type)}/${encodeURIComponent(item().id)}`}
            />
            <button
              type="button"
              class="cursor-pointer rounded-xs px-1 text-slate-600 select-none hover:bg-slate-400/40"
              aria-label={t("zotero_not_based_on", "Not based on it")}
              title={t("zotero_not_based_on", "Not based on it")}
              onClick={clear}
            >
              ✕
            </button>
          </span>
        )}
      </Show>
      <Show when={picking()}>
        <ItemPicker
          title={t("zotero_from_title", "A new {type} from an item of the Zotero library", {
            type: modelName(props.type),
          })}
          note={t(
            "zotero_from_note",
            "The item becomes this {type}, and stays an item of the library: what refers to it is kept. Save makes it so.",
            { type: modelName(props.type) },
          )}
          fallback={props.fallback}
          onPick={(item) => void choose(item)}
          onClose={() => setPicking(false)}
        />
      </Show>
    </>
  );
}

/**
 * *From Zotero* on the form of a new item of a class that an item can be made into (a `newItemActions` entry): the form
 * is filled in from the item picked, and Save turns that item into the new one (`POST /api/zotero/base-on`).
 */
export default function FromZotero(props: NewItemActionProps) {
  const api = useApi();
  const classes = createMemo(() => getClasses(api));
  return (
    <Show when={classes().targets.includes(props.type)}>
      <Based type={props.type} model={props.model} form={props.form} fallback={classes().fallback} />
    </Show>
  );
}
