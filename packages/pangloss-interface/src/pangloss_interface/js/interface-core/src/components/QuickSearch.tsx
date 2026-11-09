import { Dynamic } from "@solidjs/web";
import { createSignal, onSettled, Show } from "solid-js";
import type { Component } from "solid-js";
import { isQuickSearchShortcut } from "./keys";
import type { QuickSearchPopupProps } from "./QuickSearchPopup";

/**
 * The search of the homepage in a popup, from any page: `/` opens it, when not typing in a field. Its code is fetched the
 * first time it is asked for. (Not `lazy`, as `ClipboardBarWhenNeeded` is not: the server never makes it.)
 */
export function QuickSearch(props: { onNavigate: (href: string) => void }) {
  const [open, setOpen] = createSignal(false);
  const [loaded, setLoaded] = createSignal<Component<QuickSearchPopupProps>>();
  let asked = false;
  onSettled(() => {
    const keyDown = (event: KeyboardEvent) => {
      if (!isQuickSearchShortcut(event)) return;
      event.preventDefault();
      setOpen(true);
      if (asked) return;
      asked = true;
      void import("./QuickSearchPopup").then((module) => setLoaded(() => module.default));
    };
    // (capture, and the default prevented: the console's search takes a character typed on the page otherwise)
    window.addEventListener("keydown", keyDown, true);
    return () => window.removeEventListener("keydown", keyDown, true);
  });
  return (
    <Show when={open() ? loaded() : undefined}>
      {(popup) => <Dynamic component={popup()} onNavigate={(href: string) => props.onNavigate(href)} onClose={() => setOpen(false)} />}
    </Show>
  );
}
