import { FieldRow, smallButtonClass, useApi, useComponent, useTranslations } from "@pangloss/interface-core";
import type { NewItemActionProps, NewItemForm } from "@pangloss/interface-core";
import { createMemo, createSignal, Show, untrack } from "solid-js";
import { baseOn, getClasses } from "../api";
import type { Summary } from "../api";
import { ItemPicker, ZoteroIcon } from "./ItemPicker";

/** The row of the item the new one is based on: a button that finds one, then the item, with a way to undo that */
function Based(props: { type: string; form: NewItemForm; fallback: string }) {
  const api = useApi();
  const { t, modelName } = useTranslations();
  const ReferenceChip = useComponent("ReferenceChip");
  const [picking, setPicking] = createSignal(false);
  const [based, setBased] = createSignal<Summary>();

  // (the fields the sync owns are not on the form: Save takes them from the item. The label is the item's, to change)
  const choose = (picked: Summary) => {
    setPicking(false);
    const type = untrack(() => props.type);
    props.form.set(["label"], picked.label);
    props.form.sendBy((body) => baseOn(api, type, picked.id, body));
    setBased(picked);
  };
  const clear = () => {
    props.form.sendBy(undefined);
    setBased(undefined);
  };

  return (
    <FieldRow
      name={t("zotero_item", "Zotero item")}
      description={t("zotero_item_note", "The item of the library it is (Save makes the item this {type})", {
        type: modelName(props.type),
      })}
    >
      <Show
        when={based()}
        fallback={
          <button type="button" class={smallButtonClass} data-testid="zotero-from" onClick={() => setPicking(true)}>
            <ZoteroIcon class="size-4" />
            {t("zotero_find", "Find in the library")}
          </button>
        }
      >
        {(item) => (
          // (as wide as the row at most: a long label is cut short, and ✕ stays in view)
          <span class="flex max-w-full min-w-0" data-testid="zotero-based-on">
            <ReferenceChip
              type={item().type}
              label={item().label}
              href={`/${encodeURIComponent(item().type)}/${encodeURIComponent(item().id)}`}
              onRemove={clear}
              removeLabel={t("zotero_not_based_on", "Not based on it")}
            />
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
          onPick={choose}
          onClose={() => setPicking(false)}
        />
      </Show>
    </FieldRow>
  );
}

/**
 * The Zotero item a new item of a class that an item can be made into is (a `newItemFields` entry: a row first among
 * its fields, on its page and in the dialog of a relation). The fields the sync owns are not on the form (they are
 * `readOnly`): Save turns the item picked into the new one, with them (`POST /api/zotero/base-on`). With none picked,
 * it is made by hand, and has none of them.
 */
export default function FromZotero(props: NewItemActionProps) {
  const api = useApi();
  const classes = createMemo(() => getClasses(api));
  return (
    <Show when={classes().targets.includes(props.type)}>
      <Based type={props.type} form={props.form} fallback={classes().fallback} />
    </Show>
  );
}
