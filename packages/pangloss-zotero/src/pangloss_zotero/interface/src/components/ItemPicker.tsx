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
    <Modal title={props.title} onClose={props.onClose} size="lg">
      <div class="flex flex-col gap-4 p-4 text-sm" data-testid="zotero-picker">
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

/** A book with a Z on it */
export function ZoteroIcon(props: { class?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      class={["select-none fill-none stroke-current stroke-2", props.class ?? "size-5"]}
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z" />
      <path d="M9 9h6l-6 6h6" />
    </svg>
  );
}
