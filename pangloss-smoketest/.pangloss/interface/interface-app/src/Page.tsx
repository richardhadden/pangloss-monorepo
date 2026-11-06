import { useNavExpanded } from "@pangloss/interface-core";
import type { ParentProps } from "solid-js";

/**
 * The `main` of a page, inset as the console bar is (5rem in from each side of the page, or 2rem
 * with the nav bar pinned open), so that what is on the page lines up with the bar.
 */
export function Page(props: ParentProps) {
  const { navPinned } = useNavExpanded();
  return (
    <main class={["w-full py-8", { "px-8": navPinned(), "px-20": !navPinned() }]}>
      {props.children}
    </main>
  );
}
