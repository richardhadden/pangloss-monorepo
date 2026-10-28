import { createContext, createSignal, useContext } from "solid-js";
import type { Accessor, ParentProps, Setter } from "solid-js";

interface NavExpanded {
  /** Whether the navigation bar is expanded */
  navExpanded: Accessor<boolean>;
  setNavExpanded: Setter<boolean>;
}

const NavExpandedContext = createContext<NavExpanded>();

/**
 * Holds whether the navigation bar is expanded, so that the bar (which opens when hovered
 * or clicked) and anything else (a link that closes it, say) share it. It is a context,
 * not a module-level signal, so that server-side renders do not share it.
 */
export function NavExpandedProvider(props: ParentProps) {
  const [navExpanded, setNavExpanded] = createSignal(false);
  return (
    <NavExpandedContext value={{ navExpanded, setNavExpanded }}>
      {props.children}
    </NavExpandedContext>
  );
}

/** The signal of whether the navigation bar is expanded: `{ navExpanded, setNavExpanded }` */
export function useNavExpanded(): NavExpanded {
  const state = useContext(NavExpandedContext);
  if (!state) {
    throw new Error("useNavExpanded(): there is no <NavExpandedProvider> above");
  }
  return state;
}
