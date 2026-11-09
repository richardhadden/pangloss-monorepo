import { useTranslations } from "@pangloss/interface-core";

/** A book with a Z on it */
export function ZoteroIcon(props: { class?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      class={["select-none fill-none stroke-current", props.class ?? "size-5 stroke-[1.5]"]}
      stroke-linecap="square"
      aria-hidden="true"
    >
      <path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z" />
      <path d="M9 9h6l-6 6h6" />
    </svg>
  );
}

/** Before the name of a field: Zotero keeps this up to date */
export function ZoteroControlled() {
  const { t } = useTranslations();
  return (
    <span
      class="mr-1 inline-flex align-[-0.22em]"
      title={t("zotero_controlled", "Kept up to date from Zotero")}
      data-testid="zotero-controlled"
    >
      <ZoteroIcon class="size-3.5 stroke-2" />
    </span>
  );
}
