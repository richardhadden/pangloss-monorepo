// The icons that are drawn in more than one place. (One file: each file shared by the frame and by code loaded later
// is fetched by itself, so a file for each icon is a request for each on every page.)

import { useTranslations } from "../context";

/** A small spinner, in the colour of the text around it, for something that is loading (`class` for another size) */
export function Spinner(props: { class?: string }) {
  const { t } = useTranslations();
  return (
    <svg
      role="status"
      aria-label={t("loading", "Loading…")}
      viewBox="0 0 24 24"
      class={[props.class ?? "size-3.5", "animate-spin select-none fill-none stroke-current stroke-[3]"]}
      stroke-linecap="round"
    >
      <circle cx="12" cy="12" r="9" class="opacity-25" />
      <path d="M21 12a9 9 0 0 0-9-9" />
    </svg>
  );
}

// (whole class names, so that Tailwind finds them: the line is as heavy on screen at each size)
const SIZES = {
  "5": "size-5 stroke-[1.5]",
  "4": "size-4 stroke-[1.75]",
  "3.5": "size-3.5 stroke-2",
};

/**
 * The ✕ of closing, cancelling, clearing or taking out, as every icon is drawn: thin and sharp. `size` `5` (the
 * default) is a bar's or the console's; `4` a panel's head; `3.5` beside text
 */
export function CloseIcon(props: { size?: keyof typeof SIZES }) {
  return (
    <svg
      viewBox="0 0 24 24"
      class={`${SIZES[props.size ?? "5"]} fill-none stroke-current select-none`}
      stroke-linecap="square"
      aria-hidden="true"
    >
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}
