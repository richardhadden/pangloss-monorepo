import { Show } from "solid-js";
import { useTranslations } from "../context";
import { buttonClass } from "./buttonClass";

/**
 * Previous | Page 2 of 7 | Next, under a list that is read a page at a time. Nothing where there is one page.
 * `onPage` is told the page asked for (from 1); it does not keep the page itself.
 */
export function Pager(props: { page: number; pages: number; onPage: (page: number) => void }) {
  const { t } = useTranslations();
  return (
    <Show when={props.pages > 1}>
      <nav
        class="mt-4 flex items-center justify-center gap-3 text-xs font-semibold text-slate-600 uppercase"
        aria-label={t("pager_pages", "Pages")}
      >
        <button
          type="button"
          class={buttonClass("quiet")}
          disabled={props.page <= 1}
          onClick={() => props.onPage(props.page - 1)}
        >
          {t("pager_previous", "Previous")}
        </button>
        <span>{t("pager_page", "Page {page} of {pages}", { page: String(props.page), pages: String(props.pages) })}</span>
        <button
          type="button"
          class={buttonClass("quiet")}
          disabled={props.page >= props.pages}
          onClick={() => props.onPage(props.page + 1)}
        >
          {t("pager_next", "Next")}
        </button>
      </nav>
    </Show>
  );
}
