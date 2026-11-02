import { For, Show } from "solid-js";
import { useClipboard, useToasts, useTranslations } from "../context";

/**
 * The toasts (`useToasts().show`), fixed at the bottom right of the page, the latest lowest, each
 * glassy as the bars are (sliding up as it comes), and closed by clicking it. They are kept clear of the clipboard bar when it
 * is showing, and above a dialog. A screen reader is told of each (`role="status"`).
 */
export function Toasts() {
  const toasts = useToasts();
  const clipboard = useClipboard();
  const { t } = useTranslations();
  const barShown = () => (clipboard?.entries().length ?? 0) > 0 && !!clipboard?.formShown();
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={t("toasts", "Notifications")}
      class={[
        "pointer-events-none fixed right-4 z-60 flex w-80 flex-col items-end gap-2 transition-[bottom] duration-300",
        {
          "bottom-4": !barShown(),
          "bottom-52": barShown() && !clipboard?.collapsed(),
          "bottom-12": barShown() && !!clipboard?.collapsed(),
        },
      ]}
    >
      <For each={toasts?.toasts() ?? []}>
        {(toast) => (
          <button
            type="button"
            aria-label={t("toast_dismiss", "Dismiss: {message}", { message: toast.message })}
            onClick={() => toasts?.dismiss(toast.key)}
            class={[
              "pointer-events-auto transition-[opacity,translate] duration-300 starting:translate-y-2 starting:opacity-0 flex max-w-full cursor-pointer items-center gap-2 rounded-sm border-[0.5px] px-3 py-2 text-left text-sm shadow-md backdrop-blur-md",
              {
                "border-emerald-700/50": toast.tone === "success",
                "bg-emerald-100/80": toast.tone === "success",
                "text-emerald-900": toast.tone === "success",
                "border-red-700/50": toast.tone === "error",
                "bg-red-100/80": toast.tone === "error",
                "text-red-900": toast.tone === "error",
              },
            ]}
          >
            <svg
              viewBox="0 0 24 24"
              class="size-4 shrink-0 select-none fill-none stroke-current stroke-2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <Show when={toast.tone === "success"} fallback={<path d="M12 8v5M12 16.5v.5M12 3l10 18H2z" />}>
                <path d="M5 12.5l4.5 4.5L19 7.5" />
              </Show>
            </svg>
            <span class="min-w-0">{toast.message}</span>
          </button>
        )}
      </For>
    </div>
  );
}
