/**
 * Shows what was just added (or pasted), which is otherwise easy to miss: once the form has drawn it
 * (`find`, called then), it is scrolled into view if it is not, and flashes, a ring round it and a
 * wash over it that fade; and (`focus`) the cursor goes in the first thing in it that takes a value,
 * so it can be filled in at once.
 */
export function revealAdded(find: () => Element | null | undefined, focus = true): void {
  // (after the form has drawn the new item)
  requestAnimationFrame(() => {
    const added = find();
    if (!(added instanceof HTMLElement)) return;
    // (an inset shadow is drawn over the background and under what is in it: the wash)
    const lit = "0 0 0 3px rgb(14 165 233 / 0.55), inset 0 0 0 100vmax rgb(14 165 233 / 0.12)";
    const out = "0 0 0 3px rgb(14 165 233 / 0), inset 0 0 0 100vmax rgb(14 165 233 / 0)";
    // (not where there is no animation, as in the tests)
    added.animate?.(
      [
        { boxShadow: out, offset: 0 },
        { boxShadow: lit, offset: 0.12 },
        { boxShadow: lit, offset: 0.35 },
        { boxShadow: out, offset: 1 },
      ],
      { duration: 1500, easing: "ease-out" },
    );
    if (!focus) {
      added.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
      return;
    }
    const field =
      added.querySelector<HTMLElement>("input:not([type=hidden]), textarea, select") ??
      added.querySelector<HTMLElement>('[role="radio"]');
    // (focusing scrolls to the field; with nothing to focus, to what was added)
    if (field) field.focus();
    else added.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  });
}
