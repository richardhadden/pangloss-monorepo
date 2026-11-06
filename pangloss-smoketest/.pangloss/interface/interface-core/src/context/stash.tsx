import { createContext, createEffect, createMemo, createSignal, onSettled, useContext } from "solid-js";
import type { Accessor, ParentProps } from "solid-js";
import type { FormData } from "../schema";

/** A new head document put aside to be finished later */
export interface StashEntry {
  key: string;
  /** Its type (the model of the form it was made in) */
  type: string;
  label: string;
  /** All of it, as the form had it */
  value: FormData;
  /** When it was stashed (an ISO date and time) */
  when: string;
}

interface Stash {
  /** What is stashed, the latest first */
  entries: Accessor<StashEntry[]>;
  /** The entry with this key, if there is one (reactive) */
  get: (key: string) => StashEntry | undefined;
  /** Stashes an item; with the `key` of an entry, that entry is replaced (and comes first). Gives back the key */
  put: (entry: Omit<StashEntry, "key" | "when"> & { key?: string }) => string;
  remove: (key: string) => void;
  /** The types the page is about (where more of them could be made), most recently said first */
  shownTypes: Accessor<string[]>;
  /** A page says it is about `type` while it is shown; the function it returns, when it is gone */
  showFor: (type: string) => () => void;
  /** The key of the entry the form on the page was opened from, if it was */
  openKey: Accessor<string | undefined>;
  /** A form says it was opened from the entry `key`; the function it returns, when it is gone */
  markOpen: (key: string) => () => void;
}

const PREFIX = "pangloss.stash";

const StashContext = createContext<Stash | null>(null);

/**
 * Holds the stashed items (new documents put aside unfinished) in the browser's local storage, as the clipboard is
 * held: they outlive the page, the tabs share them, and each user has their own (`owner`). Read once settled, so that
 * the server-side render and the first client render agree. Without this provider nothing can be stashed.
 */
export function StashProvider(props: ParentProps<{ owner?: Accessor<string | undefined> }>) {
  const [entries, setEntries] = createSignal<StashEntry[]>([]);
  const key = createMemo(() => {
    const owner = props.owner?.() ?? "";
    return owner ? `${PREFIX}.${owner}` : PREFIX;
  });
  const [shown, setShown] = createSignal<string[]>([]);
  const [openKey, setOpenKey] = createSignal<string>();
  const load = (storageKey: string) => {
    try {
      const stored = JSON.parse(localStorage.getItem(storageKey) ?? "[]");
      setEntries(Array.isArray(stored) ? (stored as StashEntry[]) : []);
    } catch {
      setEntries([]);
    }
  };
  const save = (next: StashEntry[]) => {
    setEntries(next);
    try {
      localStorage.setItem(key(), JSON.stringify(next));
    } catch {
      // (storage unavailable or full: the stash is this page's only)
    }
  };
  createEffect(key, (storageKey) => {
    load(storageKey);
  });
  onSettled(() => {
    const changed = (event: StorageEvent) => {
      if (event.key !== null && event.key === key()) load(event.key);
    };
    window.addEventListener("storage", changed);
    return () => window.removeEventListener("storage", changed);
  });
  const state: Stash = {
    entries,
    get: (at) => entries().find((entry) => entry.key === at),
    put: (entry) => {
      const at = entry.key ?? newKey();
      const made: StashEntry = {
        key: at,
        type: entry.type,
        label: entry.label,
        value: entry.value,
        when: new Date().toISOString(),
      };
      save([made, ...entries().filter((other) => other.key !== at)]);
      return at;
    },
    remove: (at) => save(entries().filter((entry) => entry.key !== at)),
    shownTypes: shown,
    showFor: (type) => {
      setShown((all) => [type, ...all]);
      return () =>
        setShown((all) => {
          const at = all.indexOf(type);
          return at < 0 ? all : [...all.slice(0, at), ...all.slice(at + 1)];
        });
    },
    openKey,
    markOpen: (at) => {
      setOpenKey(at);
      return () => setOpenKey((open) => (open === at ? undefined : open));
    },
  };
  return <StashContext value={state}>{props.children}</StashContext>;
}

const newKey = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

/** The stash, or `undefined` where there is none (then nothing offers to stash) */
export function useStash(): Stash | undefined {
  return useContext(StashContext) ?? undefined;
}
