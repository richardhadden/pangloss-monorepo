import { useClipboard, useModels, useStash } from "../context";
import { getModel } from "../schema";

/**
 * Whether the bar at the bottom is showing, and whether it is folded to its head line: for the page, which leaves room
 * for it
 */
export function useBottomBar() {
  const clipboard = useClipboard();
  const stash = useStash();
  const definitions = useModels();
  const clipShown = () => (clipboard?.entries().length ?? 0) > 0 && !!clipboard?.formShown();
  // (what is stashed of the types the page is about, or of their subtypes)
  const stashed = () => {
    const types = new Set(
      (stash?.shownTypes() ?? []).flatMap((type) => [type, ...(getModel(definitions, type)?.concreteTypes ?? [])]),
    );
    return (stash?.entries() ?? []).filter((entry) => types.has(entry.type));
  };
  return {
    clipShown,
    stashed,
    shown: () => clipShown() || stashed().length > 0,
    collapsed: () => clipboard?.collapsed() ?? false,
  };
}
