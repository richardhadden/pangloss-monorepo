import { createContext, createSignal, untrack, useContext } from "solid-js";
import type { Accessor, ParentProps, Setter } from "solid-js";

// (each panel that asks is one of its own: a panel of a page that has gone is not the same as that of the next page)
type Panel = { readonly name: string };

interface SidePanels {
  /** The panel that is open on the right, if one is */
  current: Accessor<Panel | undefined>;
  setCurrent: Setter<Panel | undefined>;
}

// (optional: `null` without a provider)
const SidePanelContext = createContext<SidePanels | null>(null);

/**
 * The panels that slide out from the right of the page, below the console (review, history, those of other interface
 * modules): one at a time, so that opening one closes any other. A context, so that server-side renders do not share it.
 */
export function SidePanelProvider(props: ParentProps) {
  const [current, setCurrent] = createSignal<Panel | undefined>();
  return <SidePanelContext value={{ current, setCurrent }}>{props.children}</SidePanelContext>;
}

export interface SidePanel {
  /** Whether this panel is the one open */
  open: Accessor<boolean>;
  /** Opens it (closing whichever other is open) or closes it; or toggles it, with a function of whether it was open */
  setOpen: (open: boolean | ((was: boolean) => boolean)) => void;
}

/**
 * Whether a panel (`name`, for what it is) is open, and a way to open or close it. Opening it closes any other panel
 * that uses this. Each call is a panel of its own, so one on the next page is closed, as it was before it was shared.
 * Without a `SidePanelProvider` above (a test that renders one panel), it is a signal of its own.
 */
export function useSidePanel(name: string): SidePanel {
  const shared = useContext(SidePanelContext);
  const [own, setOwn] = createSignal<Panel | undefined>();
  const current = shared?.current ?? own;
  const setCurrent = shared?.setCurrent ?? setOwn;
  const panel: Panel = { name };
  const open = () => current() === panel;
  const setOpen = (next: boolean | ((was: boolean) => boolean)) => {
    const value = typeof next === "function" ? next(untrack(open)) : next;
    if (value) setCurrent(() => panel);
    else if (untrack(current) === panel) setCurrent(undefined);
  };
  return { open, setOpen };
}
