import { createContext, createEffect, createMemo, createSignal, onSettled, useContext } from "solid-js";
import type { Accessor, ParentProps } from "solid-js";
import type { FormData } from "../schema";

/** Something cut or copied */
export interface ClipEntry {
  key: string;
  /** What it is, with all that is inside it (`clipValue`) */
  value: FormData;
  /** Cut (it goes from the clipboard when it is pasted), or copied (it stays) */
  cut: boolean;
  /** The id of the document it was taken from (none: one not yet made) */
  source?: string;
  /** For an entity: the model of the properties of the relation it was in */
  edgeModel?: string | null;
}

interface Clipboard {
  /** What is on the clipboard, the latest first */
  entries: Accessor<ClipEntry[]>;
  put: (entry: Omit<ClipEntry, "key">) => void;
  /** Says that `key` has been pasted: something cut goes, something copied stays */
  pasted: (key: string) => void;
  remove: (key: string) => void;
  clear: () => void;
  /** Whether the bar that shows it is folded to its head line (remembered, for every user) */
  collapsed: Accessor<boolean>;
  setCollapsed: (collapsed: boolean) => void;
  /** Whether a form is on the page (the bar is shown only then: it is where things are pasted) */
  formShown: Accessor<boolean>;
  /** A form calls this when it is shown; the function it returns, when it is gone */
  registerForm: () => () => void;
}

const PREFIX = "pangloss.clipboard";
const COLLAPSED_KEY = "pangloss.clipboardCollapsed";

const ClipboardContext = createContext<Clipboard | null>(null);

/**
 * Holds what has been cut or copied, in the browser's local storage, so that it outlives the page
 * and is shared by the tabs (what one tab puts there the others see). Each user has their own:
 * `owner` is who is logged in. Read once settled, so that the server-side render and the first
 * client render agree. Without this provider nothing can be cut, copied or pasted.
 */
export function ClipboardProvider(props: ParentProps<{ owner?: Accessor<string | undefined> }>) {
  const [entries, setEntries] = createSignal<ClipEntry[]>([]);
  // (where this user's clipboard is kept)
  const key = createMemo(() => {
    const owner = props.owner?.() ?? "";
    return owner ? `${PREFIX}.${owner}` : PREFIX;
  });
  const [collapsed, setCollapsedSignal] = createSignal(false);
  const [forms, setForms] = createSignal(0);
  const load = (storageKey: string) => {
    try {
      const stored = JSON.parse(localStorage.getItem(storageKey) ?? "[]");
      setEntries(Array.isArray(stored) ? (stored as ClipEntry[]) : []);
    } catch {
      setEntries([]);
    }
  };
  const save = (next: ClipEntry[]) => {
    setEntries(next);
    try {
      localStorage.setItem(key(), JSON.stringify(next));
    } catch {
      // (storage unavailable or full: the clipboard is this page's only)
    }
  };
  // (what is kept there: read in the browser, after the first render, which is the server's)
  createEffect(key, (storageKey) => {
    load(storageKey);
  });
  onSettled(() => {
    try {
      setCollapsedSignal(localStorage.getItem(COLLAPSED_KEY) === "true");
    } catch {
      // (storage unavailable: it starts open)
    }
    const changed = (event: StorageEvent) => {
      if (event.key !== null && event.key === key()) load(event.key);
    };
    window.addEventListener("storage", changed);
    return () => window.removeEventListener("storage", changed);
  });
  const state: Clipboard = {
    entries,
    put: (entry) => save([{ ...entry, key: newKey() }, ...entries()]),
    pasted: (at) => {
      if (entries().find((entry) => entry.key === at)?.cut) state.remove(at);
    },
    remove: (at) => save(entries().filter((entry) => entry.key !== at)),
    clear: () => save([]),
    formShown: () => forms() > 0,
    registerForm: () => {
      setForms((n) => n + 1);
      return () => setForms((n) => n - 1);
    },
    collapsed,
    setCollapsed: (next) => {
      setCollapsedSignal(next);
      try {
        localStorage.setItem(COLLAPSED_KEY, String(next));
      } catch {
        // (as above)
      }
    },
  };
  return <ClipboardContext value={state}>{props.children}</ClipboardContext>;
}

const newKey = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

/** The clipboard, or `undefined` where there is none (then nothing offers to cut, copy or paste) */
export function useClipboard(): Clipboard | undefined {
  return useContext(ClipboardContext) ?? undefined;
}
