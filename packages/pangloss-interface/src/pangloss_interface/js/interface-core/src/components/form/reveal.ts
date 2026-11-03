/**
 * Shows what was just added (or pasted), which is otherwise easy to miss: once the form has drawn it
 * (`find`, called then), it is scrolled into view if it is not, and flashes, a ring round it and a
 * wash over it that fade, with rounded corners, in the colour of what was added (the tint of the
 * first thing marked `data-tint` in it, the outermost: a space, the type of a block, a chip; sky
 * for what has none); and (`focus`) the cursor goes in the first thing in it that takes a value, so
 * it can be filled in at once.
 */
export function revealAdded(find: () => Element | null | undefined, focus = true): void {
  // (after the form has drawn the new item)
  requestAnimationFrame(() => {
    const added = find();
    if (!(added instanceof HTMLElement)) return;
    // (an inset shadow is drawn over the background and under what is in it: the wash)
    const colour = tintOf(added);
    const shade = (alpha: number) => `rgb(from ${colour} r g b / ${alpha})`;
    const lit = `0 0 0 3px ${shade(0.55)}, inset 0 0 0 100vmax ${shade(0.12)}`;
    const out = `0 0 0 3px ${shade(0)}, inset 0 0 0 100vmax ${shade(0)}`;
    // (the shadow follows the corners: what has square ones has them rounded while it flashes)
    const radius = getComputedStyle(added).borderRadius;
    const borderRadius = radius === "" || /^0(px)?$/.test(radius) ? "2px" : radius;
    // (not where there is no animation, as in the tests)
    added.animate?.(
      [
        { boxShadow: out, borderRadius, offset: 0 },
        { boxShadow: lit, borderRadius, offset: 0.12 },
        { boxShadow: lit, borderRadius, offset: 0.35 },
        { boxShadow: out, borderRadius, offset: 1 },
      ],
      { duration: 1000, easing: "ease-out" },
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

// (the interface's own colour, for what has no tint)
const SKY = "rgb(14 165 233)";

/** The background of the first element marked `data-tint` (the element itself, or the first inside it), or sky */
function tintOf(element: HTMLElement): string {
  const tinted = element.matches("[data-tint]") ? element : element.querySelector("[data-tint]");
  if (!tinted) return SKY;
  const background = getComputedStyle(tinted).backgroundColor;
  // (nothing behind it, or a browser that cannot say: sky)
  if (!background || background === "transparent" || /^rgba\(0, 0, 0, 0\)$/.test(background)) return SKY;
  return background;
}
