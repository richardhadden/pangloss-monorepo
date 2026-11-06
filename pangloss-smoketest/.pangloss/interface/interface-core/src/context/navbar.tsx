import { createContext, createSignal, onSettled, useContext } from "solid-js";
import type { Accessor, ParentProps } from "solid-js";

interface NavExpanded {
  /** Whether the navigation bar is expanded */
  navExpanded: Accessor<boolean>;
  /** Setting it to false does nothing while the bar is pinned */
  setNavExpanded: (expanded: boolean) => void;
  /** Whether the bar is pinned open (it is then also expanded, and the page is moved across for it) */
  navPinned: Accessor<boolean>;
  setNavPinned: (pinned: boolean) => void;
}

const PINNED_KEY = "pangloss.navPinned";

const NavExpandedContext = createContext<NavExpanded>();

/**
 * Holds whether the navigation bar is expanded, so that the bar (which opens when hovered
 * or clicked) and anything else (a link that closes it, say) share it. It is a context,
 * not a module-level signal, so that server-side renders do not share it.
 */
export function NavExpandedProvider(props: ParentProps) {
  const [navExpanded, setExpanded] = createSignal(false);
  const [navPinned, setPinned] = createSignal(false);
  // Whether it is pinned is remembered (read once settled, so that the server-side render
  // and the first client render agree)
  onSettled(() => {
    try {
      if (localStorage.getItem(PINNED_KEY) === "true") {
        setPinned(true);
        setExpanded(true);
      }
    } catch {
      // (storage unavailable: the pin is just not remembered)
    }
  });
  const setNavExpanded = (expanded: boolean) => {
    if (expanded || !navPinned()) setExpanded(expanded);
  };
  const setNavPinned = (pinned: boolean) => {
    setPinned(pinned);
    if (pinned) setExpanded(true);
    try {
      localStorage.setItem(PINNED_KEY, String(pinned));
    } catch {
      // (as above)
    }
  };
  return (
    <NavExpandedContext value={{ navExpanded, setNavExpanded, navPinned, setNavPinned }}>
      {props.children}
    </NavExpandedContext>
  );
}

/** The signal of whether the navigation bar is expanded: `{ navExpanded, setNavExpanded, navPinned, setNavPinned }` */
export function useNavExpanded(): NavExpanded {
  const state = useContext(NavExpandedContext);
  if (!state) {
    throw new Error("useNavExpanded(): there is no <NavExpandedProvider> above");
  }
  return state;
}
