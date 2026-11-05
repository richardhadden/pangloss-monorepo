import { createContext, createSignal, onSettled, useContext } from "solid-js";
import type { Accessor, ParentProps, Setter } from "solid-js";

interface ConsoleMount {
  /** The element of the console bar that a `Console` renders into (once the bar is in the page) */
  mount: Accessor<HTMLElement | undefined>;
  setMount: Setter<HTMLElement | undefined>;
  /** Whether any page has a `Console` at the moment (otherwise the bar is hidden) */
  active: Accessor<boolean>;
  /** A `Console` calls this when it is shown; the function it returns, when it is gone */
  register: () => () => void;
  /** How what refers to the item of the page is shown: a module's button in the console chooses, the page shows it */
  incomingView: IncomingViewState;
}

/**
 * Which view of what refers to the item of the page is chosen: one an interface module adds (`incomingViews`, by its
 * name `app:name`), or none, by the field it is in. A view is chosen only while the page offers it.
 */
export interface IncomingViewState {
  /** The name of the view chosen (whether or not the page offers it); undefined: by field */
  chosen: Accessor<string | undefined>;
  choose: (name: string | undefined) => void;
  /** Whether the page has something the view shows (its button is shown only then) */
  offered: (name: string) => boolean;
  /** The page calls this while it has; the function it returns, when it has not */
  offer: (name: string) => () => void;
}

const INCOMING_VIEW_KEY = "pangloss.incomingView";

/** The view, remembered from one page to the next (read once settled, so that the server-side render and the first
 * client render agree) */
function createIncomingView(): IncomingViewState {
  const [chosen, setChosen] = createSignal<string>();
  const [offers, setOffers] = createSignal<Record<string, number>>({});
  onSettled(() => {
    try {
      setChosen(localStorage.getItem(INCOMING_VIEW_KEY) ?? undefined);
    } catch {
      // (storage unavailable: the choice is just not remembered)
    }
  });
  const count = (name: string, by: number) =>
    setOffers((all) => ({ ...all, [name]: (all[name] ?? 0) + by }));
  return {
    chosen,
    choose: (name) => {
      setChosen(name);
      try {
        if (name) localStorage.setItem(INCOMING_VIEW_KEY, name);
        else localStorage.removeItem(INCOMING_VIEW_KEY);
      } catch {
        // (as above)
      }
    },
    offered: (name) => (offers()[name] ?? 0) > 0,
    offer: (name) => {
      count(name, 1);
      return () => count(name, -1);
    },
  };
}

// (null when there is none, so that a part that can do without a console, as `useIncomingView`, may ask)
const ConsoleMountContext = createContext<ConsoleMount | null>(null);

/**
 * Connects the `ConsoleBar` (fixed at the top, in the frame of the app) to the `Console`
 * that each page renders: the bar says where it is, and the page's `Console` renders into it.
 * A context, so that server-side renders do not share it.
 */
export function ConsoleMountProvider(props: ParentProps) {
  const [mount, setMount] = createSignal<HTMLElement | undefined>();
  const [count, setCount] = createSignal(0);
  const register = () => {
    setCount((n) => n + 1);
    return () => setCount((n) => n - 1);
  };
  const incomingView = createIncomingView();
  return (
    <ConsoleMountContext value={{ mount, setMount, active: () => count() > 0, register, incomingView }}>
      {props.children}
    </ConsoleMountContext>
  );
}

export function useConsoleMount(): ConsoleMount {
  const state = useContext(ConsoleMountContext);
  if (!state) {
    throw new Error("useConsoleMount(): there is no <ConsoleMountProvider> above");
  }
  return state;
}

/**
 * How what refers to the item of the page is shown (see `IncomingViewState`). Without a console (a component on its own,
 * in a test) it is by field, and nothing is offered.
 */
export function useIncomingView(): IncomingViewState {
  return useContext(ConsoleMountContext)?.incomingView ?? BY_FIELD;
}

const BY_FIELD: IncomingViewState = {
  chosen: () => undefined,
  choose: () => {},
  offered: () => false,
  offer: () => () => {},
};
