import type { JSX } from "@solidjs/web";
import type { ParentProps } from "solid-js";
import { useTranslations } from "../context";

/** A link to something outside the application, which opens in a new tab and shows that it will */
export function ExternalLink(props: ParentProps<{ href: string; class?: JSX.HTMLAttributes<HTMLElement>["class"] }>) {
  const { t } = useTranslations();
  return (
    <a
      href={props.href}
      target="_blank"
      rel="noopener noreferrer"
      class={["break-all text-blue-700 underline hover:text-blue-900", props.class]}
    >
      {props.children}
      <svg
        viewBox="0 0 24 24"
        class="ml-1 inline-block size-3.5 fill-none stroke-current stroke-2 align-[-0.125em] select-none"
        stroke-linecap="square"
        aria-hidden="true"
      >
        <path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6" />
      </svg>
      <span class="sr-only">{t("opens_in_new_tab", "(opens in a new tab)")}</span>
    </a>
  );
}
