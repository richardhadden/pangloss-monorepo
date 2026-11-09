import { createEffect } from "solid-js";

// Once the form or item page is on show, scrolls to the document inside it whose id is `id` (the block that has it in
// `data-item-id`), and lights it up for a moment, so the eye finds it; and again if `id` becomes another
export function ScrollToNested(props: { id: string | undefined }) {
  createEffect(
    () => props.id,
    (id) => {
      if (!id) return;
      // (after the browser has laid the page out)
      requestAnimationFrame(() => {
        const block = document.querySelector<HTMLElement>(`[data-item-id="${CSS.escape(id)}"]`);
        if (!block) return;
        block.scrollIntoView({ block: "start" });
        block.animate(
          [{ backgroundColor: "rgb(253 230 138 / 0.45)" }, { backgroundColor: "transparent" }],
          { duration: 2000, easing: "ease-out" },
        );
      });
    },
  );
  return null;
}
