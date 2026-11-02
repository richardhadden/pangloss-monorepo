/**
 * Shows what was just added to a list, which is otherwise easy to miss: once the list has drawn it
 * (`find`, called then), a ring round it that fades, and (`focus`) the cursor in the first thing in it
 * that takes a value, so it can be filled in at once.
 */
export function revealAdded(find: () => Element | null | undefined, focus = true): void {
  // (after the form has drawn the new item)
  requestAnimationFrame(() => {
    const added = find();
    if (!(added instanceof HTMLElement)) return;
    // (not where there is no animation, as in the tests)
    added.animate?.(
      [
        { boxShadow: "0 0 0 3px rgb(100 116 139 / 0.45)" },
        { boxShadow: "0 0 0 3px rgb(100 116 139 / 0)" },
      ],
      { duration: 1200, easing: "ease-out" },
    );
    if (!focus) return;
    const field =
      added.querySelector<HTMLElement>("input:not([type=hidden]), textarea, select") ??
      added.querySelector<HTMLElement>('[role="radio"]');
    field?.focus();
  });
}
