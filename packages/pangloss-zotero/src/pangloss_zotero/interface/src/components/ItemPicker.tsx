import { ZoteroIcon } from "./ZoteroIcon";
import { inputClass, Modal, PickOrCreate, smallButtonClass, useTranslations } from "@pangloss/interface-core";
import { createSignal, Show } from "solid-js";
import type { Summary } from "../api";

/**
 * The dialog that finds an item of the library: a search of the class the items are (`fallback`), as a relation's
 * field has, and, with `onAddress`, a box for an item's Zotero address (one that is not synced yet).
 */
export function ItemPicker(props: {
  title: string;
  fallback: string;
  onPick: (item: Summary) => void;
  onAddress?: (address: string) => void;
  /** Said above the search (what will happen) */
  note?: string;
  onClose: () => void;
}) {
  const { t } = useTranslations();
  const [address, setAddress] = createSignal("");
  return (
    // (wider than the form it is over, and tall enough for the list of what is found, which the dialog would cut off)
    <Modal title={props.title} onClose={props.onClose} size="xl">
      <div class="flex min-h-[60vh] flex-col gap-4 p-4 text-sm" data-testid="zotero-picker">
        <Show when={props.note}>
          <p class="text-slate-600">{props.note}</p>
        </Show>
        <PickOrCreate
          types={[props.fallback]}
          createTypes={[]}
          placeholder={t("zotero_search", "Find an item of the Zotero library")}
          onPick={(item) => props.onPick(item as Summary)}
        />
        <Show when={props.onAddress}>
          <form
            class="flex items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              const given = address().trim();
              if (given) props.onAddress?.(given);
            }}
          >
            <input
              class={inputClass}
              aria-label={t("zotero_address", "Or the item's Zotero address")}
              placeholder={t("zotero_address", "Or the item's Zotero address")}
              value={address()}
              onInput={(event) => setAddress(event.currentTarget.value)}
            />
            <button type="submit" class={smallButtonClass} disabled={address().trim() === ""}>
              {t("zotero_link_address", "Link")}
            </button>
          </form>
        </Show>
      </div>
    </Modal>
  );
}

export { ZoteroIcon };
