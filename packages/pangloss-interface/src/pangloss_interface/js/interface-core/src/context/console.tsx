import { createContext, createSignal, useContext } from "solid-js";
import type { Accessor, ParentProps, Setter } from "solid-js";

interface ConsoleMount {
  /** The element of the console bar that a `Console` renders into (once the bar is in the page) */
  mount: Accessor<HTMLElement | undefined>;
  setMount: Setter<HTMLElement | undefined>;
  /** Whether any page has a `Console` at the moment (otherwise the bar is hidden) */
  active: Accessor<boolean>;
  /** A `Console` calls this when it is shown; the function it returns, when it is gone */
  register: () => () => void;
}

const ConsoleMountContext = createContext<ConsoleMount>();

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
  return (
    <ConsoleMountContext value={{ mount, setMount, active: () => count() > 0, register }}>
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
