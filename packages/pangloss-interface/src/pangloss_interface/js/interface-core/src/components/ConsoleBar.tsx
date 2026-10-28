import { useConsoleMount } from "../context";

/**
 * The console, fixed along the top of the page, 5rem in from each side of it (the page
 * starts after the 3rem nav bar, so `left-32` and `right-20`), and glassy: the page shows
 * blurred through it. It has nothing of its own: each page renders a `Console`, which
 * appears here. Without one the bar is hidden, and slides in from the top when a page has one. The page
 * is to be in an element with `pt-12` to keep clear of it.
 */
export function ConsoleBar() {
  const { setMount, active } = useConsoleMount();
  return (
    <header
      aria-label="Console"
      aria-hidden={active() ? undefined : "true"}
      class={[
        "fixed top-0 right-20 left-32 z-30 flex h-12 items-center overflow-hidden rounded-b-sm border-[0.5px] border-t-0 border-slate-400/70 bg-slate-200/60 text-xs font-semibold text-slate-700 uppercase backdrop-blur-md transition-[opacity,translate] duration-300",
        {
          "translate-y-0": active(),
          "opacity-100": active(),
          "pointer-events-none": !active(),
          "-translate-y-full": !active(),
          "opacity-0": !active(),
        },
      ]}
    >
      <div ref={setMount} class="flex h-full min-w-0 flex-1 items-center" />
    </header>
  );
}
