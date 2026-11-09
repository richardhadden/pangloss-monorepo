import { createSignal, onSettled } from "solid-js";
import { useConsoleMount, useNavExpanded, useTranslations } from "../context";

/**
 * The console, fixed along the top of the page, 5rem in from each side of it (the page
 * starts after the 3rem nav bar, so `left-32` and `right-20`; with the nav bar pinned open
 * the page starts after 18rem, and it is 2rem in from each side: `left-80` and `right-8`,
 * still centred on the page), and glassy: the page shows
 * blurred through it. It has nothing of its own: each page renders a `Console`, which
 * appears here. Without one the bar is hidden, and slides in from the top when a page has one. The page
 * is to be in an element with `pt-12` to keep clear of it. Once the page is scrolled a little, so that it
 * is passing under the bar, the bar has a faint shadow.
 */
export function ConsoleBar() {
  const { setMount, active } = useConsoleMount();
  const { navPinned } = useNavExpanded();
  const { t } = useTranslations();
  const [scrolled, setScrolled] = createSignal(false);
  onSettled(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    // (the page may already be scrolled, when its position has been restored)
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  });
  return (
    <header
      aria-label={t("console", "Console")}
      aria-hidden={active() ? undefined : "true"}
      class={[
        "fixed top-0 z-30 flex h-12 items-center overflow-hidden rounded-b-xs border-[0.5px] border-t-0 border-slate-400/70 bg-slate-200/60 text-xs font-semibold text-slate-700 uppercase backdrop-blur-md transition-[opacity,translate,box-shadow] duration-300",
        {
          "right-8 left-80": navPinned(),
          "right-20 left-32": !navPinned(),
          "translate-y-0": active(),
          "opacity-100": active(),
          "pointer-events-none": !active(),
          "-translate-y-full": !active(),
          "opacity-0": !active(),
          "shadow-[0_1px_3px_rgb(0_0_0/0.08)]": scrolled(),
        },
      ]}
    >
      <div ref={setMount} class="flex h-full min-w-0 flex-1 items-center" />
    </header>
  );
}
