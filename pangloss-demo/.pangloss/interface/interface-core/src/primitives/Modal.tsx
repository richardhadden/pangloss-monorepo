import { Portal } from "@solidjs/web";
import { createUniqueId, onSettled } from "solid-js";
import type { ModalProps } from "../types";

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';

/**
 * A dialog over the page, in a portal on the body. Everything behind it is greyed and cannot be
 * clicked (the backdrop is in the way), the keyboard stays inside it (Tab goes round), and Escape
 * or the close button ask for it to be closed (`onClose`; it does not close itself). The focus
 * goes into it when it opens, and back to where it was when it closes. A portal is client-only,
 * so the server renders nothing for it: show it only on a click.
 */
export function Modal(props: ModalProps) {
  const titleId = createUniqueId();
  let panel: HTMLDivElement | undefined;
  const opener = typeof document === "undefined" ? null : (document.activeElement as HTMLElement | null);

  onSettled(() => {
    // (the page behind does not scroll under the backdrop)
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    (panel?.querySelector<HTMLElement>("[autofocus]") ?? panel?.querySelector<HTMLElement>(FOCUSABLE))?.focus();
    return () => {
      document.body.style.overflow = overflow;
      opener?.focus?.();
    };
  });

  function keyDown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.stopPropagation();
      props.onClose();
    } else if (event.key === "Tab" && panel) {
      const focusable = [...panel.querySelectorAll<HTMLElement>(FOCUSABLE)];
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  }

  return (
    <Portal>
      {/* The backdrop: it covers the page, so nothing behind it can be clicked */}
      <div
        class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-[1px]"
        onKeyDown={keyDown}
      >
        <div
          ref={panel}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          class="flex max-h-full w-full max-w-sm flex-col overflow-hidden rounded-sm border-[0.5px] border-slate-400/70 bg-slate-100"
        >
          <div class="flex h-12 shrink-0 items-center justify-between border-b-[0.5px] border-slate-400/70 text-xs font-semibold text-slate-700 uppercase">
            <h2 id={titleId} class="px-4">
              {props.title}
            </h2>
            <button
              type="button"
              aria-label={props.closeLabel ?? "Close"}
              title={props.closeLabel ?? "Close"}
              onClick={() => props.onClose()}
              class="flex h-full w-12 shrink-0 cursor-pointer items-center justify-center select-none hover:bg-slate-400/40 active:bg-slate-400/60"
            >
              <svg
                viewBox="0 0 24 24"
                class="size-5 fill-none stroke-current stroke-2 select-none"
                stroke-linecap="round"
                aria-hidden="true"
              >
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </div>
          <div class="min-h-0 overflow-y-auto">{props.children}</div>
        </div>
      </div>
    </Portal>
  );
}
