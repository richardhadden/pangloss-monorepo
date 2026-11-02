import { createContext, createSignal, useContext } from "solid-js";
import type { Accessor, ParentProps } from "solid-js";

export type ToastTone = "success" | "error";

/** A short message that something has happened */
export interface Toast {
  key: number;
  message: string;
  tone: ToastTone;
}

interface Toasts {
  /** What is showing, the oldest first */
  toasts: Accessor<Toast[]>;
  /** Shows a message for a few seconds (`TOAST_MS`) */
  show: (message: string, tone?: ToastTone) => void;
  dismiss: (key: number) => void;
}

/** How long a toast stays */
export const TOAST_MS = 4000;

const ToastsContext = createContext<Toasts | null>(null);

/**
 * Holds the toasts (short messages that something has happened, such as an item saved) that
 * `Toasts` shows. Put it above the router, so that a toast outlives the page that showed it (a
 * save goes to the item saved). Without this provider `useToasts()` is null, and nothing is shown.
 */
export function ToastsProvider(props: ParentProps) {
  const [toasts, setToasts] = createSignal<Toast[]>([]);
  let next = 0;
  const dismiss = (key: number) => setToasts((all) => all.filter((toast) => toast.key !== key));
  const show = (message: string, tone: ToastTone = "success") => {
    const key = ++next;
    setToasts((all) => [...all, { key, message, tone }]);
    setTimeout(() => dismiss(key), TOAST_MS);
  };
  return <ToastsContext value={{ toasts, show, dismiss }}>{props.children}</ToastsContext>;
}

/** The toasts of the page: `useToasts()?.show("Saved")`. Null without a `ToastsProvider` above */
export function useToasts(): Toasts | null {
  return useContext(ToastsContext);
}
