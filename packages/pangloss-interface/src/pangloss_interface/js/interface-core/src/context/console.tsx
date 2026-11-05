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
  /** How what refers to the item of the page is shown: the console has the buttons, the page shows it */
  incomingOrder: IncomingOrderState;
}

/** What refers to an item, grouped by the field it is in, or sorted by date */
export type IncomingOrder = "field" | "date";

export interface IncomingOrderState {
  order: Accessor<IncomingOrder>;
  setOrder: (order: IncomingOrder) => void;
  /** Whether the page has something to sort by date (the console shows the buttons only then) */
  offered: Accessor<boolean>;
  /** The page calls this while it has; the function it returns, when it has not */
  offer: () => () => void;
}

const INCOMING_ORDER_KEY = "pangloss.incomingOrder";

/** The order, remembered from one page to the next (read once settled, so that the server-side render and the first
 * client render agree) */
function createIncomingOrder(): IncomingOrderState {
  const [order, setOrderSignal] = createSignal<IncomingOrder>("field");
  const [offers, setOffers] = createSignal(0);
  onSettled(() => {
    try {
      if (localStorage.getItem(INCOMING_ORDER_KEY) === "date") setOrderSignal("date");
    } catch {
      // (storage unavailable: the choice is just not remembered)
    }
  });
  return {
    order,
    setOrder: (next) => {
      setOrderSignal(next);
      try {
        localStorage.setItem(INCOMING_ORDER_KEY, next);
      } catch {
        // (as above)
      }
    },
    offered: () => offers() > 0,
    offer: () => {
      setOffers((n) => n + 1);
      return () => setOffers((n) => n - 1);
    },
  };
}

// (null when there is none, so that a part that can do without a console, as `useIncomingOrder`, may ask)
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
  const incomingOrder = createIncomingOrder();
  return (
    <ConsoleMountContext value={{ mount, setMount, active: () => count() > 0, register, incomingOrder }}>
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
 * How what refers to the item of the page is shown (see `IncomingOrderState`). Without a console (a component on its own,
 * in a test) it is grouped by field, and nothing offers to sort it.
 */
export function useIncomingOrder(): IncomingOrderState {
  return useContext(ConsoleMountContext)?.incomingOrder ?? FIELD_ONLY;
}

const FIELD_ONLY: IncomingOrderState = {
  order: () => "field",
  setOrder: () => {},
  offered: () => false,
  offer: () => () => {},
};
